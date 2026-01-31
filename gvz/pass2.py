from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from .config import Pass2Config
from .filters import (
    deesser,
    estimate_noise_db,
    lowpass_filter,
    noise_gate,
    notch_filter,
    peaking_eq,
    spectral_denoise,
)
from .manifest import read_manifest
from .scoring import apply_gain


def pass2(config: Pass2Config) -> Path:
    entries = read_manifest(config.manifest_path)
    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        action = entry.get("action")
        if action != "suppress":
            continue

        src_path = Path(entry.get("path"))
        rel_path = entry.get("rel_path") or src_path.name
        dst_path = output_dir / rel_path
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        if dst_path.suffix.lower() not in {".wav", ".flac", ".ogg"}:
            dst_path = dst_path.with_suffix(".wav")

        y, _ = librosa.load(src_path, sr=config.sr, mono=True)
        gain_db = config.gain_db
        denoise_strength = config.denoise_strength
        deesser_threshold_db = config.deesser_threshold_db
        deesser_ratio = config.deesser_ratio

        if config.noise_split_enabled:
            noise_db = estimate_noise_db(y, config.sr, config.noise_window_sec)
            if noise_db >= config.noise_threshold_db:
                gain_db = config.noisy_gain_db
                denoise_strength = config.noisy_denoise_strength
                deesser_threshold_db = config.noisy_deesser_threshold_db
                deesser_ratio = config.noisy_deesser_ratio
            else:
                gain_db = config.clean_gain_db
                denoise_strength = config.clean_denoise_strength
                deesser_threshold_db = config.clean_deesser_threshold_db
                deesser_ratio = config.clean_deesser_ratio
        segments = entry.get("speech_segments") or []
        if segments:
            y_out = np.copy(y)
            for start_s, end_s in segments:
                start = int(float(start_s) * config.sr)
                end = int(float(end_s) * config.sr)
                y_out[start:end] = apply_gain(y_out[start:end], gain_db)
            y = y_out
        else:
            y = apply_gain(y, gain_db)

        y = lowpass_filter(y, config.sr, config.highcut_hz, config.highcut_order)
        y = notch_filter(y, config.sr, config.notch_hz, config.notch_q)
        y = peaking_eq(y, config.sr, 5000.0, config.eq_5k_db, config.eq_q)
        y = peaking_eq(y, config.sr, 10000.0, config.eq_10k_db, config.eq_q)
        if config.gate_enabled:
            y = noise_gate(
                y,
                config.sr,
                threshold_db=config.gate_threshold_db,
                attack_ms=config.gate_attack_ms,
                release_ms=config.gate_release_ms,
            )
        if config.denoise_enabled:
            y = spectral_denoise(
                y,
                config.sr,
                noise_quantile=config.denoise_quantile,
                prop_decrease=denoise_strength,
                noise_profile_sec=config.denoise_profile_sec,
                time_smooth_frames=config.denoise_time_smooth,
            )
        if config.deesser_enabled:
            y = deesser(
                y,
                config.sr,
                freq_low=config.deesser_low_hz,
                freq_high=config.deesser_high_hz,
                threshold_db=deesser_threshold_db,
                ratio=deesser_ratio,
                attack_ms=config.deesser_attack_ms,
                release_ms=config.deesser_release_ms,
            )
        sf.write(dst_path, y, config.sr)

    report_dir = config.manifest_path.parent
    return report_dir
