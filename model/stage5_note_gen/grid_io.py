from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .types import Grid


def load_grid_json(path: str | Path) -> Grid:
    p = Path(path)
    d: Dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))

    meter = d.get("meter", "4/4")
    numer, denom = meter.split("/")
    numer_i = int(numer)
    denom_i = int(denom)

    t_step = d["t_step"]
    if not isinstance(t_step, list) or not t_step or not isinstance(t_step[0], list):
        raise ValueError("grid_json.t_step must be 2D list [bar][step]")

    return Grid(
        bpm=float(d["bpm"]),
        meter_numer=numer_i,
        meter_denom=denom_i,
        steps_per_bar=int(d["steps_per_bar"]),
        num_bars=int(d["num_bars"]),
        tbeat=float(d["tbeat"]),
        tbar=float(d["tbar"]),
        tstep=float(d["tstep"]),
        bar_start=[float(x) for x in d["bar_start"]],
        t_step=[[float(x) for x in row] for row in t_step],
    )


def build_repeated_grid(base: Grid, repeat_bars: int) -> Grid:
    if repeat_bars <= 0:
        raise ValueError("repeat_bars must be > 0")

    # base grid의 step spacing 유지하면서 bar_start/t_step을 늘려서 새 grid 생성
    num_bars = repeat_bars
    bar_start: List[float] = [b * base.tbar for b in range(num_bars)]
    t_step: List[List[float]] = []
    for b in range(num_bars):
        row = [bar_start[b] + k * base.tstep for k in range(base.steps_per_bar)]
        t_step.append(row)

    return Grid(
        bpm=base.bpm,
        meter_numer=base.meter_numer,
        meter_denom=base.meter_denom,
        steps_per_bar=base.steps_per_bar,
        num_bars=num_bars,
        tbeat=base.tbeat,
        tbar=base.tbar,
        tstep=base.tstep,
        bar_start=bar_start,
        t_step=t_step,
    )


def dump_grid_json(grid: Grid) -> Dict[str, Any]:
    return {
        "bpm": grid.bpm,
        "meter": f"{grid.meter_numer}/{grid.meter_denom}",
        "steps_per_bar": grid.steps_per_bar,
        "num_bars": grid.num_bars,
        "tbeat": grid.tbeat,
        "tbar": grid.tbar,
        "tstep": grid.tstep,
        "bar_start": grid.bar_start,
        "t_step": grid.t_step,
    }