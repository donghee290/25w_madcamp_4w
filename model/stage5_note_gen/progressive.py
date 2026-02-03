from __future__ import annotations

from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

from .types import Grid, Event
from .grid_io import build_repeated_grid


@dataclass
class ProgressiveConfig:
    segment_bars: int = 4
    layers: Tuple[str, ...] = ("CORE", "ACCENT", "MOTION", "FILL")  # TEXTURE는 보통 별도
    final_repeat: int = 2  # 마지막 Full 단계를 몇 번 더 반복할지


def filter_by_roles(events: List[Event], allowed: set[str]) -> List[Event]:
    return [e for e in events if e.role.upper() in allowed]


def shift_bars(events: List[Event], bar_offset: int) -> List[Event]:
    out: List[Event] = []
    for e in events:
        out.append(
            Event(
                bar=e.bar + bar_offset,
                step=e.step,
                role=e.role,
                sample_id=e.sample_id,
                vel=e.vel,
                dur_steps=e.dur_steps,
                micro_offset_ms=e.micro_offset_ms,
                source=e.source,
                extra=e.extra,
            )
        )
    return out


def build_progressive_timeline(
    base_grid: Grid,
    base_events: List[Event],
    cfg: ProgressiveConfig,
) -> Tuple[Grid, List[Event], Dict[str, Any]]:
    # base_grid.num_bars는 보통 4로 들어옴
    seg = int(cfg.segment_bars)

    # 누적 허용 role set을 단계별로 확장
    allowed: set[str] = set()
    staged_events: List[Event] = []
    meta_layers: List[Dict[str, Any]] = []

    for i, role in enumerate(cfg.layers):
        allowed.add(role.upper())
        # base_events에서 필요한 role만 뽑기
        layer_events = filter_by_roles(base_events, allowed)

        # segment에 맞추기: base_events는 bar 0..base_grid.num_bars-1 이므로,
        # seg bars 단위를 넘기려면 bar 범위를 잘라야 함
        # MVP: base_grid.num_bars == seg 가정(기본 4)
        layer_events = [e for e in layer_events if 0 <= e.bar < seg]

        # i번째 segment로 bar shift
        bar_offset = i * seg
        staged_events.extend(shift_bars(layer_events, bar_offset))

        meta_layers.append(
            {
                "segment_index": i,
                "bar_offset": bar_offset,
                "allowed_roles": sorted(list(allowed)),
                "num_events": len(layer_events),
                "type": "buildup"
            }
        )

    # Final repeat (Full intensity)
    # 마지막 레이어 상태(allowed가 전부 포함된 상태)를 그대로 유지하며 뒤에 붙임
    final_layer_events = filter_by_roles(base_events, allowed)
    final_layer_events = [e for e in final_layer_events if 0 <= e.bar < seg] # base loop

    current_seg_idx = len(cfg.layers)
    for r in range(cfg.final_repeat):
        bar_offset = current_seg_idx * seg
        staged_events.extend(shift_bars(final_layer_events, bar_offset))
        
        meta_layers.append({
            "segment_index": current_seg_idx,
            "bar_offset": bar_offset,
            "allowed_roles": sorted(list(allowed)),
            "num_events": len(final_layer_events),
            "type": "repeat_full"
        })
        current_seg_idx += 1

    total_bars = seg * current_seg_idx
    new_grid = build_repeated_grid(base_grid, repeat_bars=total_bars)
    staged_events.sort(key=lambda e: (e.bar, e.step))
    meta = {"segment_bars": seg, "layers": list(cfg.layers), "segments": meta_layers}
    return new_grid, staged_events, meta