"""
Beat Project Repository
MongoDB에 비트 프로젝트 저장/조회
"""

from __future__ import annotations

import os
from typing import List, Optional

from .models import BeatProject


class BeatProjectRepository:
    """MongoDB 기반 비트 프로젝트 저장소"""
    
    def __init__(self, uri: str, db_name: str, collection: str = "beat_projects") -> None:
        from pymongo import MongoClient
        
        self._client = MongoClient(uri)
        self._db = self._client[db_name]
        self._col = self._db[collection]
        
        # 인덱스 생성
        try:
            self._col.create_index("project_id", unique=True)
            self._col.create_index("user_id")
            self._col.create_index([("user_id", 1), ("created_at", -1)])
        except Exception:
            pass
    
    def save(self, project: BeatProject) -> None:
        """프로젝트 저장 (upsert)"""
        doc = project.to_dict()
        doc["_id"] = project.project_id
        self._col.replace_one({"_id": project.project_id}, doc, upsert=True)
    
    def get(self, project_id: str) -> Optional[BeatProject]:
        """프로젝트 ID로 조회"""
        doc = self._col.find_one({"_id": project_id})
        if not doc:
            doc = self._col.find_one({"project_id": project_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return BeatProject.from_dict(doc)
    
    def get_by_user(self, user_id: str, limit: int = 50) -> List[BeatProject]:
        """사용자별 프로젝트 목록 조회 (최신순)"""
        cursor = (
            self._col.find({"user_id": user_id}, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
        )
        return [BeatProject.from_dict(doc) for doc in cursor]
    
    def delete(self, project_id: str) -> bool:
        """프로젝트 삭제"""
        result = self._col.delete_one({"project_id": project_id})
        return result.deleted_count > 0
    
    def update_json_files(self, project_id: str, json_files: dict) -> bool:
        """JSON 파일 경로 업데이트"""
        from datetime import datetime, timezone
        result = self._col.update_one(
            {"project_id": project_id},
            {
                "$set": {
                    "json_files": json_files,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            }
        )
        return result.modified_count > 0
    
    def update_status(self, project_id: str, status: str) -> bool:
        """상태 업데이트"""
        from datetime import datetime, timezone
        result = self._col.update_one(
            {"project_id": project_id},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            }
        )
        return result.modified_count > 0


class InMemoryBeatProjectRepository:
    """개발/테스트용 인메모리 저장소"""
    
    def __init__(self) -> None:
        self._store: dict[str, BeatProject] = {}
    
    def save(self, project: BeatProject) -> None:
        self._store[project.project_id] = project
    
    def get(self, project_id: str) -> Optional[BeatProject]:
        return self._store.get(project_id)
    
    def get_by_user(self, user_id: str, limit: int = 50) -> List[BeatProject]:
        projects = [p for p in self._store.values() if p.user_id == user_id]
        projects.sort(key=lambda x: x.created_at, reverse=True)
        return projects[:limit]
    
    def delete(self, project_id: str) -> bool:
        if project_id in self._store:
            del self._store[project_id]
            return True
        return False
    
    def update_json_files(self, project_id: str, json_files: dict) -> bool:
        if project_id in self._store:
            self._store[project_id].json_files = json_files
            return True
        return False
    
    def update_status(self, project_id: str, status: str) -> bool:
        if project_id in self._store:
            self._store[project_id].status = status
            return True
        return False


# 싱글톤 인스턴스
_beat_project_repo: Optional[BeatProjectRepository | InMemoryBeatProjectRepository] = None


def get_beat_project_repository() -> BeatProjectRepository | InMemoryBeatProjectRepository:
    """비트 프로젝트 저장소 싱글톤 반환"""
    global _beat_project_repo
    
    if _beat_project_repo is None:
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
            _beat_project_repo = BeatProjectRepository(mongo_uri, mongo_db)
        else:
            _beat_project_repo = InMemoryBeatProjectRepository()
    
    return _beat_project_repo
