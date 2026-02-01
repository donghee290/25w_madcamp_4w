"""Sequencer module for rendering EventGrid to audio."""

import random
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from .utils import logger, load_audio, save_audio
from .scoring import DrumRole
from .events import EventGrid, DrumEvent

def load_kit(kit_dir: Path, sr: int = 44100) -> Dict[DrumRole, List[np.ndarray]]:
    """Load drum kit using analyze_kit logic to assign roles on the fly if needed.
       For now, we assume folders are named by roles if possible, or we re-map old folders.
    """
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

    # Load from subdirectories
    for subdir in kit_dir.iterdir():
        if not subdir.is_dir():
            continue

        role = None
        try:
            role = DrumRole(subdir.name)
        except ValueError:
            role = mapping.get(subdir.name)

        if not role:
            continue

        for wav_path in sorted(subdir.glob("*.wav")):
            y, _ = load_audio(wav_path, sr=sr)
            kit[role].append(y)

    # Fallback: if a role is empty, borrow from nearest neighbor
    if not kit[DrumRole.CORE]:
        if kit[DrumRole.FILL]:
            kit[DrumRole.CORE] = kit[DrumRole.FILL]
    
    logger.info(f"Loaded kit roles: {', '.join(f'{r.value}={len(s)}' for r, s in kit.items())}")
    return kit

def apply_reverb(y: np.ndarray, sr: int, length: float = 1.2, decay: float = 0.5) -> np.ndarray:
    """Simple synthetic reverb using decaying noise convolution."""
    samples = int(length * sr)
    ir = np.random.randn(samples) * np.exp(-np.linspace(0, 8, samples)) 
    ir = ir / np.max(np.abs(ir)) * 0.15

    from scipy.signal import fftconvolve
    reverb = fftconvolve(y, ir, mode='full')

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
    """Render an EventGrid to audio."""
    
    # Calculate total duration including potential reverb tail
    total_beats = grid.bars * 4
    total_duration = total_beats * grid.t_beat
    
    tail_s = 2.0 if reverb else 0.5
    total_samples = int((total_duration + tail_s) * sr)
    output = np.zeros(total_samples, dtype=np.float32)

    for event in grid.events:
        if event.role not in kit or not kit[event.role]:
            continue
            
        # Select sample (naive round-robin or random based on sample_id??)
        # Here we just pick random for now as sample_id mapping is complex without a loaded map
        samples_pool = kit[event.role]
        sample = random.choice(samples_pool)
        
        # Apply volume
        scaled = sample * event.vel
        
        # Calculate start position
        t_start = grid.event_time(event)
        pos = int(round(t_start * sr))
        
        if pos >= total_samples:
            continue
            
        end = min(pos + len(scaled), total_samples)
        segment = scaled[:end-pos]
        output[pos:end] += segment

    # Apply Reverb
    if reverb:
        output = apply_reverb(output, sr, length=1.2)

    # Normalize
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
    """Render EventGrid and save to WAV."""
    audio = render_event_grid(grid, kit, sr, reverb)
    save_audio(output_path, audio, sr)
    logger.info(f"Rendered grid ({grid.bpm} BPM) -> {output_path}")
    return output_path
