"""Google OAuth 2.0 authentication handler with DB integration."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests
from flask import Blueprint, current_app, jsonify, redirect, request, session, url_for

from .jwt_handler import (
    create_access_token, 
    create_refresh_token, 
    save_session,
    revoke_refresh_token,
    revoke_all_user_tokens,
    verify_access_token,
)
from ..db.models import User, generate_id
from ..db.repository import get_user_repository

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

# 핵심: 외부 도메인 기반으로 리다이렉트 URI 생성
# 내부 포트(8000)가 아닌 외부 HTTPS 도메인 사용
EXTERNAL_BASE_URL = os.getenv("EXTERNAL_BASE_URL", "https://your-domain.com")
GOOGLE_REDIRECT_URI = f"{EXTERNAL_BASE_URL}/api/auth/google/callback"

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# OAuth scopes
GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
]

# Create Blueprint
google_oauth_bp = Blueprint("google_oauth", __name__, url_prefix="/api/auth")


def init_google_oauth(app: Any) -> None:
    """Initialize Google OAuth with app configuration."""
    global GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, EXTERNAL_BASE_URL, GOOGLE_REDIRECT_URI
    
    GOOGLE_CLIENT_ID = app.config.get("GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID)
    GOOGLE_CLIENT_SECRET = app.config.get("GOOGLE_CLIENT_SECRET", GOOGLE_CLIENT_SECRET)
    EXTERNAL_BASE_URL = app.config.get("EXTERNAL_BASE_URL", EXTERNAL_BASE_URL)
    GOOGLE_REDIRECT_URI = f"{EXTERNAL_BASE_URL}/api/auth/google/callback"
    
    # Set secret key for session
    if not app.secret_key:
        app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))


@google_oauth_bp.route("/google/login", methods=["GET"])
def google_login():
    """
    Initiate Google OAuth 2.0 login flow.
    
    Frontend redirects user here, then we redirect to Google.
    After authentication, Google redirects back to /callback.
    """
    # Generate state token to prevent CSRF
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    
    # Store frontend callback URL if provided
    frontend_callback = request.args.get("callback_url")
    if frontend_callback:
        session["frontend_callback"] = frontend_callback
    
    # Build Google OAuth URL
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return redirect(auth_url)


@google_oauth_bp.route("/google/callback", methods=["GET"])
def google_callback():
    """
    Handle Google OAuth callback.
    
    Google redirects here after user authenticates.
    We exchange the code for tokens and create a JWT, saving to DB.
    """
    # Check for errors
    error = request.args.get("error")
    if error:
        return jsonify({"error": f"OAuth error: {error}"}), 400
    
    # Verify state to prevent CSRF
    state = request.args.get("state")
    stored_state = session.pop("oauth_state", None)
    
    if not state or state != stored_state:
        return jsonify({"error": "Invalid state parameter"}), 400
    
    # Get authorization code
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "Missing authorization code"}), 400
    
    try:
        # Exchange code for tokens
        token_data = exchange_code_for_tokens(code)
        
        # Get user info from Google
        userinfo = get_google_userinfo(token_data["access_token"])
        
        # Create or update user in database
        user = save_user_to_db(userinfo)
        
        # Get device info and IP for session tracking
        device_info = request.headers.get("User-Agent", "")
        ip_address = request.remote_addr or ""
        
        # Create JWT tokens (now saved to DB)
        access_token, access_jti = create_access_token(
            user_id=user.user_id,
            email=user.email,
            name=user.name,
        )
        refresh_token, refresh_token_id = create_refresh_token(
            user_id=user.user_id,
            device_info=device_info,
            ip_address=ip_address,
        )
        
        # Save session to DB
        save_session(
            user_id=user.user_id,
            access_token_jti=access_jti,
            refresh_token_id=refresh_token_id,
            device_info=device_info,
            ip_address=ip_address,
        )
        
        current_app.logger.info(f"User logged in: {user.email} (ID: {user.user_id})")
        
        # Check if we should redirect to frontend
        frontend_callback = session.pop("frontend_callback", None)
        
        if frontend_callback:
            # Redirect to frontend with tokens in query params
            # Frontend should extract tokens and store them
            redirect_url = f"{frontend_callback}?access_token={access_token}&refresh_token={refresh_token}"
            return redirect(redirect_url)
        
        # Return JSON response for API clients
        return jsonify({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "user": {
                "id": user.user_id,
                "email": user.email,
                "name": user.name,
                "picture": user.picture,
            },
        })
        
    except Exception as e:
        current_app.logger.error(f"OAuth callback error: {str(e)}")
        return jsonify({"error": str(e)}), 500


@google_oauth_bp.route("/me", methods=["GET"])
def get_current_user():
    """Get current user info from JWT token."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid authorization header"}), 401
    
    token = auth_header.split(" ")[1]
    is_valid, payload, error = verify_access_token(token)
    
    if not is_valid:
        return jsonify({"error": error}), 401
    
    # Get full user info from DB
    try:
        user_repo = get_user_repository()
        user = user_repo.get_by_id(payload["sub"])
        if user:
            return jsonify({
                "user_id": user.user_id,
                "email": user.email,
                "name": user.name,
                "picture": user.picture,
                "created_at": user.created_at,
            })
    except Exception:
        pass
    
    # Fallback to token payload
    return jsonify({
        "user_id": payload["sub"],
        "email": payload["email"],
        "name": payload["name"],
    })


