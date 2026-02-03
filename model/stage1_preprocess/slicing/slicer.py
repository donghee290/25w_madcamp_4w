"""One-shot drum hit extraction and kit organization."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import librosa
import numpy as np

from ..cleaning.dedup import deduplicate_hits
from ..io.utils import logger, save_audio, ensure_dir


def slice_hits(
    y_drums: np.ndarray,
    sr: int,
    onsets: List[int],
    max_duration_s: float = 2.0,
    fade_out_ms: float = 50.0,
    trim_db: float = 60.0,
    min_duration_s: float = 0.05,
) -> List[np.ndarray]:
    """Extract individual drum hits from onset positions.

    Each hit spans from onset to min(next_onset, onset+max_duration).
    A minimum duration is guaranteed so release tails are preserved.
    Applies fade-out and trims trailing silence.
    """
    hits = []
    fade_samples = int(fade_out_ms / 1000.0 * sr)
    max_samples = int(max_duration_s * sr)
    min_samples = int(min_duration_s * sr)

    for i, onset in enumerate(onsets):
        # End = next onset or onset + max_duration, but at least min_duration
        if i + 1 < len(onsets):
            next_onset = onsets[i + 1]
            end = min(max(next_onset, onset + min_samples), onset + max_samples)
        else:
            end = min(onset + max_samples, len(y_drums))

        end = min(end, len(y_drums))
        hit = y_drums[onset:end].copy()

        if hit.size == 0:
            continue

        # Trim trailing silence
        trimmed, _ = librosa.effects.trim(hit, top_db=trim_db)
        if trimmed.size < int(0.005 * sr):  # Less than 5ms: skip
            continue

        # Apply fade-out
        if fade_samples > 0 and fade_samples < len(trimmed):
            fade = np.linspace(1.0, 0.0, fade_samples)
            trimmed[-fade_samples:] *= fade

        hits.append(trimmed)

    logger.info(f"Sliced {len(hits)} hits from {len(onsets)} onsets")
    return hits


def normalize_hit(y: np.ndarray, target_db: float = -1.0) -> np.ndarray:
    """Peak normalize a hit to target dB."""
    peak = np.max(np.abs(y))
    if peak < 1e-8:
        return y
    target_amp = 10.0 ** (target_db / 20.0)
    return y * (target_amp / peak)


def save_samples(
    hits: List[np.ndarray],
    sr: int,
    output_dir: Path,
    file_stem: str = "sample",
    normalize: bool = True,
) -> List[Path]:
    """Save hits to output_dir with naming {file_stem}_{i}.wav."""
    output_dir = ensure_dir(output_dir)
    saved_paths = []
    
    for i, hit in enumerate(hits, start=1):
        if normalize:
            hit = normalize_hit(hit)

        fname = f"{file_stem}_{i:03d}.wav"
        out_path = output_dir / fname
        save_audio(out_path, hit, sr)
        saved_paths.append(out_path)

    logger.info(f"Saved {len(saved_paths)} samples to {output_dir}")
    return saved_paths


def extract_samples(
    y_drums: np.ndarray,
    sr: int,
    onsets: List[int],
    output_dir: Path,
    file_stem: str,
    max_duration_s: float = 2.0,
    fade_out_ms: float = 50.0,
    trim_db: float = 60.0,
    min_hit_duration_s: float = 0.0,
    dedup_enabled: bool = True,
    dedup_threshold: float = 0.5,
) -> List[Path]:
    """Full pipeline: slice -> filter -> dedup -> save."""
    hits = slice_hits(y_drums, sr, onsets, max_duration_s, fade_out_ms, trim_db)

    min_samples = int(min_hit_duration_s * sr)
    hits = [h for h in hits if len(h) >= min_samples]

    representatives = hits
    # dedup_stats unused in flat output
    if dedup_enabled:
        representatives, _ = deduplicate_hits(hits, sr, threshold=dedup_threshold)

    return save_samples(representatives, sr, output_dir, file_stem=file_stem)
