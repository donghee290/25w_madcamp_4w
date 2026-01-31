"""Multi-band onset detection for drum hits."""

from typing import List, Tuple

import librosa
import numpy as np
from scipy.signal import butter, filtfilt

from .utils import logger


def _bandpass(y: np.ndarray, sr: int, low: float, high: float, order: int = 4) -> np.ndarray:
    """Apply bandpass filter using SOS for stability."""
    nyq = 0.5 * sr
    low_n = np.clip(low / nyq, 1e-6, 0.9999)
    high_n = np.clip(high / nyq, 1e-6, 0.9999)

    if low_n >= high_n:
        return y

    try:
        sos = butter(order, [low_n, high_n], btype="band", output="sos")
        from scipy.signal import sosfiltfilt
        y_filt = sosfiltfilt(sos, y).astype(y.dtype)

        if not np.isfinite(y_filt).all():
            logger.warning(f"Bandpass {low}-{high}Hz produced non-finite values. Using original signal.")
            return y

        return y_filt
    except Exception as e:
        logger.warning(f"Bandpass filter failed: {e}. Using original signal.")
        return y


def _detect_band_onsets(
    y: np.ndarray,
    sr: int,
    backtrack: bool = True,
    delta: float = 0.07,
) -> np.ndarray:
    """Detect onsets in a single band. Returns onset sample positions."""
    if np.max(np.abs(y)) < 1e-6:
        return np.array([], dtype=int)

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(
        y=y, sr=sr,
        onset_envelope=onset_env,
        backtrack=backtrack,
        delta=delta,
    )
    return librosa.frames_to_samples(onset_frames)


def detect_onsets(
    y_drums: np.ndarray,
    sr: int,
    merge_ms: float = 30.0,
    backtrack: bool = True,
) -> List[int]:
    """Multi-band onset detection on drum audio.

    Splits into 4 frequency bands, detects onsets in each,
    then merges onsets within merge_ms window.

    Returns sorted list of onset sample positions.
    """
    bands: List[Tuple[float, float, float]] = [
        (20.0, 100.0, 0.05),    # sub-bass (kicks)
        (100.0, 500.0, 0.06),   # low (toms, body)
        (500.0, 4000.0, 0.07),  # mid (snare, attack)
        (4000.0, min(sr / 2 - 1, 16000.0), 0.05),  # high (cymbals)
    ]

    all_onsets = []
    for low, high, delta in bands:
        y_band = _bandpass(y_drums, sr, low, high)
        onsets = _detect_band_onsets(y_band, sr, backtrack=backtrack, delta=delta)
        all_onsets.extend(onsets.tolist())
        logger.debug(f"  Band {low}-{high}Hz: {len(onsets)} onsets")

    if not all_onsets:
        # Fallback: detect on full signal
        logger.info("No band onsets found, falling back to full-signal detection")
        onsets = _detect_band_onsets(y_drums, sr, backtrack=backtrack, delta=0.05)
        all_onsets = onsets.tolist()

    # Sort and merge close onsets
    all_onsets.sort()
    merge_samples = int(merge_ms / 1000.0 * sr)

    merged = []
    for onset in all_onsets:
        if merged and onset - merged[-1] < merge_samples:
            continue  # Skip: too close to previous
        merged.append(onset)

    logger.info(f"Detected {len(merged)} onsets (from {len(all_onsets)} raw)")
    return merged


def onset_strengths(y: np.ndarray, sr: int) -> np.ndarray:
    """Compute onset strength envelope for visualization."""
    return librosa.onset.onset_strength(y=y, sr=sr)