@google_oauth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """
    Logout endpoint - revokes refresh token in DB.
    Client should also delete local tokens.
    """
    # HTML 링크로 접속 시 (GET)
    if request.method == "GET":
        session.clear()
        return redirect("/")

    auth_header = request.headers.get("Authorization")

    refresh_token = request.json.get("refresh_token") if request.is_json else None
    
    revoked = False
    
    # Revoke refresh token if provided
    if refresh_token:
        revoked = revoke_refresh_token(refresh_token)
    
    # If access token provided, try to get user and revoke all their tokens
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        is_valid, payload, _ = verify_access_token(token)
        if is_valid:
            user_id = payload.get("sub")
            if user_id:
                # Deactivate current session
                from ..db.token_repository import get_token_repository
                try:
                    repo = get_token_repository()
                    jti = payload.get("jti")
                    if jti:
                        repo.deactivate_session_by_jti(jti)
                        revoked = True
                except Exception:
                    pass
    
    # Server-side session cleanup
    session.clear()
    
    return jsonify({
        "message": "Logged out successfully",
        "token_revoked": revoked,
    })


@google_oauth_bp.route("/logout-all", methods=["POST"])
def logout_all_devices():
    """
    Logout from all devices - revokes all user's tokens.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Authorization required"}), 401
    
    token = auth_header.split(" ")[1]
    is_valid, payload, error = verify_access_token(token)
    
    if not is_valid:
        return jsonify({"error": error}), 401
    
    user_id = payload.get("sub")
    count = revoke_all_user_tokens(user_id)
    
    session.clear()
    
    return jsonify({
        "message": "Logged out from all devices",
        "revoked_count": count,
    })


@google_oauth_bp.route("/sessions", methods=["GET"])
def get_user_sessions():
    """Get all active sessions for current user."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Authorization required"}), 401
    
    token = auth_header.split(" ")[1]
    is_valid, payload, error = verify_access_token(token)
    
    if not is_valid:
        return jsonify({"error": error}), 401
    
    user_id = payload.get("sub")
    
    try:
        from ..db.token_repository import get_token_repository
        repo = get_token_repository()
        sessions = repo.get_user_sessions(user_id)
        
        return jsonify({
            "sessions": [
                {
                    "session_id": s.session_id,
                    "device_info": s.device_info,
                    "ip_address": s.ip_address,
                    "created_at": s.created_at,
                    "last_activity": s.last_activity,
                    "is_current": s.access_token_jti == payload.get("jti"),
                }
                for s in sessions
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@google_oauth_bp.route("/refresh", methods=["POST"])
def refresh_access_token():
    """
    Refresh access token using refresh token.
    """
    from .jwt_handler import verify_refresh_token
    
    data = request.get_json() or {}
    refresh_token = data.get("refresh_token")
    
    if not refresh_token:
        return jsonify({"error": "Refresh token required"}), 400
    
    is_valid, payload, error = verify_refresh_token(refresh_token)
    
    if not is_valid:
        return jsonify({"error": error}), 401
    
    user_id = payload.get("sub")
    
    # Get user from DB
    try:
        user_repo = get_user_repository()
        user = user_repo.get_by_id(user_id)
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Create new access token
        access_token, access_jti = create_access_token(
            user_id=user.user_id,
            email=user.email,
            name=user.name,
        )
        
        # Update session with new access token JTI
        refresh_token_id = payload.get("jti")
        device_info = request.headers.get("User-Agent", "")
        ip_address = request.remote_addr or ""
        
        save_session(
            user_id=user.user_id,
            access_token_jti=access_jti,
            refresh_token_id=refresh_token_id,
            device_info=device_info,
            ip_address=ip_address,
        )
        
        return jsonify({
            "access_token": access_token,
            "token_type": "Bearer",
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """Exchange authorization code for access and refresh tokens."""
    data = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": GOOGLE_REDIRECT_URI,
    }
    
    response = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=30)
    response.raise_for_status()
    
    return response.json()


def get_google_userinfo(access_token: str) -> Dict[str, Any]:
    """Get user info from Google using access token."""
    headers = {"Authorization": f"Bearer {access_token}"}
    
    response = requests.get(GOOGLE_USERINFO_URL, headers=headers, timeout=30)
    response.raise_for_status()
    
    return response.json()


def save_user_to_db(userinfo: Dict[str, Any]) -> User:
    """Save or update user in MongoDB and return User object."""
    try:
        user_repo = get_user_repository()
        
        # Check if user exists by Google ID
        existing_user = user_repo.get_by_google_id(userinfo["sub"])
        
        if existing_user:
            # Update last login
            user_repo.update_last_login(existing_user.user_id)
            existing_user.last_login = datetime.now(timezone.utc).isoformat()
            return existing_user
        else:
            # Create new user
            user = User.from_google_userinfo(userinfo)
            user_repo.save(user)
            current_app.logger.info(f"New user created: {user.email}")
            return user
        
    except Exception as e:
        current_app.logger.warning(f"Failed to save user to DB: {str(e)}")
        # Return a temporary user object for the session
        return User.from_google_userinfo(userinfo)
