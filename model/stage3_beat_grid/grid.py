# beat_grid/grid.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class GridConfig:
    bpm: float
    meter_numer: int = 4          # 4/4
    meter_denom: int = 4
    steps_per_bar: int = 16       # 16-step
    num_bars: int = 4             # MVP 기본 4 bar


@dataclass(frozen=True)
class GridTime:
    cfg: GridConfig
    tbeat: float
    tbar: float
    tstep: float
    bar_start: List[float]
    t_step: List[List[float]]  # [bar][step] -> time(sec)


def build_grid(cfg: GridConfig) -> GridTime:
    if cfg.bpm <= 0:
        raise ValueError("bpm must be > 0")

    # 4/4 고정 MVP: 한 박 = quarter note
    tbeat = 60.0 / float(cfg.bpm)
    tbar = float(cfg.meter_numer) * tbeat
    tstep = tbar / float(cfg.steps_per_bar)

    bar_start = [b * tbar for b in range(cfg.num_bars)]
    t_step: List[List[float]] = []
    for b in range(cfg.num_bars):
        row = []
        base = bar_start[b]
        for k in range(cfg.steps_per_bar):
            row.append(base + k * tstep)
        t_step.append(row)

    return GridTime(
        cfg=cfg,
        tbeat=tbeat,
        tbar=tbar,
        tstep=tstep,
        bar_start=bar_start,
        t_step=t_step,
    )