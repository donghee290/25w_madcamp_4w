from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List

from stage7_editor_preview.io import load_json

def render_wav_from_event_grid(
    grid_json_path: str,
    event_grid_json_path: str,
    sample_root: str,
    out_wav: str,
    target_sr: int = 44100,
) -> None:
    grid: Dict[str, Any] = load_json(grid_json_path)
    events: List[Dict[str, Any]] = load_json(event_grid_json_path)

    # 기존 render_events가 (grid_json dict, events list)를 받는 구조라면 그대로 전달
    from beat_grid.test_audio_render.render import render_events

    render_events(
        grid_json=grid,
        events=events,
        sample_root=Path(sample_root),
        out_wav=Path(out_wav),
        target_sr=int(target_sr),
    )