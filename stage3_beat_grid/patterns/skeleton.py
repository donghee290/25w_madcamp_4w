# beat_grid/patterns/skeleton.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import random

from stage3_beat_grid.events import Event, vel_from_energy


@dataclass(frozen=True)
class SkeletonConfig:
    seed: int = 42
    steps_per_bar: int = 16
    num_bars: int = 4

    # MOTION 밀도
    motion_mode: str = "A"          # A or B
    motion_keep_per_bar: int = 6    # 4~8 권장

    # FILL
    fill_every_n_bars: int = 4       # 매 4bar마다 마지막 bar
    fill_prob: float = 0.25          # 0~1
    fill_steps: Tuple[int, ...] = (12, 13, 14, 15)
    fill_num_steps_range: Tuple[int, int] = (1, 3)  # 1~3개

    # TEXTURE
    texture_enabled: bool = True
    texture_dur_steps: int = 16

    # 동시타격 제한
    max_poly: int = 3


def _pick_one(rng: random.Random, pool: List[dict]) -> Optional[dict]:
    if not pool:
        return None
    return rng.choice(pool)


def _pick_many(rng: random.Random, pool: List[dict], k: int) -> List[dict]:
    if not pool:
        return []
    if len(pool) <= k:
        return list(pool)
    return rng.sample(pool, k)


def _event_key(e: Event) -> Tuple[int, int]:
    return (e.bar, e.step)


def _apply_max_poly(events: List[Event], max_poly: int) -> List[Event]:
    """
    같은 (bar, step)에 이벤트가 max_poly 초과면 삭제.
    삭제 우선순위: TEXTURE > MOTION > ACCENT > CORE (FILL은 ACCENT와 비슷하게 취급)
    """
    if max_poly <= 0:
        return events

    prio = {"CORE": 0, "ACCENT": 1, "FILL": 1, "MOTION": 2, "TEXTURE": 3}

    buckets: Dict[Tuple[int, int], List[Event]] = {}
    for e in events:
        buckets.setdefault(_event_key(e), []).append(e)

    out: List[Event] = []
    for k, lst in buckets.items():
        if len(lst) <= max_poly:
            out.extend(lst)
            continue
        lst_sorted = sorted(lst, key=lambda x: prio.get(x.role, 9))
        out.extend(lst_sorted[:max_poly])

    out.sort(key=lambda e: (e.bar, e.step, e.role))
    return out


