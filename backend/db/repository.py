"""
SoundRoutine MongoDB Repositories
사용자, 사운드, 프로젝트 데이터 관리
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Dict, Any

from .models import User, Sound, Project, generate_id, utc_now

# MongoDB 연결 설정
MONGO_URI = os.getenv(
    "SOUNDROUTINE_MONGO_URI",
    "mongodb+srv://Madcamp_4W:Madcamp_4W@cluster0.uz3jpef.mongodb.net/?appName=Cluster0"
)
MONGO_DB = os.getenv("SOUNDROUTINE_MONGO_DB", "soundroutine")

# 파일 저장 경로
UPLOAD_ROOT = Path(os.getenv("SOUNDROUTINE_UPLOAD_ROOT", "uploads"))
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


def get_mongo_client():
    """MongoDB 클라이언트 반환"""
    try:
        from pymongo import MongoClient
        import certifi
        
        # TLS 인증서 경로 설정
        client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
            tls=True,
            tlsCAFile=certifi.where(),
        )
        # 연결 테스트
        client.admin.command('ping')
        return client
    except ImportError:
        # certifi가 없으면 기본 설정으로 시도
        try:
            from pymongo import MongoClient
            client = MongoClient(
                MONGO_URI,
                serverSelectionTimeoutMS=5000,
                tlsAllowInvalidCertificates=True,
            )
            client.admin.command('ping')
            return client
        except Exception as e:
            print(f"[MongoDB] Connection failed: {e}")
            return None
    except Exception as e:
        print(f"[MongoDB] Connection failed: {e}")
        return None


def get_database():
    """데이터베이스 반환"""
    client = get_mongo_client()
    if client:
        return client[MONGO_DB]
    return None


# ============================================================================
# User Repository
# ============================================================================
class UserRepository(ABC):
    @abstractmethod
    def save(self, user: User) -> User:
        pass
    
    @abstractmethod
    def get_by_id(self, user_id: str) -> Optional[User]:
        pass
    
    @abstractmethod
    def get_by_google_id(self, google_id: str) -> Optional[User]:
        pass
    
    @abstractmethod
    def update_last_login(self, user_id: str) -> None:
        pass


class MongoUserRepository(UserRepository):
    """MongoDB 사용자 Repository"""
    
    def __init__(self):
        self.db = get_database()
        if self.db is not None:
            self.collection = self.db["users"]
            # 인덱스 생성
            self.collection.create_index("google_id", unique=True)
            self.collection.create_index("email")
    
    def save(self, user: User) -> User:
        if self.db is None:
            raise ConnectionError("MongoDB not connected")
        
        data = user.to_dict()
        self.collection.update_one(
            {"user_id": user.user_id},
            {"$set": data},
            upsert=True
        )
        return user
    
    def get_by_id(self, user_id: str) -> Optional[User]:
        if self.db is None:
            return None
        
        doc = self.collection.find_one({"user_id": user_id})
        return User.from_dict(doc) if doc else None
    
    def get_by_google_id(self, google_id: str) -> Optional[User]:
        if self.db is None:
            return None
        
        doc = self.collection.find_one({"google_id": google_id})
        return User.from_dict(doc) if doc else None
    
    def update_last_login(self, user_id: str) -> None:
        if self.db is None:
            return
        
        self.collection.update_one(
            {"user_id": user_id},
            {"$set": {"last_login": utc_now()}}
        )


class InMemoryUserRepository(UserRepository):
    """인메모리 사용자 Repository (테스트/개발용)"""
    
    def __init__(self):
        self._users: Dict[str, User] = {}
        self._google_index: Dict[str, str] = {}  # google_id -> user_id
    
    def save(self, user: User) -> User:
        self._users[user.user_id] = user
        self._google_index[user.google_id] = user.user_id
        return user
    
    def get_by_id(self, user_id: str) -> Optional[User]:
        return self._users.get(user_id)
    
    def get_by_google_id(self, google_id: str) -> Optional[User]:
        user_id = self._google_index.get(google_id)
        return self._users.get(user_id) if user_id else None
    
    def update_last_login(self, user_id: str) -> None:
        if user_id in self._users:
            self._users[user_id].last_login = utc_now()


# ============================================================================
# Sound Repository
# ============================================================================
class SoundRepository(ABC):
    @abstractmethod
    def save(self, sound: Sound) -> Sound:
        pass
    
    @abstractmethod
    def get(self, sound_id: str) -> Optional[Sound]:
        pass
    
    @abstractmethod
    def get_by_user(self, user_id: str, status: str = None) -> List[Sound]:
        pass
    
    @abstractmethod
    def delete(self, sound_id: str) -> bool:
        pass
    
    @abstractmethod
    def update_analysis(self, sound_id: str, analysis: Dict[str, Any]) -> bool:
        pass


class MongoSoundRepository(SoundRepository):
    """MongoDB 사운드 Repository"""
    
    def __init__(self):
        self.db = get_database()
        if self.db is not None:
            self.collection = self.db["sounds"]
            self.collection.create_index("user_id")
            self.collection.create_index("status")
    
    def save(self, sound: Sound) -> Sound:
        if self.db is None:
            raise ConnectionError("MongoDB not connected")
        
        data = sound.to_dict()
        self.collection.update_one(
            {"sound_id": sound.sound_id},
            {"$set": data},
            upsert=True
        )
        return sound
    
    def get(self, sound_id: str) -> Optional[Sound]:
        if self.db is None:
            return None
        
        doc = self.collection.find_one({"sound_id": sound_id})
        return Sound.from_dict(doc) if doc else None
    
    def get_by_user(self, user_id: str, status: str = None) -> List[Sound]:
        if self.db is None:
            return []
        
        query = {"user_id": user_id}
        if status:
            query["status"] = status
        
        docs = self.collection.find(query).sort("slot_index", 1)
        return [Sound.from_dict(doc) for doc in docs]
    
    def delete(self, sound_id: str) -> bool:
        if self.db is None:
            return False
        
        # 파일도 삭제
        sound = self.get(sound_id)
        if sound and sound.file_path:
            try:
                file_path = Path(sound.file_path)
                if file_path.exists():
                    file_path.unlink()
            except Exception as e:
                print(f"[Sound] Failed to delete file: {e}")
        
        result = self.collection.delete_one({"sound_id": sound_id})
        return result.deleted_count > 0
    
    def update_analysis(self, sound_id: str, analysis: Dict[str, Any]) -> bool:
        if self.db is None:
            return False
        
        result = self.collection.update_one(
            {"sound_id": sound_id},
            {"$set": {"analysis": analysis, "status": "validated"}}
        )
        return result.modified_count > 0


class InMemorySoundRepository(SoundRepository):
    """인메모리 사운드 Repository"""
    
    def __init__(self):
        self._sounds: Dict[str, Sound] = {}
    
    def save(self, sound: Sound) -> Sound:
        self._sounds[sound.sound_id] = sound
        return sound
    
    def get(self, sound_id: str) -> Optional[Sound]:
        return self._sounds.get(sound_id)
    
    def get_by_user(self, user_id: str, status: str = None) -> List[Sound]:
        sounds = [s for s in self._sounds.values() if s.user_id == user_id]
        if status:
            sounds = [s for s in sounds if s.status == status]
        return sorted(sounds, key=lambda s: s.slot_index)
    
    def delete(self, sound_id: str) -> bool:
        if sound_id in self._sounds:
            sound = self._sounds[sound_id]
            # 파일 삭제
            if sound.file_path:
                try:
                    file_path = Path(sound.file_path)
                    if file_path.exists():
                        file_path.unlink()
                except Exception:
                    pass
            del self._sounds[sound_id]
            return True
        return False
    
    def update_analysis(self, sound_id: str, analysis: Dict[str, Any]) -> bool:
        if sound_id in self._sounds:
            sound = self._sounds[sound_id]
            sound.analysis.role = analysis.get("role", sound.analysis.role)
            sound.status = "validated"
            return True
        return False


# ============================================================================
# Project Repository  
# ============================================================================
class ProjectRepository(ABC):
    @abstractmethod
    def save(self, project: Project) -> Project:
        pass
    
    @abstractmethod
    def get(self, project_id: str) -> Optional[Project]:
        pass
    
    @abstractmethod
    def get_by_user(self, user_id: str, limit: int = 50) -> List[Project]:
        pass
    
    @abstractmethod
    def delete(self, project_id: str) -> bool:
        pass
    
    @abstractmethod
    def update_sequence(self, project_id: str, sequence: Dict[str, Any]) -> bool:
        pass


class MongoProjectRepository(ProjectRepository):
    """MongoDB 프로젝트 Repository"""
    
    def __init__(self):
        self.db = get_database()
        if self.db is not None:
            self.collection = self.db["projects"]
            self.collection.create_index("user_id")
            self.collection.create_index("updated_at")
    
    def save(self, project: Project) -> Project:
        if self.db is None:
            raise ConnectionError("MongoDB not connected")
        
        project.updated_at = utc_now()
        data = project.to_dict()
        self.collection.update_one(
            {"project_id": project.project_id},
            {"$set": data},
            upsert=True
        )
        return project
    
    def get(self, project_id: str) -> Optional[Project]:
        if self.db is None:
            return None
        
        doc = self.collection.find_one({"project_id": project_id})
        return Project.from_dict(doc) if doc else None
    
    def get_by_user(self, user_id: str, limit: int = 50) -> List[Project]:
        if self.db is None:
            return []
        
        docs = self.collection.find({"user_id": user_id}).sort("updated_at", -1).limit(limit)
        return [Project.from_dict(doc) for doc in docs]
    
    def delete(self, project_id: str) -> bool:
        if self.db is None:
            return False
        
        # 출력 파일도 삭제
        project = self.get(project_id)
        if project and project.output_path:
            try:
                output_path = Path(project.output_path)
                if output_path.exists():
                    output_path.unlink()
            except Exception as e:
                print(f"[Project] Failed to delete output: {e}")
        
        result = self.collection.delete_one({"project_id": project_id})
        return result.deleted_count > 0
    
    def update_sequence(self, project_id: str, sequence: Dict[str, Any]) -> bool:
        if self.db is None:
            return False
        
        result = self.collection.update_one(
            {"project_id": project_id},
            {"$set": {"sequence": sequence, "updated_at": utc_now()}}
        )
        return result.modified_count > 0


class InMemoryProjectRepository(ProjectRepository):
    """인메모리 프로젝트 Repository"""
    
    def __init__(self):
        self._projects: Dict[str, Project] = {}
    
    def save(self, project: Project) -> Project:
        project.updated_at = utc_now()
        self._projects[project.project_id] = project
        return project
    
    def get(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)
    
    def get_by_user(self, user_id: str, limit: int = 50) -> List[Project]:
        projects = [p for p in self._projects.values() if p.user_id == user_id]
        projects.sort(key=lambda p: p.updated_at, reverse=True)
        return projects[:limit]
    
    def delete(self, project_id: str) -> bool:
        if project_id in self._projects:
            project = self._projects[project_id]
            if project.output_path:
                try:
                    output_path = Path(project.output_path)
                    if output_path.exists():
                        output_path.unlink()
                except Exception:
                    pass
            del self._projects[project_id]
            return True
        return False
    
    def update_sequence(self, project_id: str, sequence: Dict[str, Any]) -> bool:
        if project_id in self._projects:
            from .models import Sequence
            self._projects[project_id].sequence = Sequence.from_dict(sequence)
            self._projects[project_id].updated_at = utc_now()
            return True
        return False


# ============================================================================
# Repository Factory
# ============================================================================
_user_repo: Optional[UserRepository] = None
_sound_repo: Optional[SoundRepository] = None
_project_repo: Optional[ProjectRepository] = None


def get_user_repository() -> UserRepository:
    """사용자 Repository 반환"""
    global _user_repo
    
    if _user_repo is None:
        backend = os.getenv("SOUNDROUTINE_DB_BACKEND", "mongo")
        if backend == "memory":
            _user_repo = InMemoryUserRepository()
            print("[DB] Using InMemory UserRepository")
        else:
            try:
                _user_repo = MongoUserRepository()
                print("[DB] Using MongoDB UserRepository")
            except Exception as e:
                print(f"[DB] MongoDB failed, using InMemory: {e}")
                _user_repo = InMemoryUserRepository()
    
    return _user_repo


def get_sound_repository() -> SoundRepository:
    """사운드 Repository 반환"""
    global _sound_repo
    
    if _sound_repo is None:
        backend = os.getenv("SOUNDROUTINE_DB_BACKEND", "mongo")
        if backend == "memory":
            _sound_repo = InMemorySoundRepository()
            print("[DB] Using InMemory SoundRepository")
        else:
            try:
                _sound_repo = MongoSoundRepository()
                print("[DB] Using MongoDB SoundRepository")
            except Exception as e:
                print(f"[DB] MongoDB failed, using InMemory: {e}")
                _sound_repo = InMemorySoundRepository()
    
    return _sound_repo


def get_project_repository() -> ProjectRepository:
    """프로젝트 Repository 반환"""
    global _project_repo
    
    if _project_repo is None:
        backend = os.getenv("SOUNDROUTINE_DB_BACKEND", "mongo")
        if backend == "memory":
            _project_repo = InMemoryProjectRepository()
            print("[DB] Using InMemory ProjectRepository")
        else:
            try:
                _project_repo = MongoProjectRepository()
                print("[DB] Using MongoDB ProjectRepository")
            except Exception as e:
                print(f"[DB] MongoDB failed, using InMemory: {e}")
                _project_repo = InMemoryProjectRepository()
    
    return _project_repo
