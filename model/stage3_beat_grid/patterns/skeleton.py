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

    # FILL (pattern-based)
    fill_every_n_bars: int = 4       # 매 4bar마다 마지막 bar
    fill_prob: float = 0.25          # 0~1

    # fill 생성 방식: "patterns"(권장) | "random"(예전 방식)
    fill_mode: str = "patterns"
    fill_repeat_across_occurrences: bool = True  # fill이 여러 번 등장할 때 같은 패턴 유지

    # fill이 들어갈 구간(보통 마디 끝 1/4)
    fill_window_steps: Tuple[int, ...] = (12, 13, 14, 15)

    # 패턴 가중치: [one, two, three, offbeat, full_roll]
    # full_roll(4연타)은 낮게
    fill_pattern_weights: Tuple[float, ...] = (0.35, 0.30, 0.20, 0.10, 0.05)

    # FILL velocity 감쇄(조금 덜 시끄럽게)
    fill_vel_scale: float = 0.75

    # (옵션) 예전 random 방식 파라미터(호환)
    fill_steps: Tuple[int, ...] = (12, 13, 14, 15)
    fill_num_steps_range: Tuple[int, int] = (1, 3)  # 1~3개

    # TEXTURE
    texture_enabled: bool = True

    # texture는 배경이므로, 기본은 "곡 전체를 1개 이벤트로" 깔기
    # (renderer에서 길이가 부족하면 loop로 채우도록)
    texture_loop_enabled: bool = True

    # texture velocity 감쇄(잔잔하게)
    texture_vel_scale: float = 0.55

    # legacy: bar마다 깔고 싶으면 True로 돌리면 됨(추천 X)
    texture_per_bar: bool = False
    texture_dur_steps: int = 16  # texture_per_bar=True일 때만 의미


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


def _pick_weighted(rng: random.Random, items: List[Tuple[int, ...]], weights: List[float]) -> Tuple[int, ...]:
    return rng.choices(items, weights=weights, k=1)[0]


def _fill_patterns_for_window(window: Tuple[int, ...]) -> List[Tuple[int, ...]]:
    w = list(window)
    if len(w) < 2:
        return [tuple(w)]
    if len(w) == 2:
        return [(w[1],), (w[0], w[1])]

    # 4개 기준
    s0, s1, s2, s3 = w[0], w[1], w[2], w[3]
    return [
        (s3,),                 # 0) one_shot
        (s2, s3),              # 1) two_shot
        (s1, s2, s3),          # 2) three_shot
        (s0, s2, s3),          # 3) offbeat_roll
        (s0, s1, s2, s3),      # 4) full_roll (가끔만)
    ]


