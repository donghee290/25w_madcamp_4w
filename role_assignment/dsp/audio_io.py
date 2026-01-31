from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import librosa


@dataclass
class AudioLoadConfig:
    target_sr: int = 16000
    mono: bool = True
    max_duration_sec: float = 2.0

    trim_silence: bool = True
    trim_top_db: int = 30

    peak_normalize: bool = True
    peak_target: float = 0.95


def load_audio(
    filepath: str | Path,
    cfg: AudioLoadConfig,
) -> Tuple[np.ndarray, int]:
    """
    오디오 로드 + 표준화:
    - librosa.load로 로드(리샘플 포함)
    - mono 변환
    - max_duration_sec로 컷
    - trim_silence(선택)
    - peak normalize(선택)
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    # duration을 librosa.load에서 직접 제한하면 메모리/시간이 절약됨
    duration = None
    if cfg.max_duration_sec and cfg.max_duration_sec > 0:
        duration = float(cfg.max_duration_sec)

    y, sr = librosa.load(
        str(path),
        sr=cfg.target_sr,
        mono=cfg.mono,
        duration=duration,
    )

    # librosa는 보통 float32로 반환하지만, 안전하게 float32로 맞춤
    if y.dtype != np.float32:
        y = y.astype(np.float32, copy=False)

    # 너무 짧거나 빈 경우 방어
    if y.size == 0:
        y = np.zeros((1,), dtype=np.float32)

    # 무음 트림
    if cfg.trim_silence:
        y = trim_silence(y, top_db=cfg.trim_top_db)

    # peak normalize
    if cfg.peak_normalize:
        y = peak_normalize(y, target_peak=cfg.peak_target)

    return y, sr


def trim_silence(y: np.ndarray, top_db: int = 30) -> np.ndarray:
    """
    앞/뒤 무음을 잘라 원샷의 onset을 더 명확히 만듭니다.
    """
    if y.size < 4:
        return y

    yt, _ = librosa.effects.trim(y, top_db=top_db)

    # trim 결과가 너무 짧아지는 경우 방어
    if yt.size < 8:
        return y
    return yt.astype(np.float32, copy=False)


def peak_normalize(y: np.ndarray, target_peak: float = 0.95) -> np.ndarray:
    """
    peak를 target_peak로 맞추는 단순 정규화.
    - 너무 작은 신호는 스킵
    """
    if y.size == 0:
        return y

    peak = float(np.max(np.abs(y)))
    if peak < 1e-6:
        return y

    scale = target_peak / peak
    y2 = y * scale

    # 안전 클리핑 (혹시 초과하면 제한)
    y2 = np.clip(y2, -1.0, 1.0)

    return y2.astype(np.float32, copy=False)


def ensure_min_length(y: np.ndarray, sr: int, min_sec: float = 0.05) -> np.ndarray:
    """
    너무 짧은 오디오는 특징 추출이 불안정하므로 최소 길이를 보장합니다.
    - 모자라면 0 padding
    """
    min_len = int(sr * min_sec)
    if y.size >= min_len:
        return y
    pad = min_len - y.size
    return np.pad(y, (0, pad), mode="constant").astype(np.float32, copy=False)


def slice_max_duration(y: np.ndarray, sr: int, max_sec: Optional[float]) -> np.ndarray:
    """
    max_sec 기준으로 오디오를 앞에서부터 자릅니다.
    """
    if not max_sec or max_sec <= 0:
        return y
    max_len = int(sr * float(max_sec))
    if y.size <= max_len:
        return y
    return y[:max_len].astype(np.float32, copy=False)