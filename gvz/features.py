from pathlib import Path
from typing import Any, Dict, List, Tuple

import librosa
import numpy as np

from .io_utils import safe_relpath


def _segment_features(y: np.ndarray, sr: int) -> Dict[str, float]:
    if y.size == 0:
        return {"zcr": 0.0, "harm_ratio": 0.0, "rms": 0.0}
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(y=y)))
    rms = float(np.mean(librosa.feature.rms(y=y)))
    y_h, y_p = librosa.effects.hpss(y)
    harm_energy = float(np.sum(y_h ** 2))
    total_energy = float(np.sum(y ** 2)) + 1e-12
    harm_ratio = harm_energy / total_energy
    return {"zcr": zcr, "harm_ratio": harm_ratio, "rms": rms}


def _classify_segments(
    y: np.ndarray,
    sr: int,
    top_db: float = 40.0,
    transient_max_s: float = 2.0,
    zcr_high: float = 0.15,
    harm_ratio_speech: float = 0.3,
) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    intervals = librosa.effects.split(y, top_db=top_db)
    speech_segments: List[Tuple[float, float]] = []
    transient_segments: List[Tuple[float, float]] = []

    for start, end in intervals:
        seg = y[start:end]
        duration = (end - start) / sr
        feats = _segment_features(seg, sr)
        is_transient = duration < transient_max_s and feats["zcr"] >= zcr_high and feats["harm_ratio"] < harm_ratio_speech
        is_speech = duration >= transient_max_s and feats["harm_ratio"] >= harm_ratio_speech
        if is_transient:
            transient_segments.append((start / sr, end / sr))
        elif is_speech:
            speech_segments.append((start / sr, end / sr))

    return speech_segments, transient_segments


def classify_segments(y: np.ndarray, sr: int) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    return _classify_segments(y, sr)


def extract_features(args: Tuple[str, str, int, int, bool]) -> Dict[str, Any]:
    path_str, root_str, sr, n_mfcc, use_harmonic = args
    path = Path(path_str)
    root = Path(root_str)

    try:
        y, _ = librosa.load(path, sr=sr, mono=True)
        if y.size == 0:
            return {
                "path": str(path),
                "rel_path": safe_relpath(path, root),
                "duration": 0.0,
                "score": None,
                "mfcc_mean": None,
                "error": "empty audio",
            }

        speech_segments, transient_segments = _classify_segments(y, sr)

        if use_harmonic:
            y = librosa.effects.hpss(y)[0]

        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc)
        delta_mfcc = librosa.feature.delta(mfcc)
        score = float(np.mean(np.abs(delta_mfcc)))
        mfcc_mean = np.mean(mfcc, axis=1).astype(float).tolist()
        duration = float(librosa.get_duration(y=y, sr=sr))

        zcr_full = float(np.mean(librosa.feature.zero_crossing_rate(y=y)))

        return {
            "path": str(path),
            "rel_path": safe_relpath(path, root),
            "duration": duration,
            "score": score,
            "mfcc_mean": mfcc_mean,
            "zcr": zcr_full,
            "speech_segments": speech_segments,
            "transient_segments": transient_segments,
            "error": None,
        }
    except Exception as exc:
        return {
            "path": str(path),
            "rel_path": safe_relpath(path, root),
            "duration": None,
            "score": None,
            "mfcc_mean": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
