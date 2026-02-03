"""Rule-based 8-class drum hit classifier."""

from typing import Optional

import librosa
import numpy as np

from .config import DrumClass, ClassifierThresholds
from .utils import logger


def _extract_features(y: np.ndarray, sr: int) -> dict:
    """Extract spectral features from a single drum hit."""
    if y.size == 0:
        return {}

    # Spectral centroid
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    centroid_mean = float(np.mean(centroid))

    # Spectral bandwidth
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)
    bandwidth_mean = float(np.mean(bandwidth))

    # Zero crossing rate
    zcr = librosa.feature.zero_crossing_rate(y=y)
    zcr_mean = float(np.mean(zcr))

    # RMS energy
    rms = librosa.feature.rms(y=y)
    rms_mean = float(np.mean(rms))

    # Spectral rolloff
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)
    rolloff_mean = float(np.mean(rolloff))

    # Duration
    duration = len(y) / sr

    # pYIN pitch estimation (optimization: specific range only)
    pitch = None
    # Only run pYIN if centroid indicates potential tom (approx 80-1000Hz)
    # or if we want to distinguish low-pitched drums
    if 50.0 < centroid_mean < 1000.0:
        try:
            f0, voiced_flag, _ = librosa.pyin(
                y, fmin=60.0, fmax=600.0, sr=sr,
            )
            voiced_f0 = f0[voiced_flag]
            if len(voiced_f0) > 0:
                pitch = float(np.median(voiced_f0))
        except Exception:
            pass

    # MFCC (first 5)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=5)
    mfcc_mean = np.mean(mfcc, axis=1).tolist()

    return {
        "centroid": centroid_mean,
        "bandwidth": bandwidth_mean,
        "zcr": zcr_mean,
        "rms": rms_mean,
        "rolloff": rolloff_mean,
        "duration": duration,
        "pitch": pitch,
        "mfcc": mfcc_mean,
    }


def classify_hit(
    y: np.ndarray,
    sr: int,
    thresholds: Optional[ClassifierThresholds] = None,
) -> DrumClass:
    """Classify a single drum hit into one of 8 classes + UNKNOWN.

    Uses rule-based approach with spectral features and pYIN pitch.
    """
    if thresholds is None:
        thresholds = ClassifierThresholds()

    feats = _extract_features(y, sr)
    if not feats:
        return DrumClass.UNKNOWN

    centroid = feats["centroid"]
    zcr = feats["zcr"]
    duration = feats["duration"]
    pitch = feats["pitch"]
    bandwidth = feats["bandwidth"]

    # --- Hi-hat: very high centroid + very high ZCR ---
    if centroid > thresholds.hihat_centroid_min and zcr > thresholds.hihat_zcr_min:
        return DrumClass.HIHAT

    # --- Crash: high centroid + long duration ---
    if centroid > thresholds.crash_centroid_min and duration > thresholds.crash_duration_min:
        return DrumClass.CRASH

    # --- Ride: high centroid + medium ZCR + shorter duration ---
    if (centroid > thresholds.ride_centroid_min
            and zcr < thresholds.ride_zcr_max
            and duration < thresholds.ride_duration_max):
        return DrumClass.RIDE

    # --- Kick: very low centroid + low ZCR ---
    if centroid < thresholds.kick_centroid_max and zcr < thresholds.kick_zcr_max:
        return DrumClass.KICK

    # --- Snare: mid centroid + high ZCR ---
    if (thresholds.snare_centroid_min <= centroid <= thresholds.snare_centroid_max
            and zcr > thresholds.snare_zcr_min):
        return DrumClass.SNARE

    # --- Toms: mid-low centroid + low ZCR, differentiated by pitch ---
    if (thresholds.tom_centroid_min <= centroid <= thresholds.tom_centroid_max
            and zcr < thresholds.tom_zcr_max):
        if pitch is not None:
            if thresholds.ltom_pitch_min <= pitch < thresholds.ltom_pitch_max:
                return DrumClass.LTOM
            elif thresholds.rtom_pitch_min <= pitch < thresholds.rtom_pitch_max:
                return DrumClass.RTOM
            elif thresholds.rowtom_pitch_min <= pitch < thresholds.rowtom_pitch_max:
                return DrumClass.ROWTOM

        # Fallback: classify by centroid if pitch unavailable
        if centroid < 300:
            return DrumClass.LTOM
        elif centroid < 500:
            return DrumClass.RTOM
        else:
            return DrumClass.ROWTOM

    # --- Fallback: try broader matching ---
    # Low frequency => likely kick
    if centroid < 500 and zcr < 0.1:
        return DrumClass.KICK

    # High frequency => likely hihat/cymbal
    if centroid > 4000:
        if duration > 0.3:
            return DrumClass.CRASH
        return DrumClass.HIHAT

    # Mid frequency with high ZCR => snare
    if zcr > 0.1:
        return DrumClass.SNARE

    return DrumClass.UNKNOWN


def classify_hit_verbose(
    y: np.ndarray,
    sr: int,
    thresholds: Optional[ClassifierThresholds] = None,
) -> dict:
    """Classify with full feature details for debugging."""
    if thresholds is None:
        thresholds = ClassifierThresholds()

    feats = _extract_features(y, sr)
    label = classify_hit(y, sr, thresholds)

    return {
        "class": label.value,
        "features": feats,
    }
