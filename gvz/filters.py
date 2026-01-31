from typing import Optional

import numpy as np
import librosa
from scipy.signal import butter, filtfilt, iirnotch, sosfiltfilt


def highpass_filter(y: np.ndarray, sr: int, cutoff_hz: Optional[float], order: int = 4) -> np.ndarray:
    if cutoff_hz is None:
        return y
    nyq = 0.5 * sr
    if cutoff_hz >= nyq or cutoff_hz <= 0:
        return y
    b, a = butter(order, cutoff_hz / nyq, btype="high")
    return filtfilt(b, a, y).astype(y.dtype, copy=False)


def lowpass_filter(y: np.ndarray, sr: int, cutoff_hz: Optional[float], order: int = 8) -> np.ndarray:
    if cutoff_hz is None:
        return y
    nyq = 0.5 * sr
    if cutoff_hz >= nyq or cutoff_hz <= 0:
        return y
    b, a = butter(order, cutoff_hz / nyq, btype="low")
    return filtfilt(b, a, y).astype(y.dtype, copy=False)


def peaking_eq(y: np.ndarray, sr: int, center_hz: float, gain_db: float, q: float = 1.0) -> np.ndarray:
    if gain_db == 0.0:
        return y
    if center_hz <= 0 or center_hz >= 0.5 * sr:
        return y
    a = 10 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * (center_hz / sr)
    alpha = np.sin(w0) / (2.0 * q)

    b0 = 1.0 + alpha * a
    b1 = -2.0 * np.cos(w0)
    b2 = 1.0 - alpha * a
    a0 = 1.0 + alpha / a
    a1 = -2.0 * np.cos(w0)
    a2 = 1.0 - alpha / a

    sos = np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])
    return sosfiltfilt(sos, y).astype(y.dtype, copy=False)


def notch_filter(y: np.ndarray, sr: int, center_hz: Optional[float], q: float = 30.0) -> np.ndarray:
    if center_hz is None:
        return y
    if center_hz <= 0 or center_hz >= 0.5 * sr:
        return y
    b, a = iirnotch(center_hz / (0.5 * sr), q)
    return filtfilt(b, a, y).astype(y.dtype, copy=False)


def noise_gate(
    y: np.ndarray,
    sr: int,
    threshold_db: float = -40.0,
    attack_ms: float = 10.0,
    release_ms: float = 100.0,
    frame_length: int = 2048,
    hop_length: int = 512,
) -> np.ndarray:
    if y.size == 0:
        return y
    rms = np.sqrt(
        np.mean(
            librosa.util.frame(y, frame_length=frame_length, hop_length=hop_length) ** 2,
            axis=0,
        )
    )
    rms_db = 20.0 * np.log10(rms + 1e-12)
    target = (rms_db >= threshold_db).astype(float)

    attack_coeff = np.exp(-1.0 / max(1.0, (attack_ms / 1000.0) * sr / hop_length))
    release_coeff = np.exp(-1.0 / max(1.0, (release_ms / 1000.0) * sr / hop_length))

    gain = np.zeros_like(target)
    for i in range(len(target)):
        if i == 0:
            gain[i] = target[i]
            continue
        if target[i] > gain[i - 1]:
            gain[i] = attack_coeff * gain[i - 1] + (1.0 - attack_coeff) * target[i]
        else:
            gain[i] = release_coeff * gain[i - 1] + (1.0 - release_coeff) * target[i]

    gain_samples = np.repeat(gain, hop_length)
    if gain_samples.size < y.size:
        gain_samples = np.pad(gain_samples, (0, y.size - gain_samples.size), mode="edge")
    gain_samples = gain_samples[: y.size]
    return (y * gain_samples).astype(y.dtype, copy=False)


def estimate_noise_db(y: np.ndarray, sr: int, window_sec: float = 0.5) -> float:
    if y.size == 0:
        return -120.0
    window_len = int(max(1, window_sec * sr))
    window = y[:window_len]
    rms = np.sqrt(np.mean(window ** 2) + 1e-12)
    return 20.0 * np.log10(rms + 1e-12)


