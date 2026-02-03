from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from .types import Grid, Event
from .sample_select import SampleSelector


def load_note_list_json(path: str | Path) -> List[Dict[str, Any]]:
    p = Path(path)
    x = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x, list):
        raise ValueError("notes_json must be a list")
    return x


def map_note_role_to_internal(role: str) -> str:
    r = str(role).lower().strip()
    if r in ["kick", "bd", "bassdrum"]:
        return "CORE"
    if r in ["snare", "sd", "clap"]:
        return "ACCENT"
    if r in ["hat", "hihat", "chh", "ohh", "hh"]:
        return "MOTION"
    if r in ["tom", "toms", "perc", "percussion", "rim"]:
        return "FILL"
    if r in ["texture", "noise", "amb", "ambience"]:
        return "TEXTURE"
    return "FILL"


def nearest_step(grid: Grid, t: float) -> Tuple[int, int, float]:
    # 전체 grid에서 가장 가까운 (bar, step) 찾기
    best_b = 0
    best_k = 0
    best_dt = 1e9
    for b in range(grid.num_bars):
        row = grid.t_step[b]
        for k in range(grid.steps_per_bar):
            dt = abs(t - row[k])
            if dt < best_dt:
                best_dt = dt
                best_b, best_k = b, k
    snapped_time = grid.t_step[best_b][best_k]
    return best_b, best_k, snapped_time


def dur_steps_from_times(grid: Grid, start: float, end: float) -> int:
    dur = max(float(end) - float(start), 0.0)
    steps = int(round(dur / grid.tstep))
    return max(1, min(steps, grid.steps_per_bar))


def normalize_notes_to_event_grid(
    grid: Grid,
    notes: List[Dict[str, Any]],
    selector: SampleSelector,
    source: str = "model",
    clamp_ms: float = 40.0,
) -> List[Event]:
    out: List[Event] = []
    for n in notes:
        start = float(n.get("start", 0.0))
        end = float(n.get("end", start + grid.tstep))
        velocity = float(n.get("velocity", 80.0))
        role_in = n.get("role", "perc")

        role = map_note_role_to_internal(str(role_in))

        # 1) UI용 스냅(bar, step)은 start 기준으로 계산
        b, k, snapped = nearest_step(grid, start)

        # 2) micro_offset_ms는 "입력에 있으면 그대로" 우선 사용
        if "micro_offset_ms" in n and n["micro_offset_ms"] is not None:
            micro_ms = float(n["micro_offset_ms"])
        else:
            micro_ms = (start - snapped) * 1000.0

        # 3) clamp (원치 않으면 clamp_ms를 None으로 운영)
        if clamp_ms is not None:
            if micro_ms > clamp_ms:
                micro_ms = clamp_ms
            elif micro_ms < -clamp_ms:
                micro_ms = -clamp_ms

        vel01 = max(0.0, min(1.0, velocity / 127.0))
        dur_steps = dur_steps_from_times(grid, start, end)

        sid = selector.pick(role)

        out.append(
            Event(
                bar=int(b),
                step=int(k),
                role=role,
                sample_id=sid,
                vel=float(vel01),
                dur_steps=int(dur_steps),
                micro_offset_ms=float(micro_ms),
                source=str(source),
                extra={
                    "pitch": n.get("pitch"),
                    "is_drum": n.get("is_drum"),
                    "raw_role": role_in,
                    "raw_offset": n.get("offset", 0),
                    "raw_start": start,
                    "raw_end": end,
                    "raw_micro_offset_ms": n.get("micro_offset_ms", None),
                },
            )
        )

    out.sort(key=lambda e: (e.bar, e.step))
    return out


def dump_event_grid(events: List[Event]) -> List[Dict[str, Any]]:
    arr: List[Dict[str, Any]] = []
    for e in events:
        arr.append(
            {
                "bar": e.bar,
                "step": e.step,
                "role": e.role,
                "sample_id": e.sample_id,
                "vel": e.vel,
                "dur_steps": e.dur_steps,
                "micro_offset_ms": e.micro_offset_ms,
                "source": e.source,
            }
        )
    return arr