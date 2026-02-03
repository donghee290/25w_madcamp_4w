from __future__ import annotations
from typing import Dict, Any, Tuple

def step_time(grid: Dict[str, Any], bar: int, step: int) -> float:
    # grid_json: t_step[bar][step]
    return float(grid["t_step"][bar][step])

def ui_snap_info(grid: Dict[str, Any], ev: Dict[str, Any]) -> Dict[str, Any]:
    # UI 표시는 bar/step 그대로
    bar = int(ev["bar"])
    step = int(ev["step"])
    snapped = step_time(grid, bar, step)

    return {
        "ui_bar": bar,
        "ui_step": step,
        "ui_time_sec": snapped,
    }