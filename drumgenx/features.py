"""DSP Feature Extraction for One-Shot Drum Samples."""

import librosa
import numpy as np
from typing import Dict, Tuple

def extract_dsp_features(y: np.ndarray, sr: int) -> Dict[str, float]:
    """Extract DSP features for rule-based classification.
    
    Returns a dictionary with:
    - energy (E): 0-1 normalized
    - sharpness (S): 0-1 transient strength
    - band_ratios (L, M, H): tuple summing to 1
    - attack_time (A): seconds
    - decay_time (D): seconds
    """
    if len(y) == 0:
        return {
            "energy": 0.0, "sharpness": 0.0,
            "band_low": 0.0, "band_mid": 0.0, "band_high": 0.0,
            "attack_time": 0.0, "decay_time": 0.0
        }

    # 1. Energy (RMS peak)
    rms = librosa.feature.rms(y=y, frame_length=512, hop_length=128)[0]
    energy_raw = np.max(rms) 
    # Normalize broadly (assumption: -1dB peak normalized inputs roughly)
    energy = np.clip(energy_raw, 0, 1)

    # 2. Sharpness (Spectral Flux Peak / Onset Strength)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    sharpness_raw = np.max(onset_env)
    # Normalize: empirically, strong inputs might hit 10-20. 
    sharpness = np.clip(sharpness_raw / 15.0, 0, 1)

    # 3. Band Energy Ratio (L/M/H)
    # Low: < 300 Hz
    # Mid: 300 - 4000 Hz
    # High: > 4000 Hz
    spec = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)
    
    idx_low_end = np.searchsorted(freqs, 300)
    idx_mid_end = np.searchsorted(freqs, 4000)
    
    e_low = np.sum(spec[:idx_low_end, :])
    e_mid = np.sum(spec[idx_low_end:idx_mid_end, :])
    e_high = np.sum(spec[idx_mid_end:, :])
    
    total_e = e_low + e_mid + e_high + 1e-8
    l_ratio = e_low / total_e
    m_ratio = e_mid / total_e
    h_ratio = e_high / total_e

    # 4. Attack / Decay Time
    # Envelope via Hilbert or RMS
    # Simple approach: time to peak, time from peak to -20dB (or noise floor)
    env = librosa.feature.rms(y=y, frame_length=256, hop_length=64)[0]
    peak_idx = np.argmax(env)
    peak_time_s = peak_idx * 64 / sr
    
    attack_time = peak_time_s
    
    # Decay: find time after peak where it drops below threshold (e.g. 10% of peak)
    threshold = env[peak_idx] * 0.1
    decay_frames = 0
    for i in range(peak_idx, len(env)):
        if env[i] < threshold:
            decay_frames = i - peak_idx
            break
    else:
        decay_frames = len(env) - peak_idx
        
    decay_time = decay_frames * 64 / sr

    return {
        "energy": float(energy),
        "sharpness": float(sharpness),
        "band_low": float(l_ratio),
        "band_mid": float(m_ratio),
        "band_high": float(h_ratio),
        "attack_time": float(attack_time),
        "decay_time": float(decay_time)
    }
