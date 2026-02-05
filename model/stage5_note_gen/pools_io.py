from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_pools_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def role_to_pool_key(role: str) -> str:
    role = role.upper()
    if role == "CORE":
        return "CORE_POOL"
    if role == "ACCENT":
        return "ACCENT_POOL"
    if role == "MOTION":
        return "MOTION_POOL"
    if role == "FILL":
        return "FILL_POOL"
    if role == "TEXTURE":
        return "TEXTURE_POOL"
    return "FILL_POOL"


def extract_sample_ids_for_role(pools: Dict[str, Any], role: str) -> List[str]:
    key = role_to_pool_key(role)
    arr = pools.get(key, [])
    out: List[str] = []
    if isinstance(arr, list):
        for x in arr:
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, dict) and "sample_id" in x:
                out.append(str(x["sample_id"]))
    return out