"""JWT token handling for authentication with DB storage."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

import jwt
from flask import current_app, g, jsonify, request

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)


def generate_jti() -> str:
    """JWT ID 생성"""
    return uuid.uuid4().hex


def create_access_token(
    user_id: str,
    email: str,
    name: str,
    expires_delta: Optional[timedelta] = None,
) -> Tuple[str, str]:
    """
    Create a JWT access token.
    
    Returns:
        Tuple of (token, jti) - jti는 세션 추적에 사용
    """
    expires = datetime.now(timezone.utc) + (expires_delta or JWT_ACCESS_TOKEN_EXPIRES)
    jti = generate_jti()
    
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "exp": expires,
        "iat": datetime.now(timezone.utc),
        "jti": jti,
        "type": "access",
    }
    
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token, jti


def create_refresh_token(
    user_id: str,
    device_info: str = "",
    ip_address: str = "",
) -> Tuple[str, str]:
    """
    Create a JWT refresh token and save to DB.
    
    Returns:
        Tuple of (token, token_id) - token_id는 DB에 저장된 ID
    """
    from ..db.token_repository import get_token_repository, hash_token
    from ..db.models import RefreshToken, generate_id
    
    expires = datetime.now(timezone.utc) + JWT_REFRESH_TOKEN_EXPIRES
    token_id = generate_id()
    
    payload = {
        "sub": user_id,
        "exp": expires,
        "iat": datetime.now(timezone.utc),
        "jti": token_id,
        "type": "refresh",
    }
    
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    
    # DB에 저장
    refresh_token = RefreshToken(
        token_id=token_id,
        user_id=user_id,
        token_hash=hash_token(token),
        device_info=device_info,
        ip_address=ip_address,
        is_revoked=False,
        expires_at=expires.isoformat(),
    )
    
    try:
        repo = get_token_repository()
        repo.save_refresh_token(refresh_token)
    except Exception as e:
        # 로깅만 하고 진행 (DB 실패해도 토큰은 발급)
        if current_app:
            current_app.logger.warning(f"Failed to save refresh token to DB: {e}")
    
    return token, token_id


def save_session(
    user_id: str,
    access_token_jti: str,
    refresh_token_id: str,
    device_info: str = "",
    ip_address: str = "",
) -> Optional[str]:
    """세션 정보를 DB에 저장"""
    from ..db.token_repository import get_token_repository
    from ..db.models import ActiveSession, generate_id
    
    session = ActiveSession(
        session_id=generate_id(),
        user_id=user_id,
        access_token_jti=access_token_jti,
        refresh_token_id=refresh_token_id,
        device_info=device_info,
        ip_address=ip_address,
    )
    
    try:
        repo = get_token_repository()
        repo.save_session(session)
        return session.session_id
    except Exception as e:
        if current_app:
            current_app.logger.warning(f"Failed to save session to DB: {e}")
        return None


def verify_access_token(token: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Verify a JWT access token.
    
    Returns:
        Tuple of (is_valid, payload, error_message)
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        if payload.get("type") != "access":
            return False, None, "Invalid token type"
        
        # 세션이 유효한지 확인 (선택적)
        jti = payload.get("jti")
        if jti:
            try:
                from ..db.token_repository import get_token_repository
                repo = get_token_repository()
                session = repo.get_session_by_jti(jti)
                if session and not session.is_active:
                    return False, None, "Session has been invalidated"
                # 세션 활동 시간 업데이트
                if session:
                    repo.update_session_activity(session.session_id)
            except Exception:
                pass  # DB 실패해도 토큰 자체는 유효
        
        return True, payload, None
        
    except jwt.ExpiredSignatureError:
        return False, None, "Token has expired"
    except jwt.InvalidTokenError as e:
        return False, None, f"Invalid token: {str(e)}"


def verify_refresh_token(token: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Verify a JWT refresh token (DB 확인 포함).
    
    Returns:
        Tuple of (is_valid, payload, error_message)
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        if payload.get("type") != "refresh":
            return False, None, "Invalid token type"
        
        # DB에서 토큰이 유효한지 확인
        try:
            from ..db.token_repository import get_token_repository
            repo = get_token_repository()
            if not repo.is_token_valid(token):
                return False, None, "Token has been revoked"
            
            # 마지막 사용 시간 업데이트
            token_id = payload.get("jti")
            if token_id:
                repo.update_last_used(token_id)
        except Exception as e:
            # DB 실패 시 토큰 자체의 유효성만으로 판단
            pass
        
        return True, payload, None
        
    except jwt.ExpiredSignatureError:
        return False, None, "Refresh token has expired"
    except jwt.InvalidTokenError as e:
        return False, None, f"Invalid refresh token: {str(e)}"


def revoke_refresh_token(token: str) -> bool:
    """Refresh token 무효화 (로그아웃)"""
    from ..db.token_repository import get_token_repository, hash_token
    
    try:
        repo = get_token_repository()
        return repo.revoke_token_by_hash(hash_token(token))
    except Exception:
        return False


def revoke_all_user_tokens(user_id: str) -> int:
    """사용자의 모든 토큰 무효화 (전체 로그아웃)"""
    from ..db.token_repository import get_token_repository
    
    try:
        repo = get_token_repository()
        tokens_revoked = repo.revoke_all_user_tokens(user_id)
        sessions_deactivated = repo.deactivate_all_user_sessions(user_id)
        return tokens_revoked + sessions_deactivated
    except Exception:
        return 0


def auth_required(f: Callable) -> Callable:
    """Decorator to require authentication for a route."""
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        auth_header = request.headers.get("Authorization")
        
        if not auth_header:
            return jsonify({"error": "Authorization header missing"}), 401
        
        parts = auth_header.split()
        
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return jsonify({"error": "Invalid authorization header format"}), 401
        
        token = parts[1]
        is_valid, payload, error = verify_access_token(token)
        
        if not is_valid:
            return jsonify({"error": error}), 401
        
        # Store user info in Flask's g object for access in route handlers
        g.current_user = {
            "user_id": payload["sub"],
            "email": payload["email"],
            "name": payload["name"],
            "jti": payload.get("jti"),
        }
        
        return f(*args, **kwargs)
    
    return decorated_function


def get_current_user() -> Optional[Dict[str, Any]]:
    """Get the current authenticated user from Flask's g object."""
    return getattr(g, "current_user", None)
