from __future__ import annotations
from typing import Dict, Any

def playback_time(grid: Dict[str, Any], ev: Dict[str, Any]) -> float:
    """
    재생 시간: grid 스텝 기준 시간 + micro_offset_ms
    """
    bar = int(ev["bar"])
    step = int(ev["step"])
    base = float(grid["t_step"][bar][step])
    micro_ms = float(ev.get("micro_offset_ms", 0.0) or 0.0)
    return base + micro_ms / 1000.0