from __future__ import annotations

from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

from .types import Grid, Event
from .grid_io import build_repeated_grid


@dataclass
class ProgressiveConfig:
    # 무조건 8bars마다 레이어가 하나씩 추가됨
    segment_bars: int = 8

    # 고정 레이어 순서 (요구사항)
    layers: Tuple[str, ...] = ("CORE", "ACCENT", "MOTION", "FILL", "TEXTURE")

    # 마지막 "풀 레이어" 반복 (원하면 0으로)
    final_repeat: int = 0

    # 5/5 bar issue fix: Force based loop length (e.g. 4)
    base_loop_len: int = None


def filter_by_roles(events: List[Event], allowed: set[str]) -> List[Event]:
    return [e for e in events if str(e.role).upper() in allowed]


def shift_bars(events: List[Event], bar_offset: int) -> List[Event]:
    out: List[Event] = []
    for e in events:
        out.append(
            Event(
                bar=int(e.bar) + int(bar_offset),
                step=int(e.step),
                role=e.role,
                sample_id=e.sample_id,
                filepath=getattr(e, "filepath", None),
                vel=e.vel,
                dur_steps=e.dur_steps,
                micro_offset_ms=getattr(e, "micro_offset_ms", 0.0),
                source=getattr(e, "source", "progressive"),
                extra=getattr(e, "extra", None),
            )
        )
    return out


def _has_any_role(events: List[Event], role: str) -> bool:
    ru = role.upper()
    for e in events:
        if str(e.role).upper() == ru:
            return True
    return False


def _fit_to_segment(events: List[Event], seg: int, base_len_override: int = None) -> List[Event]:
    """
    base_events는 보통 base_grid.num_bars 길이(예: 4bar)로 들어오는데,
    segment_bars=8로 늘리려면 "패턴을 반복"해서 seg 길이로 맞춘다.
    base_len_override가 있으면 그 길이를 기준으로 반복한다(overflow 방지).
    """
    if seg <= 0:
        return []

    # base 길이 추정
    if base_len_override is not None and base_len_override > 0:
        base_len = base_len_override
    else:
        max_bar = 0
        for e in events:
            if int(e.bar) > max_bar:
                max_bar = int(e.bar)
        base_len = max_bar + 1  # bar index는 0-based

    if base_len <= 0:
        base_len = 1

    if base_len == seg:
        return [e for e in events if 0 <= int(e.bar) < seg]

    # base_len < seg (or mismatch): 반복해서 seg까지 채움/자름
    out: List[Event] = []
    repeat = (seg + base_len - 1) // base_len  # ceil
    for r in range(repeat):
        offset = r * base_len
        for e in events:
            # 원본이 base_len보다 긴 경우(overflow)도 있는데,
            # base_len_override가 있다면, 그 길이만큼은 "다음 루프"의 시작점과 겹치게 됨.
            # 하지만 단순 반복을 위해 여기서는 nb = e.bar + offset으로 둔다.
            # 만약 e.bar >= base_len_override라면, 다음 루프 영역에 찍히게 된다.
            
            nb = int(e.bar) + offset
            if 0 <= nb < seg:
                out.append(
                    Event(
                        bar=nb,
                        step=int(e.step),
                        role=e.role,
                        sample_id=e.sample_id,
                        filepath=getattr(e, "filepath", None),
                        vel=e.vel,
                        dur_steps=e.dur_steps,
                        micro_offset_ms=getattr(e, "micro_offset_ms", 0.0),
                        source=getattr(e, "source", "progressive"),
                        extra=getattr(e, "extra", None),
                    )
                )
    return out


def build_progressive_timeline(
    base_grid: Grid,
    base_events: List[Event],
    cfg: ProgressiveConfig,
    available_pool_roles: List[str] = None,
) -> Tuple[Grid, List[Event], Dict[str, Any]]:
    """
    요구사항:
    - 무조건 core > accent > motion > fill > texture 순
    - 8bars마다 하나씩 쌓음
    - core/accent/motion은 필수
    - fill/texture는 없으면 '그 레이어 단계 자체'를 스킵
      (즉, CORE+ACCENT+MOTION까지만 진행하고 끝)
    """
    seg = int(cfg.segment_bars)

    # 필수 3개 존재 체크: 하나라도 없으면 progressive 자체를 만들지 않고 원본 반환
    required = ("CORE", "ACCENT", "MOTION")
    if not all(_has_any_role(base_events, r) for r in required):
        meta = {
            "segment_bars": seg,
            "layers": list(cfg.layers),
            "segments": [],
            "skipped": True,
            "reason": "missing required roles (need CORE/ACCENT/MOTION)",
        }
        return base_grid, base_events, meta

    # 진행 순서는 config를 따르되, 실제로 사용 가능한 리소스(Pool)가 있거나 이벤트가 존재하는 레이어만 진행
    # (예: Texture가 풀에도 없고 이벤트도 없으면 스킵. 풀에라도 있으면 섹션 생성)
    event_roles = set(str(e.role).upper() for e in base_events)
    pool_roles = set(r.upper() for r in (available_pool_roles or []))
    available_roles = event_roles.union(pool_roles)

    effective_layers = [L for L in cfg.layers if L.upper() in available_roles]

    # 누적 허용 role set을 단계별로 확장
    allowed: set[str] = set()
    staged_events: List[Event] = []
    meta_segments: List[Dict[str, Any]] = []

    # seg 길이로 맞춘 "세그먼트용 루프 이벤트"를 단계별로 만들기 위해,
    # base_events에서 필요한 role만 뽑고, seg bars로 늘려둔다.
    for i, role in enumerate(effective_layers):
        allowed.add(role.upper())

        layer_events = filter_by_roles(base_events, allowed)
        layer_events = _fit_to_segment(layer_events, seg, cfg.base_loop_len)  # 핵심: 8bar segment에 맞게 반복/자르기

        bar_offset = i * seg
        staged_events.extend(shift_bars(layer_events, bar_offset))

        meta_segments.append(
            {
                "segment_index": i,
                "bar_offset": bar_offset,
                "allowed_roles": sorted(list(allowed)),
                "num_events": len(layer_events),
                "type": "buildup",
            }
        )

    # 마지막 "풀 레이어" 반복 (원하면)
    current_seg_idx = len(effective_layers)
    if cfg.final_repeat > 0:
        final_events = filter_by_roles(base_events, allowed)
        final_events = _fit_to_segment(final_events, seg, cfg.base_loop_len)

        for r in range(int(cfg.final_repeat)):
            bar_offset = (current_seg_idx + r) * seg
            staged_events.extend(shift_bars(final_events, bar_offset))
            meta_segments.append(
                {
                    "segment_index": current_seg_idx + r,
                    "bar_offset": bar_offset,
                    "allowed_roles": sorted(list(allowed)),
                    "num_events": len(final_events),
                    "type": "repeat_full",
                }
            )
        current_seg_idx += int(cfg.final_repeat)

    total_bars = seg * current_seg_idx
    new_grid = build_repeated_grid(base_grid, repeat_bars=total_bars)

    staged_events.sort(key=lambda e: (int(e.bar), int(e.step), str(e.role)))
    meta = {
        "segment_bars": seg,
        "layers_requested": list(cfg.layers),
        "layers_effective": effective_layers,
        "segments": meta_segments,
        "skipped": False,
        "notes": "segments are 8 bars; base pattern is repeated/truncated to fit each segment",
    }
    return new_grid, staged_events, meta