import time
import uuid
import threading
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class JobInfo:
    job_id: str
    project_name: str
    status: str  # "running", "completed", "failed"
    progress: str  # e.g., "Step 3/7"
    result: Optional[Dict] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)

class JobManager:
    def __init__(self):
        self._jobs: Dict[str, JobInfo] = {}
        self._job_lock = threading.Lock()

    def start_job(self, func, *args, **kwargs) -> str:
        """Starts a background thread for the given function and returns a job_id."""
        job_id = str(uuid.uuid4())
        beat_name = kwargs.get("project_name") or kwargs.get("beat_name") or "unknown"

        with self._job_lock:
            self._jobs[job_id] = JobInfo(
                job_id=job_id,
                project_name=beat_name,
                status="running",
                progress="Starting...",
            )

        def wrapper():
            try:
                # Execute the function
                res = func(*args, **kwargs)
                with self._job_lock:
                    job = self._jobs[job_id]
                    job.status = "completed"
                    job.progress = "Done"
                    job.result = res
            except Exception as e:
                logger.exception(f"Job {job_id} failed: {e}")
                with self._job_lock:
                    job = self._jobs[job_id]
                    job.status = "failed"
                    job.error = str(e)

        t = threading.Thread(target=wrapper, daemon=True)
        t.start()
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict]:
        with self._job_lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return {
                "job_id": job.job_id,
                "beat_name": job.project_name, 
                "status": job.status,
                "progress": job.progress,
                "result": job.result,
                "error": job.error,
                "created_at": job.created_at,
            }

    def update_job_progress(self, beat_name: str, progress: str):
        # Find active job for this project
        with self._job_lock:
            for job in self._jobs.values():
                if job.project_name == beat_name and job.status == "running":
                    job.progress = progress
