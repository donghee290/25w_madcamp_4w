# beat_grid/events.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import random


ROLES = ("CORE", "ACCENT", "MOTION", "FILL", "TEXTURE")


@dataclass
class Event:
    bar: int
    step: int
    role: str                 # CORE/ACCENT/MOTION/FILL/TEXTURE
    sample_id: str
    vel: float                # 0..1
    dur_steps: int            # 1..steps_per_bar
    micro_offset_ms: float = 0.0
    source: str = "skeleton"  # skeleton | groove | user_edit 등


def clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def vel_from_energy(role: str, energy: Optional[float], rng: Optional[random.Random] = None) -> float:
    e = float(energy) if energy is not None else 0.5

    if role == "CORE":
        return clamp01(0.60 + 0.40 * e)
    if role == "ACCENT":
        return clamp01(0.70 + 0.30 * e)
    if role == "MOTION":
        return clamp01(0.25 + 0.35 * e)
    if role == "FILL":
        return clamp01(0.75 + 0.25 * e)
    if role == "TEXTURE":
        # Randomize if rng provided, otherwise use fixed
        if rng:
            return clamp01(rng.uniform(0.15, 0.35))
        return clamp01(0.25)
    return clamp01(0.5)


def dur_from_decay(decay_sec: float, tstep: float, role: str) -> int:
    if role == "TEXTURE":
        return 16  # Texture is long

    # If decay is significantly longer than 1 step, let it be 2 steps
    if decay_sec is not None and tstep > 0:
        if float(decay_sec) > float(tstep) * 0.95:
            return 2
    return 1