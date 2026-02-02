from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


def load_json(path: str | Path) -> Any:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(path: str | Path, obj: Any) -> None:
    p = Path(path)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class MidiNote:
    start: float
    end: float
    pitch: int
    velocity: int
    is_drum: bool = True


def load_midi_as_notes(midi_path: str | Path) -> List[MidiNote]:
    """
    GrooVAE 출력 MIDI를 읽어 note list로 변환.
    pretty_midi 사용(설치 필요).
    """
    import pretty_midi  # type: ignore

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    notes: List[MidiNote] = []
    for inst in pm.instruments:
        for n in inst.notes:
            notes.append(
                MidiNote(
                    start=float(n.start),
                    end=float(n.end),
                    pitch=int(n.pitch),
                    velocity=int(n.velocity),
                    is_drum=bool(inst.is_drum),
                )
            )
    notes.sort(key=lambda x: (x.start, x.pitch))
    return notes


def _role_from_drum_pitch(pitch: int) -> str:
    """
    GrooVAE 드럼 채널을 role로 역매핑.
    여러 tom pitch는 FILL로.
    """
    # GM drum map 기준의 대표 pitch
    kick = {35, 36}
    snare = {38, 40}
    hh = {42, 44, 46}  # closed/pedal/open
    tom = {41, 43, 45, 47, 48, 50}  # low/mid/high tom류

    if pitch in kick:
        return "CORE"
    if pitch in snare:
        return "ACCENT"
    if pitch in hh:
        return "MOTION"
    if pitch in tom:
        return "FILL"
    # 기타는 일단 FILL로
    return "FILL"


def _vel_to_0_1(vel: int) -> float:
    v = int(vel)
    v = max(1, min(127, v))
    return float((v - 1) / 126.0)


