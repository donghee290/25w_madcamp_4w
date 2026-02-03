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
    
    # Pattern Style
    pattern_style: str = "rock"

    # MOTION 밀도
    motion_mode: str = "A"          # A or B
    motion_keep_per_bar: int = 6    # 4~8 권장

    motion_repeat_across_bars: bool = True

    # FILL
    fill_every_n_bars: int = 4       # 매 4bar마다 마지막 bar
    fill_prob: float = 0.25          # 0~1
    fill_steps: Tuple[int, ...] = (12, 13, 14, 15)
    fill_num_steps_range: Tuple[int, int] = (1, 3)  # 1~3개

    # TEXTURE
    texture_enabled: bool = True
    texture_dur_steps: int = 16


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


def build_skeleton_events(
    pools_json: Dict[str, List[dict]],
    cfg: SkeletonConfig,
    tstep: float = 0.125,
) -> Tuple[List[Event], Dict[str, str]]:
    """Build skeleton events based on pattern style."""
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
    
    motion_candidates = _pick_many(rng, motion_pool, k=4)
    if motion_candidates:
        chosen["MOTION"] = ",".join([str(x.get("sample_id")) for x in motion_candidates])

    events: List[Event] = []
    from stage3_beat_grid.events import dur_from_decay

    # Define patterns based on style
    # 16-step grid assumptions:
    # 0=1.1, 4=1.2, 8=1.3, 12=1.4
    
    if cfg.pattern_style == "house":
        core_steps = (0, 4, 8, 12)  # Four on the floor
        accent_steps = (4, 12)      # Backbeat on 2 and 4
    elif cfg.pattern_style == "hiphop":
        core_steps = (0, 10)        # Kick on 1 and 3-and (classic boom-bap / breakbeatish)
        accent_steps = (4, 12)      # Snare on 2 and 4
    else: 
        # "rock" / standard (Kung-Chi-Ta-Chi)
        core_steps = (0, 8)         # Kick on 1 and 3
        accent_steps = (4, 12)      # Snare on 2 and 4

    # ---- CORE skeleton
    if core_sample:
        feats = core_sample.get("features", {})
        decay = feats.get("decay_time", None)
        dur = dur_from_decay(decay, tstep, "CORE")
        
        for b in range(cfg.num_bars):
            for s in core_steps:
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

    # ---- ACCENT skeleton
    if accent_sample:
        feats = accent_sample.get("features", {})
        decay = feats.get("decay_time", None)
        dur = dur_from_decay(decay, tstep, "ACCENT")

        for b in range(cfg.num_bars):
            for s in accent_steps:
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
    motion_steps_A = tuple(range(0, cfg.steps_per_bar))
    motion_steps_B = (1, 3, 5, 7, 9, 11, 13, 15)
    base_steps = motion_steps_A if cfg.motion_mode.upper() == "A" else motion_steps_B

    fixed_picked_steps = None
    if cfg.motion_repeat_across_bars:
        keep = min(cfg.motion_keep_per_bar, len(base_steps))
        fixed_picked_steps = sorted(rng.sample(list(base_steps), k=keep))

    if motion_candidates:
        for b in range(cfg.num_bars):
            if fixed_picked_steps is not None:
                picked_steps = fixed_picked_steps
            else:
                keep = min(cfg.motion_keep_per_bar, len(base_steps))
                picked_steps = sorted(rng.sample(list(base_steps), k=keep))

            for i, s in enumerate(picked_steps):
                samp = motion_candidates[i % len(motion_candidates)]
                feats = samp.get("features", {})
                decay = feats.get("decay_time", None)
                dur = dur_from_decay(decay, tstep, "MOTION")
                e = feats.get("energy", None)

                events.append(
                    Event(
                        bar=b,
                        step=int(s) % cfg.steps_per_bar,  # 방어
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

    events.sort(key=lambda e: (e.bar, e.step, e.role))
    return events, chosen