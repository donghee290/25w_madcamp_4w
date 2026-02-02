from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Dict, Optional

from .models import JobRecord


class Repository(ABC):
    @abstractmethod
    def save(self, record: JobRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, job_id: str) -> Optional[JobRecord]:
        raise NotImplementedError

    @abstractmethod
    def list(self, limit: int = 20) -> list[JobRecord]:
        raise NotImplementedError


class InMemoryRepository(Repository):
    def __init__(self) -> None:
        self._store: Dict[str, JobRecord] = {}

    def save(self, record: JobRecord) -> None:
        self._store[record.job_id] = record

    def get(self, job_id: str) -> Optional[JobRecord]:
        return self._store.get(job_id)

    def list(self, limit: int = 20) -> list[JobRecord]:
        records = list(self._store.values())
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]


class DjangoDbRepository(Repository):
    """
    Placeholder for NoSQL backend.
    Replace with DjangoDB client implementation once the engine is confirmed.
    """

    def save(self, record: JobRecord) -> None:
        raise NotImplementedError("DjangoDB backend is not configured yet.")

    def get(self, job_id: str) -> Optional[JobRecord]:
        raise NotImplementedError("DjangoDB backend is not configured yet.")

    def list(self, limit: int = 20) -> list[JobRecord]:
        raise NotImplementedError("DjangoDB backend is not configured yet.")


class MongoRepository(Repository):
    def __init__(self, uri: str, db_name: str, collection: str) -> None:
        from pymongo import MongoClient  # lazy import

        self._client = MongoClient(uri)
        self._db = self._client[db_name]
        self._col = self._db[collection]
        try:
            self._col.create_index("job_id", unique=True)
        except Exception:
            pass

    def save(self, record: JobRecord) -> None:
        doc = asdict(record)
        doc["_id"] = record.job_id
        self._col.replace_one({"_id": record.job_id}, doc, upsert=True)

    def get(self, job_id: str) -> Optional[JobRecord]:
        doc = self._col.find_one({"_id": job_id})
        if not doc:
            doc = self._col.find_one({"job_id": job_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return JobRecord(**doc)

    def list(self, limit: int = 20) -> list[JobRecord]:
        cursor = (
            self._col.find({}, {"_id": 0})
            .sort("created_at", -1)
            .limit(int(limit))
        )
        return [JobRecord(**doc) for doc in cursor]


def build_repository(
    backend: str,
    mongo_uri: Optional[str] = None,
    mongo_db: Optional[str] = None,
    mongo_collection: Optional[str] = None,
) -> Repository:
    if backend == "memory":
        return InMemoryRepository()
    if backend == "django":
        return DjangoDbRepository()
    if backend in ("mongo", "mongodb"):
        if not mongo_uri or not mongo_db or not mongo_collection:
            raise ValueError("MongoDB config missing: uri/db/collection required")
        return MongoRepository(mongo_uri, mongo_db, mongo_collection)
    raise ValueError(f"Unknown db backend: {backend}")