def _clamp(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


def _time_to_bar_step_and_offset_ms(
    t: float,
    tbar: float,
    tstep: float,
    steps_per_bar: int,
) -> Tuple[int, int, float]:
    """
    UI 표시용: 가장 가까운 step으로 스냅(bar,step)
    재생용: micro_offset_ms = 실제 t - 스냅된 t_step
    """
    if t < 0:
        t = 0.0

    bar = int(math.floor(t / tbar))
    bar_t0 = bar * tbar

    rel = t - bar_t0
    step_f = rel / tstep
    step = int(round(step_f))
    step = max(0, min(steps_per_bar - 1, step))

    snapped_t = bar_t0 + step * tstep
    micro_ms = (t - snapped_t) * 1000.0

    # 너무 튀면 클램프 (그루브 느낌은 살리되 UI/재생 안전)
    micro_ms = _clamp(micro_ms, -60.0, 60.0)

    return bar, step, float(micro_ms)


def build_events_from_notes(
    grid_json: Dict[str, Any],
    notes: List[MidiNote],
    source_tag: str = "groovae",
) -> List[Dict[str, Any]]:
    bpm = float(grid_json["bpm"])
    steps_per_bar = int(grid_json.get("steps_per_bar", 16))
    num_bars = int(grid_json.get("num_bars", 4))

    tbeat = float(grid_json.get("tbeat", 60.0 / bpm))
    tbar = float(grid_json.get("tbar", 4.0 * tbeat))
    tstep = float(grid_json.get("tstep", tbar / steps_per_bar))

    events: List[Dict[str, Any]] = []

    for n in notes:
        role = _role_from_drum_pitch(n.pitch)
        t = float(n.start)

        bar, step, micro_ms = _time_to_bar_step_and_offset_ms(t, tbar, tstep, steps_per_bar)

        # grid 범위 밖은 버림
        if bar < 0 or bar >= num_bars:
            continue

        dur_sec = max(0.0, float(n.end) - float(n.start))
        dur_steps = int(math.ceil(dur_sec / tstep)) if dur_sec > 1e-6 else 1
        dur_steps = max(1, min(steps_per_bar, dur_steps))

        ev = {
            "bar": int(bar),
            "step": int(step),
            "role": str(role),
            "sample_id": "",  # 나중에 pools로 채움
            "vel": float(_vel_to_0_1(n.velocity)),
            "dur_steps": int(dur_steps),
            "micro_offset_ms": float(micro_ms),
            "source": str(source_tag),
        }
        events.append(ev)

    # 정렬(재생 안정)
    events.sort(key=lambda e: (int(e["bar"]), int(e["step"]), str(e["role"])))
    return events


def apply_poly_limit_and_protect(
    events: List[Dict[str, Any]],
    max_poly: int = 3,
    protect_core_steps: set[int] | None = None,
    protect_accent_steps: set[int] | None = None,
) -> List[Dict[str, Any]]:
    if protect_core_steps is None:
        protect_core_steps = {0, 4, 8, 12}
    if protect_accent_steps is None:
        protect_accent_steps = {4, 12}

    # 삭제 우선순위 (낮을수록 먼저 삭제)
    # TEXTURE > MOTION > FILL > ACCENT > CORE (CORE/ACCENT 보호)
    prio = {"TEXTURE": 0, "MOTION": 1, "FILL": 2, "ACCENT": 3, "CORE": 4}

    buckets: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for e in events:
        key = (int(e["bar"]), int(e["step"]))
        buckets.setdefault(key, []).append(e)

    out: List[Dict[str, Any]] = []
    for (bar, step), lst in buckets.items():
        if len(lst) <= max_poly:
            out.extend(lst)
            continue

        # 보호 대상 표시
        def is_protected(ev: Dict[str, Any]) -> bool:
            r = str(ev.get("role"))
            if r == "CORE" and step in protect_core_steps:
                return True
            if r == "ACCENT" and step in protect_accent_steps:
                return True
            return False

        protected = [e for e in lst if is_protected(e)]
        others = [e for e in lst if not is_protected(e)]

        # others를 prio 낮은 것부터 삭제(= prio 작은게 먼저 잘림)
        others.sort(key=lambda e: (prio.get(str(e.get("role")), 999), -float(e.get("vel", 0.0))))

        keep = protected[:]
        # 남은 슬롯
        slots = max_poly - len(keep)
        if slots > 0:
            # prio 높은(=삭제 늦게) 애들부터 남겨야 하니까 뒤에서 채움
            others_keep = sorted(others, key=lambda e: (prio.get(str(e.get("role")), 999), -float(e.get("vel", 0.0))))
            # 위 정렬은 삭제 후보가 앞, 유지 후보가 뒤가 되기 쉬움
            # 그래서 뒤에서 slots개 가져오되, 안정적으로 vel 높은 거 우선 남김
            others_sorted_for_keep = sorted(others, key=lambda e: (prio.get(str(e.get("role")), 999), -float(e.get("vel", 0.0))))
            keep.extend(others_sorted_for_keep[-slots:])

        out.extend(keep)

    out.sort(key=lambda e: (int(e["bar"]), int(e["step"]), str(e["role"])))
    return out


def _pool_list(pools: Dict[str, Any], role: str) -> List[Dict[str, Any]]:
    key = f"{role}_POOL"
    v = pools.get(key, [])
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    return []


def assign_samples_from_pools(
    events: List[Dict[str, Any]],
    pools: Dict[str, Any],
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """
    sample_id 부여 규칙(요구사항 반영):
    - CORE: 1개 고정
    - ACCENT: 1개 고정
    - MOTION: 여러 개면 round-robin
    - FILL: 있으면 1개 고정, 없으면 비움
    - TEXTURE: 있으면 1개 고정(렌더에서 gate 처리할 거면 vel 낮추는 건 별도)
    """
    rng = np.random.default_rng(int(seed))

    core_pool = _pool_list(pools, "CORE")
    accent_pool = _pool_list(pools, "ACCENT")
    motion_pool = _pool_list(pools, "MOTION")
    fill_pool = _pool_list(pools, "FILL")
    texture_pool = _pool_list(pools, "TEXTURE")

    def pick_one(pool: List[Dict[str, Any]]) -> Optional[str]:
        if not pool:
            return None
        # confidence 높은 것 우선
        pool2 = sorted(pool, key=lambda x: float(x.get("confidence", 0.0)), reverse=True)
        return str(pool2[0].get("sample_id") or "")

    core_fixed = pick_one(core_pool)
    accent_fixed = pick_one(accent_pool)
    fill_fixed = pick_one(fill_pool)
    texture_fixed = pick_one(texture_pool)

    motion_ids = [str(x.get("sample_id") or "") for x in sorted(motion_pool, key=lambda x: float(x.get("confidence", 0.0)), reverse=True)]
    motion_ids = [x for x in motion_ids if x]
    if not motion_ids and motion_pool:
        motion_ids = [str(motion_pool[0].get("sample_id") or "")]

    motion_idx = 0

    out = []
    for e in events:
        r = str(e.get("role"))
        e2 = dict(e)

        if r == "CORE":
            e2["sample_id"] = core_fixed or ""
        elif r == "ACCENT":
            e2["sample_id"] = accent_fixed or ""
        elif r == "MOTION":
            if motion_ids:
                e2["sample_id"] = motion_ids[motion_idx % len(motion_ids)]
                motion_idx += 1
            else:
                e2["sample_id"] = ""
        elif r == "FILL":
            e2["sample_id"] = fill_fixed or ""
        elif r == "TEXTURE":
            e2["sample_id"] = texture_fixed or ""
        else:
            e2["sample_id"] = e2.get("sample_id", "") or ""

        out.append(e2)

    return out


def deduce_sample_root_from_pools(pools: Dict[str, Any]) -> Optional[Path]:
    """
    pools json에 filepath가 들어있다면 그 공통 부모를 추정해서 sample_root로 사용.
    """
    paths: List[Path] = []
    for role in ["CORE", "ACCENT", "MOTION", "FILL", "TEXTURE"]:
        for x in _pool_list(pools, role):
            fp = x.get("filepath")
            if fp:
                paths.append(Path(str(fp)))

    if not paths:
        return None

    # 가장 많은 경우에 공통인 parent를 하나 찾기: 우선 examples/input_samples 같은 디렉토리
    # 여기서는 단순히 "가장 짧은 parent" 기준으로 맞춤
    parents = [p.parent for p in paths if p.parent.exists() or True]
    # 같은 parent가 가장 많이 등장하는 것
    from collections import Counter
    c = Counter([str(p) for p in parents])
    best, _ = c.most_common(1)[0]
    return Path(best)


def build_progressive_arrangement(
    base_grid: Dict[str, Any],
    base_events: List[Dict[str, Any]],
    stages: Sequence[Tuple[int, Tuple[str, ...]]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    stages: [(bars, ("CORE",)), (bars, ("CORE","ACCENT")), ...]
    base_events를 stage마다 role 필터 후 bar 오프셋해서 이어붙임.
    """
    steps_per_bar = int(base_grid.get("steps_per_bar", 16))
    bpm = float(base_grid["bpm"])
    meter = base_grid.get("meter", "4/4")

    tbeat = float(base_grid.get("tbeat", 60.0 / bpm))
    tbar = float(base_grid.get("tbar", 4.0 * tbeat))
    tstep = float(base_grid.get("tstep", tbar / steps_per_bar))

    total_bars = int(sum(int(b) for b, _ in stages))

    bar_start = [b * tbar for b in range(total_bars)]
    t_step = []
    for b in range(total_bars):
        t_step.append([bar_start[b] + k * tstep for k in range(steps_per_bar)])

    new_grid = {
        "bpm": bpm,
        "meter": meter,
        "steps_per_bar": steps_per_bar,
        "num_bars": total_bars,
        "tbeat": tbeat,
        "tbar": tbar,
        "tstep": tstep,
        "bar_start": bar_start,
        "t_step": t_step,
    }

    out_events: List[Dict[str, Any]] = []
    bar_offset = 0
    stage_idx = 1
    for bars, roles in stages:
        allowed = set(roles)
        stage_events = [e for e in base_events if str(e.get("role")) in allowed]
        for e in stage_events:
            e2 = dict(e)
            e2["bar"] = int(e2["bar"]) + bar_offset
            # 추적용
            src = str(e2.get("source", ""))
            e2["source"] = f"{src}|stage{stage_idx}"
            out_events.append(e2)

        bar_offset += int(bars)
        stage_idx += 1

    out_events.sort(key=lambda e: (int(e["bar"]), int(e["step"]), str(e["role"])))
    return new_grid, out_events


def export_midi_from_events(
    grid_json: Dict[str, Any],
    events: List[Dict[str, Any]],
    out_midi: str | Path,
) -> None:
    """
    events -> MIDI(DAW용)
    sample_id는 MIDI에 못 담으니 json과 같이 보관.
    role -> drum pitch:
      CORE 36
      ACCENT 38
      MOTION 42
      FILL 45 (기본, 필요시 여러 tom로 분산은 다음 개선)
      TEXTURE는 제외(요구사항)
    """
    import pretty_midi  # type: ignore

    bpm = float(grid_json["bpm"])
    steps_per_bar = int(grid_json.get("steps_per_bar", 16))

    tbeat = float(grid_json.get("tbeat", 60.0 / bpm))
    tbar = float(grid_json.get("tbar", 4.0 * tbeat))
    tstep = float(grid_json.get("tstep", tbar / steps_per_bar))

    pitch_map = {
        "CORE": 36,
        "ACCENT": 38,
        "MOTION": 42,
        "FILL": 45,
    }

    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    drum = pretty_midi.Instrument(program=0, is_drum=True, name="drums")

    for e in events:
        role = str(e.get("role"))
        if role == "TEXTURE":
            continue
        pitch = pitch_map.get(role, 45)

        bar = int(e["bar"])
        step = int(e["step"])
        micro_ms = float(e.get("micro_offset_ms", 0.0))
        vel01 = float(e.get("vel", 0.5))
        vel = int(round(1 + 126 * _clamp(vel01, 0.0, 1.0)))

        dur_steps = int(e.get("dur_steps", 1))
        dur_steps = max(1, min(steps_per_bar, dur_steps))

        t = bar * tbar + step * tstep + (micro_ms / 1000.0)
        t = max(0.0, t)
        end = t + dur_steps * tstep

        n = pretty_midi.Note(
            velocity=vel,
            pitch=int(pitch),
            start=float(t),
            end=float(end),
        )
        drum.notes.append(n)

    pm.instruments.append(drum)
    pm.write(str(out_midi))