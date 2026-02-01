from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import librosa

from ..types import DSPFeatures


@dataclass
class DSPConfig:
    frame_length: int = 1024
    hop_length: int = 256

    # band ratios
    band_edges_hz: Dict[str, Tuple[float, float]] = None

    # attack/decay windows
    attack_window_sec: float = 0.08
    decay_window_sec: float = 0.60

    def __post_init__(self):
        if self.band_edges_hz is None:
            self.band_edges_hz = {
                "low": (20.0, 150.0),
                "mid": (150.0, 2000.0),
                "high": (2000.0, 8000.0),
            }


def extract_features(y: np.ndarray, sr: int, cfg: DSPConfig) -> DSPFeatures:
    """
    원샷 오디오에서 역할 판단에 필요한 DSP 특징들을 계산합니다.
    반환 값은 DSPFeatures(0~1 정규화 위주) 입니다.
    """
    y = _to_mono_float32(y)

    # STFT magnitude
    S = np.abs(librosa.stft(y, n_fft=cfg.frame_length, hop_length=cfg.hop_length, center=True))
    # power spectrogram
    P = S**2

    # -----------------------
    # (1) Energy / RMS
    # -----------------------
    rms_frames = librosa.feature.rms(S=S, frame_length=cfg.frame_length, hop_length=cfg.hop_length)[0]
    rms = float(np.max(rms_frames)) if rms_frames.size else 0.0

    # energy는 peak 기반으로 0~1로 이미 거의 들어오지만, 안정적으로 clip
    energy = _clip01(rms)

    # -----------------------
    # (2) Sharpness = spectral flux peak
    # -----------------------
    flux = _spectral_flux(S)
    sharpness = _clip01(float(np.max(flux)) if flux.size else 0.0)

    # -----------------------
    # (3) Band energy ratios (L/M/H)
    # -----------------------
    freqs = librosa.fft_frequencies(sr=sr, n_fft=cfg.frame_length)
    total_power = float(np.sum(P)) + 1e-12

    def band_power(f_lo: float, f_hi: float) -> float:
        idx = np.where((freqs >= f_lo) & (freqs < f_hi))[0]
        if idx.size == 0:
            return 0.0
        return float(np.sum(P[idx, :]))

    low_p = band_power(*cfg.band_edges_hz["low"])
    mid_p = band_power(*cfg.band_edges_hz["mid"])
    high_p = band_power(*cfg.band_edges_hz["high"])

    L = low_p / total_power
    M = mid_p / total_power
    H = high_p / total_power

    # 합이 1에 가깝도록 보정(대역 밖 에너지가 있을 수 있음)
    s = L + M + H
    if s > 1e-9:
        L, M, H = L / s, M / s, H / s
    else:
        L, M, H = 0.0, 0.0, 0.0

    # -----------------------
    # (4) Spectral flatness (noise-like)
    # -----------------------
    flat = librosa.feature.spectral_flatness(S=S)[0]
    spectral_flatness = _clip01(float(np.median(flat)) if flat.size else 0.0)

    # -----------------------
    # (5) Zero Crossing Rate (noise/high freq hint)
    # -----------------------
    zcr = librosa.feature.zero_crossing_rate(y, frame_length=cfg.frame_length, hop_length=cfg.hop_length)[0]
    zero_crossing_rate = _clip01(float(np.median(zcr)) if zcr.size else 0.0)

    # -----------------------
    # (6) Attack / Decay times (seconds)
    #     원샷: 가장 큰 onset 위치 기준으로 계산
    # -----------------------
    onset_frame = _estimate_onset_frame(rms_frames, flux)
    attack_time, decay_time = _attack_decay_from_envelope(
        rms_frames=rms_frames,
        sr=sr,
        hop_length=cfg.hop_length,
        onset_frame=onset_frame,
        attack_window_sec=cfg.attack_window_sec,
        decay_window_sec=cfg.decay_window_sec,
    )

    # attack/decay는 초 단위이지만, rule score에서 0~1로 정규화 사용(여기선 clip만)
    # 실제 정규화는 rule_scoring에서 window 기준으로 정규화할 수도 있으나,
    # MVP에서는 [0,1] 구간에 들어오도록 "1초" 기준 clip로 충분함.
    attack_norm = _clip01(attack_time)
    decay_norm = _clip01(decay_time)

    return DSPFeatures(
        energy=_clip01(energy),
        rms=_clip01(rms),
        sharpness=_clip01(sharpness),
        attack_time=attack_norm,
        decay_time=decay_norm,
        low_ratio=_clip01(L),
        mid_ratio=_clip01(M),
        high_ratio=_clip01(H),
        spectral_flatness=_clip01(spectral_flatness),
        zero_crossing_rate=_clip01(zero_crossing_rate),
    )


