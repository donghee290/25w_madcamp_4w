from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List

import json

def load_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def render_wav_from_event_grid(
    grid_json_path: str,
    event_grid_json_path: str,
    sample_root: str,
    out_wav: str,
    target_sr: int = 44100,
) -> None:
    grid: Dict[str, Any] = load_json(grid_json_path)
    events: List[Dict[str, Any]] = load_json(event_grid_json_path)

    # Use centralized render function
    from stage7_render.audio_renderer import render_events

    render_events(
        grid_json=grid,
        events=events,
        sample_root=Path(sample_root),
        out_wav=Path(out_wav),
        target_sr=int(target_sr),
    )