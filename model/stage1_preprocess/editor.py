"""CLI-based drum grid editor for event_grid.json customization."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from .events import EventGrid, DrumEvent, display_grid, generate_skeleton
from .scoring import DrumRole
from .sequencer import load_kit, render_event_grid
from .io.utils import save_audio


def cmd_show(grid_path: Path) -> None:
    grid = EventGrid.from_json(grid_path)
    print(display_grid(grid))
    print(f"\nTotal events: {len(grid.events)}")

    from collections import Counter

    dist = Counter(e.role.value for e in grid.events)
    for role_name, count in sorted(dist.items()):
        print(f"  {role_name}: {count}")


def cmd_set(
    grid_path: Path,
    bar: int,
    step: int,
    role: str,
    vel: float = 0.8,
    sample_id: Optional[str] = None,
    dur_steps: int = 1,
) -> None:
    grid = EventGrid.from_json(grid_path)

    drum_role = DrumRole(role)
    grid.remove_events(bar, step, drum_role)

    if sample_id is None:
        sample_id = f"{role}_001"

    grid.add_event(DrumEvent(
        bar=bar,
        step=step,
        role=drum_role,
        sample_id=sample_id,
        vel=vel,
        dur_steps=dur_steps,
    ))

    grid.to_json(grid_path)
    print(f"Set {role} at bar={bar} step={step} vel={vel}")


def cmd_remove(
    grid_path: Path,
    bar: int,
    step: int,
    role: Optional[str] = None,
) -> None:
    grid = EventGrid.from_json(grid_path)

    drum_role = DrumRole(role) if role else None
    removed = grid.remove_events(bar, step, drum_role)

    grid.to_json(grid_path)
    print(f"Removed {removed} event(s) at bar={bar} step={step}")


def cmd_velocity(
    grid_path: Path,
    role: Optional[str] = None,
    value: Optional[float] = None,
    scale: Optional[float] = None,
) -> None:
    grid = EventGrid.from_json(grid_path)

    drum_role = DrumRole(role) if role else None
    count = 0

    for event in grid.events:
        if drum_role and event.role != drum_role:
            continue

        if value is not None:
            event.vel = max(0.0, min(1.0, value))
        elif scale is not None:
            event.vel = max(0.0, min(1.0, event.vel * scale))
        count += 1

    grid.to_json(grid_path)
    target = role if role else "all"
    print(f"Updated velocity for {count} {target} events")


def cmd_render(
    grid_path: Path,
    output_path: Path,
    kit_dir: Optional[Path] = None,
    sr: int = 44100,
    reverb: bool = False,
    fmt: str = "wav",
) -> None:
    grid = EventGrid.from_json(grid_path)

    kit_path = kit_dir or (Path(grid.kit_dir) if grid.kit_dir else None)
    if not kit_path or not kit_path.exists():
        print(f"Error: Kit directory not found: {kit_path}")
        print("Use --kit-dir to specify the path to your drum kit")
        sys.exit(1)

    kit = load_kit(kit_path, sr=sr)
    audio = render_event_grid(grid, kit, sr=sr, reverb=reverb)

    if fmt == "mp3":
        wav_path = output_path.with_suffix(".wav")
        save_audio(wav_path, audio, sr)
        try:
            from pydub import AudioSegment
            sound = AudioSegment.from_wav(str(wav_path))
            sound.export(str(output_path), format="mp3")
            wav_path.unlink()
            print(f"Rendered mp3: {output_path}")
        except ImportError:
            print(f"pydub not installed, saved as WAV: {wav_path}")
    else:
        save_audio(output_path, audio, sr)
        print(f"Rendered wav: {output_path}")


def cmd_export_midi(grid_path: Path, output_path: Path) -> None:
    grid = EventGrid.from_json(grid_path)
    grid.to_midi(output_path)
    print(f"MIDI exported: {output_path}")


def cmd_generate(
    output_path: Path,
    bpm: float = 120.0,
    bars: int = 4,
    kit_dir: Optional[str] = None,
) -> None:
    grid = generate_skeleton(
        bars=bars,
        bpm=bpm,
        kit_dir=kit_dir or "",
    )
    grid.to_json(output_path)
    print(f"Generated skeleton pattern: {output_path}")
    print(display_grid(grid))
