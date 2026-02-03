# stage5_note_gen/normalize.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
    if r in ["core", "kick", "bd", "bassdrum"]:
        return "CORE"
    if r in ["accent", "snare", "sd", "clap"]:
        return "ACCENT"
    if r in ["motion", "hat", "hihat", "chh", "ohh", "hh", "ride"]:
        return "MOTION"
    if r in ["fill", "tom", "toms", "perc", "percussion", "rim"]:
        return "FILL"
    if r in ["texture", "noise", "amb", "ambience"]:
        return "TEXTURE"
    return "FILL"


def nearest_step_local(grid: Grid, t: float) -> Tuple[int, int, float]:
    """
    start time으로 bar를 먼저 고정하고, 해당 bar 내부에서만 nearest step을 찾습니다.
    (bar 경계에서 다른 bar로 스냅되는 문제 방지)
    """
    # bar clamp
    b = int(t // grid.tbar) if grid.tbar > 0 else 0
    if b < 0:
        b = 0
    elif b >= grid.num_bars:
        b = grid.num_bars - 1

    row = grid.t_step[b]
    best_k = 0
    best_dt = 1e18
    for k in range(grid.steps_per_bar):
        dt = abs(t - row[k])
        if dt < best_dt:
            best_dt = dt
            best_k = k

    snapped_time = row[best_k]
    return b, best_k, snapped_time


def dur_steps_from_times(grid: Grid, start: float, end: float) -> int:
    dur = max(float(end) - float(start), 0.0)
    steps = int(round(dur / grid.tstep)) if grid.tstep > 0 else 1
    return max(1, min(steps, grid.steps_per_bar))


def _wrap_bar_step(grid: Grid, b: int, k: int) -> Tuple[int, int]:
    """
    step 이동 보정 시 bar/step을 정상 범위로 맞춥니다.
    grid.num_bars 밖으로 나가면 끝 bar에 clamp합니다(무한 반복 방지).
    """
    if k >= grid.steps_per_bar:
        k = 0
        b += 1
    elif k < 0:
        k = grid.steps_per_bar - 1
        b -= 1

    if b < 0:
        b = 0
    elif b >= grid.num_bars:
        b = grid.num_bars - 1

    return b, k


def normalize_notes_to_event_grid(
    grid: Grid,
    notes: List[Dict[str, Any]],
    selector: SampleSelector,
    source: str = "model",
    clamp_ms: float | None = 40.0,
    trust_input_micro_offset: bool = True,
) -> List[Event]:
    """
    notes(start/end/velocity/role/optional micro_offset_ms)를 EventGrid로 정규화합니다.

    핵심 안정화:
    - bar를 먼저 고정한 local snap(nearest_step_local)
    - micro_offset_ms가 half-step을 넘으면 step 자체를 이동시키고 offset 재계산
    - (선택) 입력 micro_offset_ms는 half-step 이내일 때만 신뢰
    - 마지막에 clamp_ms 적용
    """
    out: List[Event] = []

    half_step_ms = (grid.tstep * 0.5) * 1000.0 if grid.tstep > 0 else 0.0

    for n in notes:
        # Decision-based logic (Stage 4 Output)
        if "bar" in n and "step" in n:
            b = int(n["bar"])
            k = int(n["step"])
            # Validate against grid
            b = max(0, min(b, grid.num_bars - 1))
            k = max(0, min(k, grid.steps_per_bar - 1))
            
            snapped = grid.t_step[b][k]
            start = snapped
            end = snapped + (grid.tstep if grid.tstep > 0 else 0) # Fallback duration
            
            intensity = float(n.get("intensity", 0.8))
            velocity = intensity * 127.0 # Back to legacy if needed or use intensity directly
        else:
            # Legacy Time-based logic
            start = float(n.get("start", 0.0))
            end = float(n.get("end", start + (grid.tstep if grid.tstep > 0 else 0.0)))
            velocity = float(n.get("velocity", 80.0))
            
            # 1) local snap
            b, k, snapped = nearest_step_local(grid, start)

        role_in = n.get("role", "perc")
        role = map_note_role_to_internal(str(role_in))

        # 2) micro offset: REMOVED per user request
        micro_ms = 0.0

        # 5) 저장 직전 방어
        b = max(0, min(int(b), grid.num_bars - 1))
        k = int(k) % grid.steps_per_bar

        vel01 = max(0.0, min(1.0, velocity / 127.0))
        dur_steps = dur_steps_from_times(grid, start, end)

        sid = selector.pick(role)
        filepath = selector.get_filepath(sid)

        out.append(
            Event(
                bar=int(b),
                step=int(k),
                role=role,
                sample_id=sid,
                filepath=filepath,
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
                    "snapped_time": snapped,
                },
            )
        )

    out.sort(key=lambda e: (e.bar, e.step, e.role))

    # Deduplication for stability (User request)
    # Key: (bar, step, role, sample_id)
    # Resolution: max velocity
    dedup: Dict[Tuple[int, int, str, str], Event] = {}
    for ev in out:
        key = (ev.bar, ev.step, ev.role, ev.sample_id)
        if key not in dedup:
            dedup[key] = ev
        else:
            # Keep the one with higher velocity
            if ev.vel > dedup[key].vel:
                dedup[key] = ev
    
    # Sort again just to be sure
    final_events = sorted(list(dedup.values()), key=lambda e: (e.bar, e.step, e.role))
    
    return final_events


def dump_event_grid(events: List[Event]) -> List[Dict[str, Any]]:
    arr: List[Dict[str, Any]] = []
    for e in events:
        arr.append(
            {
                "bar": e.bar,
                "step": e.step,
                "role": e.role,
                "sample_id": e.sample_id,
                "filepath": e.filepath,
                "vel": e.vel,
                "dur_steps": e.dur_steps,
                "micro_offset_ms": e.micro_offset_ms,
                "source": e.source,
            }
        )
    return arr