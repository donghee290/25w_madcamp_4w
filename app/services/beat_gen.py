from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from stage3_beat_grid.grid import GridConfig, build_grid
from stage3_beat_grid.patterns.skeleton import SkeletonConfig, build_skeleton_events


def _jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if is_dataclass(obj):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "value"):
        try:
            return _jsonable(obj.value)
        except Exception:
            return str(obj)
    try:
        import numpy as np
        if isinstance(obj, (np.integer, np.floating)):
            return obj.item()
    except Exception:
        pass
    return obj


def _event_to_dict(e: Any) -> Dict[str, Any]:
    if isinstance(e, dict):
        d = dict(e)
    elif is_dataclass(e):
        d = asdict(e)
    else:
        d = {}
        for k in ["bar", "step", "role", "sample_id", "vel", "dur_steps", "micro_offset_ms", "source", "filepath"]:
            if hasattr(e, k):
                d[k] = getattr(e, k)

    role = d.get("role", None)
    if role is not None and hasattr(role, "value"):
        try:
            d["role"] = role.value
        except Exception:
            d["role"] = str(role)

    d.setdefault("micro_offset_ms", 0.0)
    d.setdefault("source", "skeleton")

    if "bar" in d:
        d["bar"] = int(d["bar"])
    if "step" in d:
        d["step"] = int(d["step"])
    if "vel" in d:
        d["vel"] = float(d["vel"])
    if "dur_steps" in d:
        d["dur_steps"] = int(d["dur_steps"])
    if "micro_offset_ms" in d:
        d["micro_offset_ms"] = float(d["micro_offset_ms"])

    if "sample_id" in d and d["sample_id"] is not None:
        d["sample_id"] = str(d["sample_id"])
    if "filepath" in d and d["filepath"] is not None:
        d["filepath"] = str(d["filepath"])

    return _jsonable(d)


def generate_basic_beat(
    pools_json: Dict[str, Any],
    bpm: float,
    bars: int = 4,
    seed: int = 42,
    motion_mode: str = "B",
    motion_keep: int = 6,
    fill_prob: float = 0.25,
    texture_enabled: bool = True,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    gcfg = GridConfig(
        bpm=float(bpm),
        num_bars=int(bars),
        steps_per_bar=16,
        meter_numer=4,
        meter_denom=4,
    )
    grid = build_grid(gcfg)

    grid_json = {
        "bpm": float(grid.cfg.bpm),
        "meter": f"{int(grid.cfg.meter_numer)}/{int(grid.cfg.meter_denom)}",
        "steps_per_bar": int(grid.cfg.steps_per_bar),
        "num_bars": int(grid.cfg.num_bars),
        "tbeat": float(grid.tbeat),
        "tbar": float(grid.tbar),
        "tstep": float(grid.tstep),
        "bar_start": _jsonable(grid.bar_start),
        "t_step": _jsonable(grid.t_step),
    }

    scfg = SkeletonConfig(
        seed=int(seed),
        steps_per_bar=16,
        num_bars=int(bars),
        motion_mode=str(motion_mode),
        motion_keep_per_bar=int(motion_keep),
        fill_prob=float(fill_prob),
        texture_enabled=bool(texture_enabled),
    )

    events, chosen = build_skeleton_events(
        pools_json,
        scfg,
        tstep=grid.tstep,
    )

    events_json = [_event_to_dict(e) for e in events]
    return grid_json, events_json, _jsonable(chosen)