def build_skeleton_events(
    pools_json: Dict[str, List[dict]],
    cfg: SkeletonConfig,
    tstep: float = 0.125,  # Add tstep argument for dur calculation
) -> Tuple[List[Event], Dict[str, str]]:
    """
    pools_json: role_assignment 결과 pools json
    """
    rng = random.Random(cfg.seed)

    core_pool = pools_json.get("CORE_POOL", []) or []
    accent_pool = pools_json.get("ACCENT_POOL", []) or []
    motion_pool = pools_json.get("MOTION_POOL", []) or []
    fill_pool = pools_json.get("FILL_POOL", []) or []
    texture_pool = pools_json.get("TEXTURE_POOL", []) or []

    chosen: Dict[str, str] = {}

    core_sample = _pick_one(rng, core_pool)
    accent_sample = _pick_one(rng, accent_pool)
    fill_sample = _pick_one(rng, fill_pool)
    texture_sample = _pick_one(rng, texture_pool) if cfg.texture_enabled else None

    if core_sample:
        chosen["CORE"] = str(core_sample.get("sample_id"))
    if accent_sample:
        chosen["ACCENT"] = str(accent_sample.get("sample_id"))
    if fill_sample:
        chosen["FILL"] = str(fill_sample.get("sample_id"))
    if texture_sample:
        chosen["TEXTURE"] = str(texture_sample.get("sample_id"))

    # MOTION은 2~4개 후보
    motion_candidates = _pick_many(rng, motion_pool, k=4)
    if motion_candidates:
        chosen["MOTION"] = ",".join([str(x.get("sample_id")) for x in motion_candidates])

    events: List[Event] = []

    from stage3_beat_grid.events import dur_from_decay  # Lazy import to avoid circular if any

    # ---- CORE skeleton: 0,4,8,12
    if core_sample:
        steps = (0, 4, 8, 12)
        feats = core_sample.get("features", {})
        decay = feats.get("decay_time", None)
        dur = dur_from_decay(decay, tstep, "CORE")
        
        for b in range(cfg.num_bars):
            for s in steps:
                e = feats.get("energy", None)
                events.append(
                    Event(
                        bar=b,
                        step=s,
                        role="CORE",
                        sample_id=str(core_sample["sample_id"]),
                        vel=vel_from_energy("CORE", e, rng),
                        dur_steps=dur,
                    )
                )

    # ---- ACCENT skeleton: 4,12
    if accent_sample:
        steps = (4, 12)
        feats = accent_sample.get("features", {})
        decay = feats.get("decay_time", None)
        dur = dur_from_decay(decay, tstep, "ACCENT")

        for b in range(cfg.num_bars):
            for s in steps:
                e = feats.get("energy", None)
                events.append(
                    Event(
                        bar=b,
                        step=s,
                        role="ACCENT",
                        sample_id=str(accent_sample["sample_id"]),
                        vel=vel_from_energy("ACCENT", e, rng),
                        dur_steps=dur,
                    )
                )

    # ---- MOTION skeleton
    motion_steps_A = (2, 6, 10, 14)
    motion_steps_B = (1, 3, 5, 7, 9, 11, 13, 15)
    base_steps = motion_steps_A if cfg.motion_mode.upper() == "A" else motion_steps_B

    if motion_candidates:
        for b in range(cfg.num_bars):
            # bar당 motion 후보 steps 중 keep개만 고정 seed로 선택
            keep = min(cfg.motion_keep_per_bar, len(base_steps))
            picked_steps = rng.sample(list(base_steps), k=keep)

            # step마다 sample을 round-robin
            for i, s in enumerate(sorted(picked_steps)):
                samp = motion_candidates[i % len(motion_candidates)]
                feats = samp.get("features", {})
                decay = feats.get("decay_time", None)
                dur = dur_from_decay(decay, tstep, "MOTION")
                e = feats.get("energy", None)
                
                events.append(
                    Event(
                        bar=b,
                        step=s,
                        role="MOTION",
                        sample_id=str(samp["sample_id"]),
                        vel=vel_from_energy("MOTION", e, rng),
                        dur_steps=dur,
                    )
                )

    # ---- FILL
    if fill_sample and cfg.num_bars > 0:
        last_bar = cfg.num_bars - 1
        if cfg.fill_every_n_bars <= 1:
            do_fill = (rng.random() < cfg.fill_prob)
        else:
            do_fill = (cfg.num_bars % cfg.fill_every_n_bars == 0) and (rng.random() < cfg.fill_prob)

        if do_fill:
            feats = fill_sample.get("features", {})
            decay = feats.get("decay_time", None)
            dur = dur_from_decay(decay, tstep, "FILL")
            
            nmin, nmax = cfg.fill_num_steps_range
            n = rng.randint(max(1, nmin), max(1, nmax))
            n = min(n, len(cfg.fill_steps))
            steps = rng.sample(list(cfg.fill_steps), k=n)
            for s in sorted(steps):
                e = feats.get("energy", None)
                events.append(
                    Event(
                        bar=last_bar,
                        step=int(s),
                        role="FILL",
                        sample_id=str(fill_sample["sample_id"]),
                        vel=vel_from_energy("FILL", e, rng),
                        dur_steps=dur,
                    )
                )

    # ---- TEXTURE: bar 시작 1개, dur=16
    if texture_sample and cfg.texture_enabled:
        feats = texture_sample.get("features", {})
        # Texture duration usually fixed to full bar
        dur = int(cfg.texture_dur_steps)
        
        for b in range(cfg.num_bars):
            e = feats.get("energy", None)
            events.append(
                Event(
                    bar=b,
                    step=0,
                    role="TEXTURE",
                    sample_id=str(texture_sample["sample_id"]),
                    vel=vel_from_energy("TEXTURE", e, rng), # Now randomizes
                    dur_steps=dur,
                )
            )

    # 동시타격 제한
    events = _apply_max_poly(events, cfg.max_poly)
    return events, chosen