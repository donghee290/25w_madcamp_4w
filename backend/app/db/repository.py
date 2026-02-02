from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import get_db


def save_job(job_id: str, request_data: Dict[str, Any], result_data: Dict[str, Any]) -> Dict[str, Any]:
    """비트 생성 작업 결과를 저장한다."""
    doc = {
        "_id": job_id,
        "job_id": job_id,
        "status": "completed",
        "request": {
            "bpm": request_data.get("bpm"),
            "bars": request_data.get("bars"),
            "filename": request_data.get("filename"),
        },
        "result": {
            "audio_url": result_data.get("audio_url"),
            "grid": result_data.get("grid"),
            "events_count": len(result_data.get("events", [])),
            "events": result_data.get("events"),
        },
        "created_at": datetime.now(timezone.utc),
    }
    get_db().jobs.insert_one(doc)
    return doc


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """job_id로 작업 결과를 조회한다."""
    return get_db().jobs.find_one({"_id": job_id})


def list_jobs(limit: int = 20) -> list:
    """최근 작업 목록을 반환한다."""
    cursor = get_db().jobs.find(
        {}, {"result.events": 0}  # events는 양이 많으므로 목록에서 제외
    ).sort("created_at", -1).limit(limit)
    return list(cursor)