def deesser(
    y: np.ndarray,
    sr: int,
    freq_low: float = 4000.0,
    freq_high: float = 10000.0,
    threshold_db: float = -30.0,
    ratio: float = 4.0,
    attack_ms: float = 5.0,
    release_ms: float = 80.0,
    frame_length: int = 2048,
    hop_length: int = 512,
) -> np.ndarray:
    if y.size == 0:
        return y
    nyq = 0.5 * sr
    if freq_low <= 0 or freq_high <= 0 or freq_low >= freq_high or freq_high >= nyq:
        return y

    b, a = butter(4, [freq_low / nyq, freq_high / nyq], btype="band")
    band = filtfilt(b, a, y).astype(y.dtype, copy=False)

    rms = np.sqrt(
        np.mean(
            librosa.util.frame(band, frame_length=frame_length, hop_length=hop_length) ** 2,
            axis=0,
        )
    )
    rms_db = 20.0 * np.log10(rms + 1e-12)
    over_db = np.maximum(rms_db - threshold_db, 0.0)
    gain_db = -over_db * (1.0 - 1.0 / max(ratio, 1e-6))
    target = 10.0 ** (gain_db / 20.0)

    attack_coeff = np.exp(-1.0 / max(1.0, (attack_ms / 1000.0) * sr / hop_length))
    release_coeff = np.exp(-1.0 / max(1.0, (release_ms / 1000.0) * sr / hop_length))

    gain = np.zeros_like(target)
    for i in range(len(target)):
        if i == 0:
            gain[i] = target[i]
            continue
        if target[i] < gain[i - 1]:
            gain[i] = attack_coeff * gain[i - 1] + (1.0 - attack_coeff) * target[i]
        else:
            gain[i] = release_coeff * gain[i - 1] + (1.0 - release_coeff) * target[i]

    gain_samples = np.repeat(gain, hop_length)
    if gain_samples.size < y.size:
        gain_samples = np.pad(gain_samples, (0, y.size - gain_samples.size), mode="edge")
    gain_samples = gain_samples[: y.size]

    band_reduced = band * gain_samples
    return (y - band + band_reduced).astype(y.dtype, copy=False)


def spectral_denoise(
    y: np.ndarray,
    sr: int,
    n_fft: int = 2048,
    hop_length: int = 512,
    noise_quantile: float = 0.2,
    prop_decrease: float = 0.7,
    freq_smooth_hz: float = 0.0,
    noise_profile_sec: Optional[float] = None,
    time_smooth_frames: int = 0,
) -> np.ndarray:
    if y.size == 0:
        return y
    stft = librosa.stft(y, n_fft=n_fft, hop_length=hop_length)
    mag, phase = np.abs(stft), np.exp(1j * np.angle(stft))

    if noise_profile_sec is not None and noise_profile_sec > 0:
        frames = int((noise_profile_sec * sr) / hop_length)
        frames = max(1, min(frames, mag.shape[1]))
        noise_mag = np.median(mag[:, :frames], axis=1, keepdims=True)
    else:
        frame_rms = np.sqrt(np.mean(mag**2, axis=0))
        thresh = np.quantile(frame_rms, noise_quantile)
        noise_frames = frame_rms <= thresh
        if np.any(noise_frames):
            noise_mag = np.median(mag[:, noise_frames], axis=1, keepdims=True)
        else:
            noise_mag = np.quantile(mag, noise_quantile, axis=1, keepdims=True)
    if freq_smooth_hz > 0:
        bins = max(1, int(freq_smooth_hz / (sr / n_fft)))
        kernel = np.ones(bins, dtype=float) / bins
        noise_mag = np.convolve(noise_mag[:, 0], kernel, mode="same")[:, None]

    reduced = mag - noise_mag * prop_decrease
    reduced = np.maximum(reduced, 0.0)
    if time_smooth_frames and time_smooth_frames > 1:
        kernel = np.ones(time_smooth_frames, dtype=float) / time_smooth_frames
        reduced = np.apply_along_axis(lambda x: np.convolve(x, kernel, mode="same"), 1, reduced)
    stft_out = reduced * phase
    y_out = librosa.istft(stft_out, hop_length=hop_length, length=y.size)
    return y_out.astype(y.dtype, copy=False)