def build_skeleton_events(
    pools_json: Dict[str, List[dict]],
    cfg: SkeletonConfig,
    tstep: float = 0.125,
) -> Tuple[List[Event], Dict[str, str]]:
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

    # 16-step grid assumptions:
    # 0=1.1, 4=1.2, 8=1.3, 12=1.4
    
    # Define Styles (Core Steps, Accent Steps)
    # This could be moved to config or outside function, but fine here for now.
    STYLES = {
        "rock":   ((0, 8), (4, 12)),
        "house":  ((0, 4, 8, 12), (4, 12)),
        "techno": ((0, 4, 8, 12), (4, 12)),
        "hiphop": ((0, 10), (4, 12)),
        "trap":   ((0, 10), (4, 12)), # Similar to hiphop but often slower feel
        "funk":   ((0, 7, 10), (4, 12)), # Syncopated
        "rnb":    ((0, 3, 8), (4, 12)), # Smoother kick placement
        "dnb":    ((0, 10), (4, 12)), # Fast breakbeat feel (needs high BPM)
    }
    
    style_key = cfg.pattern_style.lower()
    if style_key not in STYLES:
        # Fallback to rock if unknown
        style_key = "rock"
        
    core_steps, accent_steps = STYLES[style_key]

    # ---- CORE
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
                        step=int(s) % cfg.steps_per_bar,
                        role="CORE",
                        sample_id=str(core_sample["sample_id"]),
                        vel=vel_from_energy("CORE", e, rng),
                        dur_steps=dur,
                    )
                )

    # ---- ACCENT
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
                        step=int(s) % cfg.steps_per_bar,
                        role="ACCENT",
                        sample_id=str(accent_sample["sample_id"]),
                        vel=vel_from_energy("ACCENT", e, rng),
                        dur_steps=dur,
                    )
                )

    # ---- MOTION
    motion_steps_A = tuple(range(0, cfg.steps_per_bar))          # 0..15
    motion_steps_B = (1, 3, 5, 7, 9, 11, 13, 15)                 # offbeat-ish
    base_steps = motion_steps_A if cfg.motion_mode.upper() == "A" else motion_steps_B

    fixed_picked_steps: Optional[List[int]] = None
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
                        step=int(s) % cfg.steps_per_bar,
                        role="MOTION",
                        sample_id=str(samp["sample_id"]),
                        vel=vel_from_energy("MOTION", e, rng),
                        dur_steps=dur,
                    )
                )

    # ---- FILL (pattern-based)
    if fill_sample and cfg.num_bars > 0:
        last_bar = cfg.num_bars - 1

        if cfg.fill_every_n_bars <= 1:
            do_fill = (rng.random() < cfg.fill_prob)
        else:
            # e.g. 4 bars total, fill_every_n_bars=4 -> 4%4==0 -> True
            is_fill_bar = (cfg.num_bars % cfg.fill_every_n_bars == 0)
            do_fill = is_fill_bar and (rng.random() < cfg.fill_prob)

        if do_fill:
            feats = fill_sample.get("features", {})
            decay = feats.get("decay_time", None)
            dur = dur_from_decay(decay, tstep, "FILL")

            fill_steps_to_use: Tuple[int, ...]
            if cfg.fill_mode == "patterns":
                patterns = _fill_patterns_for_window(cfg.fill_window_steps)
                weights = list(cfg.fill_pattern_weights)
                if len(weights) != len(patterns):
                    weights = [1.0] * len(patterns)
                chosen_pattern = _pick_weighted(rng, patterns, weights)
                fill_steps_to_use = tuple(chosen_pattern)
            else:
                window = cfg.fill_steps if cfg.fill_steps else cfg.fill_window_steps
                nmin, nmax = cfg.fill_num_steps_range
                n = rng.randint(max(1, nmin), max(1, nmax))
                n = min(n, len(window))
                fill_steps_to_use = tuple(sorted(rng.sample(list(window), k=n)))

            for s in sorted(fill_steps_to_use):
                e = feats.get("energy", None)
                v = vel_from_energy("FILL", e, rng) * float(cfg.fill_vel_scale)
                events.append(
                    Event(
                        bar=last_bar,
                        step=int(s) % cfg.steps_per_bar,
                        role="FILL",
                        sample_id=str(fill_sample["sample_id"]),
                        vel=v,
                        dur_steps=dur,
                    )
                )

    # ---- TEXTURE
    if texture_sample and cfg.texture_enabled:
        feats = texture_sample.get("features", {})
        e = feats.get("energy", None)

        # 텍스처는 보통 '잔잔한 배경'이라 velocity 낮추는 쪽이 안전
        v = vel_from_energy("TEXTURE", e, rng) * float(cfg.texture_vel_scale)

        if cfg.texture_per_bar:
            # legacy: bar마다 깔기(추천 X)
            dur = int(cfg.texture_dur_steps)
            for b in range(cfg.num_bars):
                events.append(
                    Event(
                        bar=b,
                        step=0,
                        role="TEXTURE",
                        sample_id=str(texture_sample["sample_id"]),
                        vel=v,
                        dur_steps=dur,
                    )
                )
        else:
            # 추천: 곡 전체 길이 1개 이벤트로 깔기
            # renderer에서 샘플이 짧으면 loop로 늘려서 깔아야 "끊김"이 안 남
            total_steps = int(cfg.num_bars * cfg.steps_per_bar)
            events.append(
                Event(
                    bar=0,
                    step=0,
                    role="TEXTURE",
                    sample_id=str(texture_sample["sample_id"]),
                    vel=v,
                    dur_steps=total_steps,
                )
            )

    events.sort(key=lambda e: (e.bar, e.step, e.role))
    return events, chosen