# =========================
# Helpers
# =========================

def _to_mono_float32(y: np.ndarray) -> np.ndarray:
    y = np.asarray(y)
    if y.ndim > 1:
        y = np.mean(y, axis=0)
    if y.dtype != np.float32:
        y = y.astype(np.float32, copy=False)
    return y


def _clip01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def _spectral_flux(S_mag: np.ndarray) -> np.ndarray:
    """
    spectral flux: 프레임 간 스펙트럼 증가량
    - onset의 날카로움/트랜지언트 강도 힌트
    """
    if S_mag.size == 0 or S_mag.shape[1] < 2:
        return np.zeros((0,), dtype=np.float32)

    # 프레임 간 차이(증가분만)
    diff = np.diff(S_mag, axis=1)
    diff = np.maximum(diff, 0.0)

    # 주파수 방향 합 -> flux per frame (원래 T-1 길이)
    flux = np.sum(diff, axis=0)

    # 안정화: 정규화(0~1 근처로)
    m = float(np.max(flux)) + 1e-12
    flux = flux / m
    return flux.astype(np.float32, copy=False)


def _estimate_onset_frame(rms_frames: np.ndarray, flux: np.ndarray) -> int:
    """
    onset 프레임을 추정합니다.
    - 원샷이라면 rms peak 또는 flux peak가 대체로 onset 근처
    - 둘을 섞어서 안정적으로 잡음
    """
    if rms_frames.size == 0 and flux.size == 0:
        return 0

    rms_idx = int(np.argmax(rms_frames)) if rms_frames.size else 0
    flux_idx = int(np.argmax(flux)) if flux.size else 0

    # flux는 (T-1) 길이일 수 있어서 +1 보정
    if flux.size and flux_idx < rms_frames.size:
        flux_frame = min(flux_idx + 1, rms_frames.size - 1)
    else:
        flux_frame = rms_idx

    # 둘 중 더 앞쪽을 onset으로 보는 편이 안전(원샷은 상승부가 중요)
    return int(min(rms_idx, flux_frame))


def _attack_decay_from_envelope(
    rms_frames: np.ndarray,
    sr: int,
    hop_length: int,
    onset_frame: int,
    attack_window_sec: float,
    decay_window_sec: float,
) -> Tuple[float, float]:
    """
    RMS envelope에서 attack/decay를 계산합니다.
    - attack: onset_frame 이전/근처 baseline 대비 peak의 90%에 도달하는데 걸린 시간
    - decay: peak 이후 peak의 30%로 떨어지는 데 걸린 시간
    """
    if rms_frames.size == 0:
        return 0.0, 0.0

    T = rms_frames.size
    onset_frame = int(np.clip(onset_frame, 0, T - 1))

    peak_frame = int(np.argmax(rms_frames))
    peak_val = float(rms_frames[peak_frame])

    if peak_val < 1e-8:
        return 0.0, 0.0

    # baseline: onset 직전 몇 프레임 평균(없으면 0)
    baseline_left = max(onset_frame - 3, 0)
    baseline = float(np.mean(rms_frames[baseline_left:onset_frame + 1])) if onset_frame > 0 else 0.0

    # attack target: baseline -> peak의 90% 지점
    attack_target = baseline + 0.90 * (peak_val - baseline)

    # attack search window: onset_frame ~ onset_frame + attack_window
    attack_max_frames = int((attack_window_sec * sr) / hop_length) + 1
    a_end = int(min(T - 1, onset_frame + attack_max_frames))

    attack_frame = onset_frame
    for i in range(onset_frame, a_end + 1):
        if float(rms_frames[i]) >= attack_target:
            attack_frame = i
            break

    attack_time = (attack_frame - onset_frame) * (hop_length / sr)

    # decay target: peak의 30%
    decay_target = 0.30 * peak_val

    # decay window: peak_frame ~ peak_frame + decay_window
    decay_max_frames = int((decay_window_sec * sr) / hop_length) + 1
    d_end = int(min(T - 1, peak_frame + decay_max_frames))

    decay_frame = d_end
    for i in range(peak_frame, d_end + 1):
        if float(rms_frames[i]) <= decay_target:
            decay_frame = i
            break

    decay_time = (decay_frame - peak_frame) * (hop_length / sr)

    # 안전: 음수 방지
    if attack_time < 0:
        attack_time = 0.0
    if decay_time < 0:
        decay_time = 0.0

    return float(attack_time), float(decay_time)