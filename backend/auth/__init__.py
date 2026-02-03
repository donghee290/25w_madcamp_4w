"""Authentication module with Google OAuth 2.0 support."""

from .google_oauth import google_oauth_bp, init_google_oauth
from .jwt_handler import (
    create_access_token, 
    create_refresh_token,
    verify_access_token, 
    auth_required,
    get_current_user,
    revoke_refresh_token
)
from .models import User

__all__ = [
    "google_oauth_bp",
    "init_google_oauth",
    "create_access_token",
    "create_refresh_token",
    "verify_access_token",
    "auth_required",
    "get_current_user",
    "revoke_refresh_token",
    "User",
]
