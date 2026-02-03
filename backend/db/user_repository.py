"""User repository for authentication data persistence."""

from __future__ import annotations

import os
from typing import Optional

from ..auth.models import User


class UserRepository:
    """MongoDB repository for user data."""
    
    def __init__(self, uri: str, db_name: str, collection: str = "users") -> None:
        from pymongo import MongoClient
        
        self._client = MongoClient(uri)
        self._db = self._client[db_name]
        self._col = self._db[collection]
        
        # Create indexes
        try:
            self._col.create_index("user_id", unique=True)
            self._col.create_index("email", unique=True)
        except Exception:
            pass
    
    def save(self, user: User) -> None:
        """Save or update a user."""
        doc = user.to_dict()
        doc["_id"] = user.user_id
        self._col.replace_one({"_id": user.user_id}, doc, upsert=True)
    
    def get_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        doc = self._col.find_one({"_id": user_id})
        if not doc:
            doc = self._col.find_one({"user_id": user_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return User.from_dict(doc)
    
    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        doc = self._col.find_one({"email": email})
        if not doc:
            return None
        doc.pop("_id", None)
        return User.from_dict(doc)
    
    def delete(self, user_id: str) -> bool:
        """Delete a user."""
        result = self._col.delete_one({"_id": user_id})
        return result.deleted_count > 0


class InMemoryUserRepository:
    """In-memory repository for development/testing."""
    
    def __init__(self) -> None:
        self._store: dict[str, User] = {}
    
    def save(self, user: User) -> None:
        self._store[user.user_id] = user
    
    def get_by_id(self, user_id: str) -> Optional[User]:
        return self._store.get(user_id)
    
    def get_by_email(self, email: str) -> Optional[User]:
        for user in self._store.values():
            if user.email == email:
                return user
        return None
    
    def delete(self, user_id: str) -> bool:
        if user_id in self._store:
            del self._store[user_id]
            return True
        return False


# Singleton instance
_user_repository: Optional[UserRepository | InMemoryUserRepository] = None


def get_user_repository() -> UserRepository | InMemoryUserRepository:
    """Get or create user repository singleton."""
    global _user_repository
    
    if _user_repository is None:
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
            _user_repository = UserRepository(mongo_uri, mongo_db)
        else:
            _user_repository = InMemoryUserRepository()
    
    return _user_repository
