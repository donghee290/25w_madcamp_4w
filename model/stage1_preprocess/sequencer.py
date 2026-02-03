"""Sequencer module for rendering EventGrid to audio."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Dict, List

import numpy as np

from .io.utils import logger, load_audio, save_audio
from .scoring import DrumRole
from .events import EventGrid


def load_kit(kit_dir: Path, sr: int = 44100) -> Dict[DrumRole, List[np.ndarray]]:
    """Load a drum kit from role subdirectories."""
    mapping = {
        "kick": DrumRole.CORE,
        "ltom": DrumRole.CORE,
        "snare": DrumRole.ACCENT,
        "hihat": DrumRole.MOTION,
        "ride": DrumRole.MOTION,
        "crash": DrumRole.TEXTURE,
        "rtom": DrumRole.FILL,
        "rowtom": DrumRole.FILL,
    }

    kit: Dict[DrumRole, List[np.ndarray]] = {r: [] for r in DrumRole}

    for subdir in kit_dir.iterdir():
        if not subdir.is_dir():
            continue

        try:
            role = DrumRole(subdir.name)
        except ValueError:
            role = mapping.get(subdir.name)

        if not role:
            continue

        for wav_path in sorted(subdir.glob("*.wav")):
            y, _ = load_audio(wav_path, sr=sr)
            kit[role].append(y)

    if not kit[DrumRole.CORE] and kit[DrumRole.FILL]:
        kit[DrumRole.CORE] = kit[DrumRole.FILL]

    logger.info(
        "Loaded kit roles: " + ", ".join(f"{r.value}={len(s)}" for r, s in kit.items())
    )
    return kit


def apply_reverb(y: np.ndarray, sr: int, length: float = 1.2, decay: float = 0.5) -> np.ndarray:
    samples = int(length * sr)
    ir = np.random.randn(samples) * np.exp(-np.linspace(0, 8, samples))
    ir = ir / np.max(np.abs(ir)) * 0.15

    from scipy.signal import fftconvolve

    reverb = fftconvolve(y, ir, mode="full")

    mix_len = max(len(y), len(reverb))
    output = np.zeros(mix_len, dtype=np.float32)

    output[:len(y)] += y
    output[:len(reverb)] += reverb

    return output


def render_event_grid(
    grid: EventGrid,
    kit: Dict[DrumRole, List[np.ndarray]],
    sr: int = 44100,
    reverb: bool = False,
) -> np.ndarray:
    total_beats = grid.bars * 4
    total_duration = total_beats * grid.t_beat

    tail_s = 2.0 if reverb else 0.5
    total_samples = int((total_duration + tail_s) * sr)
    output = np.zeros(total_samples, dtype=np.float32)

    for event in grid.events:
        if event.role not in kit or not kit[event.role]:
            continue

        samples_pool = kit[event.role]
        sample = random.choice(samples_pool)

        scaled = sample * event.vel

        t_start = grid.event_time(event)
        pos = int(round(t_start * sr))

        if pos >= total_samples:
            continue

        end = min(pos + len(scaled), total_samples)
        segment = scaled[: end - pos]
        output[pos:end] += segment

    if reverb:
        output = apply_reverb(output, sr, length=1.2)

    peak = np.max(np.abs(output))
    if peak > 0.95:
        output = output * (0.95 / peak)

    return output


def render_and_save(
    grid: EventGrid,
    kit: Dict[DrumRole, List[np.ndarray]],
    output_path: Path,
    sr: int = 44100,
    reverb: bool = False,
) -> Path:
    audio = render_event_grid(grid, kit, sr, reverb)
    save_audio(output_path, audio, sr)
    logger.info(f"Rendered grid ({grid.bpm} BPM) -> {output_path}")
    return output_path
