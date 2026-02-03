"""Token repository for JWT token management in MongoDB."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import List, Optional

from .models import RefreshToken, ActiveSession, generate_id, utc_now


def hash_token(token: str) -> str:
    """토큰을 SHA-256으로 해시하여 저장"""
    return hashlib.sha256(token.encode()).hexdigest()


class TokenRepository:
    """MongoDB repository for JWT tokens."""
    
    def __init__(self, uri: str, db_name: str) -> None:
        from pymongo import MongoClient
        
        self._client = MongoClient(uri)
        self._db = self._client[db_name]
        self._refresh_tokens = self._db["refresh_tokens"]
        self._sessions = self._db["active_sessions"]
        
        # Create indexes
        try:
            self._refresh_tokens.create_index("token_id", unique=True)
            self._refresh_tokens.create_index("user_id")
            self._refresh_tokens.create_index("token_hash")
            self._refresh_tokens.create_index("expires_at")
            
            self._sessions.create_index("session_id", unique=True)
            self._sessions.create_index("user_id")
            self._sessions.create_index("access_token_jti")
        except Exception:
            pass
    
    # =========================================================================
    # Refresh Token Operations
    # =========================================================================
    
    def save_refresh_token(self, token: RefreshToken) -> None:
        """Refresh token 저장"""
        doc = token.to_dict()
        doc["_id"] = token.token_id
        self._refresh_tokens.replace_one({"_id": token.token_id}, doc, upsert=True)
    
    def get_refresh_token_by_hash(self, token_hash: str) -> Optional[RefreshToken]:
        """해시로 refresh token 조회"""
        doc = self._refresh_tokens.find_one({"token_hash": token_hash})
        if not doc:
            return None
        doc.pop("_id", None)
        return RefreshToken.from_dict(doc)
    
    def get_refresh_token_by_id(self, token_id: str) -> Optional[RefreshToken]:
        """ID로 refresh token 조회"""
        doc = self._refresh_tokens.find_one({"_id": token_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return RefreshToken.from_dict(doc)
    
    def get_user_refresh_tokens(self, user_id: str) -> List[RefreshToken]:
        """사용자의 모든 refresh token 조회"""
        docs = self._refresh_tokens.find({"user_id": user_id, "is_revoked": False})
        return [RefreshToken.from_dict({**doc, "token_id": doc.pop("_id", doc.get("token_id"))}) for doc in docs]
    
    def revoke_token(self, token_id: str) -> bool:
        """특정 토큰 무효화"""
        result = self._refresh_tokens.update_one(
            {"_id": token_id},
            {"$set": {"is_revoked": True}}
        )
        return result.modified_count > 0
    
    def revoke_token_by_hash(self, token_hash: str) -> bool:
        """해시로 토큰 무효화"""
        result = self._refresh_tokens.update_one(
            {"token_hash": token_hash},
            {"$set": {"is_revoked": True}}
        )
        return result.modified_count > 0
    
    def revoke_all_user_tokens(self, user_id: str) -> int:
        """사용자의 모든 토큰 무효화 (전체 로그아웃)"""
        result = self._refresh_tokens.update_many(
            {"user_id": user_id},
            {"$set": {"is_revoked": True}}
        )
        return result.modified_count
    
    def update_last_used(self, token_id: str) -> None:
        """토큰 마지막 사용 시간 업데이트"""
        self._refresh_tokens.update_one(
            {"_id": token_id},
            {"$set": {"last_used_at": utc_now()}}
        )
    
    def delete_expired_tokens(self) -> int:
        """만료된 토큰 삭제"""
        now = datetime.now(timezone.utc).isoformat()
        result = self._refresh_tokens.delete_many({"expires_at": {"$lt": now}})
        return result.deleted_count
    
    def is_token_valid(self, token: str) -> bool:
        """토큰이 유효한지 확인 (해시로 조회 후 revoked 및 만료 확인)"""
        token_hash = hash_token(token)
        doc = self._refresh_tokens.find_one({"token_hash": token_hash})
        
        if not doc:
            return False
        
        if doc.get("is_revoked", False):
            return False
        
        expires_at = doc.get("expires_at", "")
        if expires_at:
            now = datetime.now(timezone.utc).isoformat()
            if expires_at < now:
                return False
        
        return True
    
    # =========================================================================
    # Session Operations
    # =========================================================================
    
    def save_session(self, session: ActiveSession) -> None:
        """세션 저장"""
        doc = session.to_dict()
        doc["_id"] = session.session_id
        self._sessions.replace_one({"_id": session.session_id}, doc, upsert=True)
    
    def get_session_by_jti(self, jti: str) -> Optional[ActiveSession]:
        """Access token JTI로 세션 조회"""
        doc = self._sessions.find_one({"access_token_jti": jti})
        if not doc:
            return None
        doc.pop("_id", None)
        return ActiveSession.from_dict(doc)
    
    def get_user_sessions(self, user_id: str) -> List[ActiveSession]:
        """사용자의 모든 활성 세션 조회"""
        docs = self._sessions.find({"user_id": user_id, "is_active": True})
        return [ActiveSession.from_dict({**doc, "session_id": doc.pop("_id", doc.get("session_id"))}) for doc in docs]
    
    def deactivate_session(self, session_id: str) -> bool:
        """세션 비활성화"""
        result = self._sessions.update_one(
            {"_id": session_id},
            {"$set": {"is_active": False}}
        )
        return result.modified_count > 0
    
    def deactivate_session_by_jti(self, jti: str) -> bool:
        """JTI로 세션 비활성화"""
        result = self._sessions.update_one(
            {"access_token_jti": jti},
            {"$set": {"is_active": False}}
        )
        return result.modified_count > 0
    
    def deactivate_all_user_sessions(self, user_id: str) -> int:
        """사용자의 모든 세션 비활성화"""
        result = self._sessions.update_many(
            {"user_id": user_id},
            {"$set": {"is_active": False}}
        )
        return result.modified_count
    
    def update_session_activity(self, session_id: str) -> None:
        """세션 마지막 활동 시간 업데이트"""
        self._sessions.update_one(
            {"_id": session_id},
            {"$set": {"last_activity": utc_now()}}
        )


class InMemoryTokenRepository:
    """In-memory repository for development/testing."""
    
    def __init__(self) -> None:
        self._refresh_tokens: dict[str, RefreshToken] = {}
        self._sessions: dict[str, ActiveSession] = {}
    
    def save_refresh_token(self, token: RefreshToken) -> None:
        self._refresh_tokens[token.token_id] = token
    
    def get_refresh_token_by_hash(self, token_hash: str) -> Optional[RefreshToken]:
        for token in self._refresh_tokens.values():
            if token.token_hash == token_hash:
                return token
        return None
    
    def get_refresh_token_by_id(self, token_id: str) -> Optional[RefreshToken]:
        return self._refresh_tokens.get(token_id)
    
    def get_user_refresh_tokens(self, user_id: str) -> List[RefreshToken]:
        return [t for t in self._refresh_tokens.values() if t.user_id == user_id and not t.is_revoked]
    
    def revoke_token(self, token_id: str) -> bool:
        if token_id in self._refresh_tokens:
            self._refresh_tokens[token_id].is_revoked = True
            return True
        return False
    
    def revoke_token_by_hash(self, token_hash: str) -> bool:
        for token in self._refresh_tokens.values():
            if token.token_hash == token_hash:
                token.is_revoked = True
                return True
        return False
    
    def revoke_all_user_tokens(self, user_id: str) -> int:
        count = 0
        for token in self._refresh_tokens.values():
            if token.user_id == user_id:
                token.is_revoked = True
                count += 1
        return count
    
    def update_last_used(self, token_id: str) -> None:
        if token_id in self._refresh_tokens:
            self._refresh_tokens[token_id].last_used_at = utc_now()
    
    def delete_expired_tokens(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        expired = [tid for tid, t in self._refresh_tokens.items() if t.expires_at < now]
        for tid in expired:
            del self._refresh_tokens[tid]
        return len(expired)
    
    def is_token_valid(self, token: str) -> bool:
        token_hash = hash_token(token)
        stored = self.get_refresh_token_by_hash(token_hash)
        if not stored:
            return False
        if stored.is_revoked:
            return False
        now = datetime.now(timezone.utc).isoformat()
        if stored.expires_at < now:
            return False
        return True
    
    def save_session(self, session: ActiveSession) -> None:
        self._sessions[session.session_id] = session
    
    def get_session_by_jti(self, jti: str) -> Optional[ActiveSession]:
        for session in self._sessions.values():
            if session.access_token_jti == jti:
                return session
        return None
    
    def get_user_sessions(self, user_id: str) -> List[ActiveSession]:
        return [s for s in self._sessions.values() if s.user_id == user_id and s.is_active]
    
    def deactivate_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            self._sessions[session_id].is_active = False
            return True
        return False
    
    def deactivate_session_by_jti(self, jti: str) -> bool:
        for session in self._sessions.values():
            if session.access_token_jti == jti:
                session.is_active = False
                return True
        return False
    
    def deactivate_all_user_sessions(self, user_id: str) -> int:
        count = 0
        for session in self._sessions.values():
            if session.user_id == user_id:
                session.is_active = False
                count += 1
        return count
    
    def update_session_activity(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id].last_activity = utc_now()


# Singleton instance
_token_repository: Optional[TokenRepository | InMemoryTokenRepository] = None


def get_token_repository() -> TokenRepository | InMemoryTokenRepository:
    """Get or create token repository singleton."""
    global _token_repository
    
    if _token_repository is None:
        db_backend = os.getenv("SOUNDROUTINE_DB_BACKEND", "memory")
        
        if db_backend in ("mongo", "mongodb"):
            mongo_uri = os.getenv(
                "SOUNDROUTINE_MONGO_URI",
                os.getenv("MONGO_URI", "mongodb://localhost:27017"),
            )
            mongo_db = os.getenv(
                "SOUNDROUTINE_MONGO_DB",
                os.getenv("MONGO_DB", "soundroutine"),
            )
            _token_repository = TokenRepository(mongo_uri, mongo_db)
        else:
            _token_repository = InMemoryTokenRepository()
    
    return _token_repository
