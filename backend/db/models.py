from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class JobRecord:
    job_id: str
    status: str
    created_at: str
    input_meta: Dict[str, Any]
    output_meta: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
