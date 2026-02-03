from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any, List


@dataclass
class Grid:
    bpm: float
    meter_numer: int
    meter_denom: int
    steps_per_bar: int
    num_bars: int
    tbeat: float
    tbar: float
    tstep: float
    bar_start: List[float]
    t_step: List[List[float]]  # [bar][step]


@dataclass
class Event:
    bar: int
    step: int
    role: str                 # CORE/ACCENT/MOTION/FILL/TEXTURE
    sample_id: str
    vel: float                # 0..1
    dur_steps: int            # >=1
    micro_offset_ms: float    # ms
    source: str               # "model" | "skeleton" | ...
    extra: Optional[Dict[str, Any]] = None