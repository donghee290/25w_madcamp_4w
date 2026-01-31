import json
import sys
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

import librosa
import numpy as np
import soundfile as sf

from .features import classify_segments
from .filters import (
    deesser,
    estimate_noise_db,
    highpass_filter,
    lowpass_filter,
    noise_gate,
    notch_filter,
    peaking_eq,
    spectral_denoise,
)
from .io_utils import safe_relpath
from .scoring import apply_gain, assign_action
from .splitter import detect_segments


def _run_demucs(src_path: Path, output_dir: Path, model: str, device: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "demucs",
        "--two-stems",
        "vocals",
        "-n",
        model,
        "-d",
        device,
        "-o",
        str(output_dir),
        str(src_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "Demucs failed. Ensure demucs is installed and accessible.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    model_dir = output_dir / model / src_path.stem
    accom_path = model_dir / "no_vocals.wav"
    if not accom_path.exists():
        raise RuntimeError("Demucs output not found: no_vocals.wav")
    return accom_path


def _save_audio(path: Path, y: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, y, sr)


def _nonsilent_segments(y: np.ndarray, sr: int) -> List[Tuple[float, float]]:
    intervals = librosa.effects.split(y, top_db=40)
    return [(start / sr, end / sr) for start, end in intervals]


def _process_chunk(
    y_chunk: np.ndarray,
    sr: int,
    n_mfcc: int,
    low_threshold: float,
    high_threshold: float,
    use_harmonic: bool,
    gain_db: float,
    primary_removal: str,
    highpass_hz: Optional[float],
    highpass_order: int,
    highcut_hz: Optional[float],
    highcut_order: int,
    notch_hz: Optional[float],
    notch_q: float,
    eq_5k_db: float,
    eq_10k_db: float,
    eq_q: float,
    gate_enabled: bool,
    gate_threshold_db: float,
    gate_attack_ms: float,
    gate_release_ms: float,
    denoise_enabled: bool,
    denoise_strength: float,
    denoise_quantile: float,
    denoise_profile_sec: Optional[float],
    denoise_time_smooth: int,
    deesser_enabled: bool,
    deesser_low_hz: float,
    deesser_high_hz: float,
    deesser_threshold_db: float,
    deesser_ratio: float,
    deesser_attack_ms: float,
    deesser_release_ms: float,
    demucs_model: str,
    demucs_device: str,
    demucs_if_speech: bool,
    noise_split_enabled: bool,
    noise_threshold_db: float,
    noise_window_sec: float,
    clean_gain_db: float,
    clean_denoise_strength: float,
    clean_deesser_threshold_db: float,
    clean_deesser_ratio: float,
    noisy_gain_db: float,
    noisy_denoise_strength: float,
    noisy_deesser_threshold_db: float,
    noisy_deesser_ratio: float,
) -> np.ndarray:
    """Process a single audio chunk through the full pipeline. Returns y_suppress."""
    speech_precheck = classify_segments(y_chunk, sr)[0]

    # --- Demucs ---
    if primary_removal == "demucs":
        if demucs_if_speech and not speech_precheck:
            y_primary = y_chunk
        else:
            with tempfile.TemporaryDirectory() as tmpdir:
                chunk_path = Path(tmpdir) / "chunk.wav"
                sf.write(chunk_path, y_chunk, sr)
                accom = _run_demucs(chunk_path, Path(tmpdir) / "demucs_out", demucs_model, demucs_device)
                y_primary, _ = librosa.load(accom, sr=sr, mono=True)
    else:
        y_primary = y_chunk

    # --- Highpass ---
    y_primary = highpass_filter(y_primary, sr, highpass_hz, highpass_order)

    # --- Classify ---
    speech_segments, transient_segments = classify_segments(y_primary, sr)

    # --- Scoring ---
    y_harmonic = y_primary
    if use_harmonic:
        y_harmonic = librosa.effects.hpss(y_primary)[0]
    mfcc = librosa.feature.mfcc(y=y_harmonic, sr=sr, n_mfcc=n_mfcc)
    delta_mfcc = librosa.feature.delta(mfcc)
    score = float(np.mean(np.abs(delta_mfcc)))
    if not speech_segments:
        action = "keep"
    else:
        action = assign_action(score, low_threshold, high_threshold)

    # --- Suppress ---
    y_suppress = np.copy(y_primary)
    if noise_split_enabled:
        noise_db = float(estimate_noise_db(y_primary, sr, noise_window_sec))
        if noise_db >= noise_threshold_db:
            gain_db = noisy_gain_db
            denoise_strength = noisy_denoise_strength
            deesser_threshold_db = noisy_deesser_threshold_db
            deesser_ratio = noisy_deesser_ratio
        else:
            gain_db = clean_gain_db
            denoise_strength = clean_denoise_strength
            deesser_threshold_db = clean_deesser_threshold_db
            deesser_ratio = clean_deesser_ratio

    if speech_segments:
        for start_s, end_s in speech_segments:
            start = int(start_s * sr)
            end = int(end_s * sr)
            y_suppress[start:end] = apply_gain(y_suppress[start:end], gain_db)

    y_suppress = lowpass_filter(y_suppress, sr, highcut_hz, highcut_order)
    y_suppress = notch_filter(y_suppress, sr, notch_hz, notch_q)
    y_suppress = peaking_eq(y_suppress, sr, 5000.0, eq_5k_db, eq_q)
    y_suppress = peaking_eq(y_suppress, sr, 10000.0, eq_10k_db, eq_q)

    if gate_enabled:
        y_suppress = noise_gate(
            y_suppress, sr,
            threshold_db=gate_threshold_db,
            attack_ms=gate_attack_ms,
            release_ms=gate_release_ms,
        )

    # 2-pass denoise
    if denoise_enabled:
        y_suppress = spectral_denoise(
            y_suppress, sr,
            noise_quantile=denoise_quantile,
            prop_decrease=denoise_strength,
            noise_profile_sec=denoise_profile_sec,
            time_smooth_frames=denoise_time_smooth,
        )
        y_suppress = spectral_denoise(
            y_suppress, sr,
            noise_quantile=denoise_quantile,
            prop_decrease=denoise_strength * 0.6,
            noise_profile_sec=None,
            time_smooth_frames=denoise_time_smooth,
        )

    # Save transient regions AFTER denoise but BEFORE deesser
    margin_s = 0.05
    fade_samples = int(0.01 * sr)
    transient_backups = []
    for start_s, end_s in transient_segments:
        s = max(0, int((start_s - margin_s) * sr))
        e = min(len(y_suppress), int((end_s + margin_s) * sr))
        transient_backups.append((s, e, y_suppress[s:e].copy()))

    if deesser_enabled:
        y_suppress = deesser(
            y_suppress, sr,
            freq_low=deesser_low_hz,
            freq_high=deesser_high_hz,
            threshold_db=deesser_threshold_db,
            ratio=deesser_ratio,
            attack_ms=deesser_attack_ms,
            release_ms=deesser_release_ms,
        )

    # Restore transient regions with crossfade
    for s, e, original in transient_backups:
        seg_len = e - s
        if seg_len <= 0:
            continue
        if fade_samples > 0 and fade_samples < seg_len // 2:
            fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=y_suppress.dtype)
            fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=y_suppress.dtype)
            y_suppress[s:s + fade_samples] = (
                y_suppress[s:s + fade_samples] * (1 - fade_in) + original[:fade_samples] * fade_in
            )
            y_suppress[s + fade_samples:e - fade_samples] = original[fade_samples:-fade_samples]
            y_suppress[e - fade_samples:e] = (
                original[-fade_samples:] * fade_out + y_suppress[e - fade_samples:e] * (1 - fade_out)
            )
        else:
            y_suppress[s:e] = original

    return y_suppress


def export_stage_outputs(
    input_file: Path,
    output_dir: Path,
    sr: int,
    n_mfcc: int,
    low_threshold: float,
    high_threshold: float,
    use_harmonic: bool,
    gain_db: float,
    primary_removal: str,
    highpass_hz: Optional[float],
    highpass_order: int,
    highcut_hz: Optional[float],
    highcut_order: int,
    notch_hz: Optional[float],
    notch_q: float,
    eq_5k_db: float,
    eq_10k_db: float,
    eq_q: float,
    gate_enabled: bool,
    gate_threshold_db: float,
    gate_attack_ms: float,
    gate_release_ms: float,
    denoise_enabled: bool,
    denoise_strength: float,
    denoise_quantile: float,
    denoise_profile_sec: Optional[float],
    denoise_time_smooth: int,
    deesser_enabled: bool,
    deesser_low_hz: float,
    deesser_high_hz: float,
    deesser_threshold_db: float,
    deesser_ratio: float,
    deesser_attack_ms: float,
    deesser_release_ms: float,
    demucs_model: str,
    demucs_device: str,
    demucs_if_speech: bool,
    noise_split_enabled: bool,
    noise_threshold_db: float,
    noise_window_sec: float,
    clean_gain_db: float,
    clean_denoise_strength: float,
    clean_deesser_threshold_db: float,
    clean_deesser_ratio: float,
    noisy_gain_db: float,
    noisy_denoise_strength: float,
    noisy_deesser_threshold_db: float,
    noisy_deesser_ratio: float,
    split_enabled: bool = False,
    split_top_db: float = 25.0,
    split_min_duration_ms: float = 1000.0,
    split_merge_gap_ms: float = 50.0,
    split_pad_ms: float = 30.0,
    split_normalize: bool = False,
    split_gain_db: float = 0.0,
    split_max_duration_s: float = 30.0,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_dir / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Load full audio (no duration cap)
    y_full, _ = librosa.load(input_file, sr=sr, mono=True)
    total_duration = len(y_full) / sr
    _save_audio(run_dir / "01_loaded.wav", y_full, sr)

    # Common processing kwargs
    proc_kwargs = dict(
        sr=sr, n_mfcc=n_mfcc,
        low_threshold=low_threshold, high_threshold=high_threshold,
        use_harmonic=use_harmonic, gain_db=gain_db,
        primary_removal=primary_removal,
        highpass_hz=highpass_hz, highpass_order=highpass_order,
        highcut_hz=highcut_hz, highcut_order=highcut_order,
        notch_hz=notch_hz, notch_q=notch_q,
        eq_5k_db=eq_5k_db, eq_10k_db=eq_10k_db, eq_q=eq_q,
        gate_enabled=gate_enabled, gate_threshold_db=gate_threshold_db,
        gate_attack_ms=gate_attack_ms, gate_release_ms=gate_release_ms,
        denoise_enabled=denoise_enabled, denoise_strength=denoise_strength,
        denoise_quantile=denoise_quantile, denoise_profile_sec=denoise_profile_sec,
        denoise_time_smooth=denoise_time_smooth,
        deesser_enabled=deesser_enabled, deesser_low_hz=deesser_low_hz,
        deesser_high_hz=deesser_high_hz, deesser_threshold_db=deesser_threshold_db,
        deesser_ratio=deesser_ratio, deesser_attack_ms=deesser_attack_ms,
        deesser_release_ms=deesser_release_ms,
        demucs_model=demucs_model, demucs_device=demucs_device,
        demucs_if_speech=demucs_if_speech,
        noise_split_enabled=noise_split_enabled,
        noise_threshold_db=noise_threshold_db, noise_window_sec=noise_window_sec,
        clean_gain_db=clean_gain_db, clean_denoise_strength=clean_denoise_strength,
        clean_deesser_threshold_db=clean_deesser_threshold_db,
        clean_deesser_ratio=clean_deesser_ratio,
        noisy_gain_db=noisy_gain_db, noisy_denoise_strength=noisy_denoise_strength,
        noisy_deesser_threshold_db=noisy_deesser_threshold_db,
        noisy_deesser_ratio=noisy_deesser_ratio,
    )

    # --- Chunk the audio into max_duration pieces ---
    max_chunk_samples = int(split_max_duration_s * sr)
    chunks = []
    pos = 0
    while pos < len(y_full):
        end = min(pos + max_chunk_samples, len(y_full))
        chunks.append((pos, end))
        pos = end

    print(f"[stages] {total_duration:.1f}s audio -> {len(chunks)} chunks ({split_max_duration_s}s each)")

    # --- Process each chunk independently ---
    all_suppress = []
    for ci, (c_start, c_end) in enumerate(chunks):
        chunk_sec = (c_end - c_start) / sr
        print(f"  chunk {ci+1}/{len(chunks)}: {c_start/sr:.1f}s ~ {c_end/sr:.1f}s ({chunk_sec:.1f}s)")
        y_chunk = y_full[c_start:c_end]
        y_suppress = _process_chunk(y_chunk, **proc_kwargs)
        all_suppress.append(y_suppress)

    # Concatenate all processed chunks for stage export
    y_suppress_full = np.concatenate(all_suppress)
    _save_audio(run_dir / "04_suppress.wav", y_suppress_full, sr)

    # --- Split into samples ---
    split_samples_info = []
    if split_enabled:
        samples_dir = run_dir / "samples"
        samples_dir.mkdir(parents=True, exist_ok=True)

        sample_counter = 1
        global_offset = 0  # sample offset for each chunk

        for ci, y_sup in enumerate(all_suppress):
            chunk_offset_s = chunks[ci][0] / sr

            segs = detect_segments(
                y_sup, sr,
                top_db=split_top_db,
                min_duration_ms=split_min_duration_ms,
                merge_gap_ms=split_merge_gap_ms,
                pad_ms=split_pad_ms,
            )

            for s_start, s_end in segs:
                seg = y_sup[s_start:s_end]
                if split_normalize:
                    peak = np.max(np.abs(seg))
                    if peak > 0:
                        seg = seg / peak
                if split_gain_db != 0.0:
                    seg = seg * (10.0 ** (split_gain_db / 20.0))
                    seg = np.clip(seg, -1.0, 1.0)

                fname = f"sample{sample_counter}.wav"
                sf.write(samples_dir / fname, seg, sr)
                split_samples_info.append({
                    "name": fname,
                    "chunk": ci + 1,
                    "start_s": round(chunk_offset_s + s_start / sr, 4),
                    "end_s": round(chunk_offset_s + s_end / sr, 4),
                    "duration_s": round((s_end - s_start) / sr, 4),
                })
                sample_counter += 1

        print(f"[split] {len(split_samples_info)} samples -> {samples_dir}")

    report = {
        "input": str(input_file),
        "rel_path": safe_relpath(input_file, input_file.parent),
        "sr": sr,
        "total_duration_s": round(total_duration, 4),
        "num_chunks": len(chunks),
        "chunk_duration_s": split_max_duration_s,
        "n_mfcc": n_mfcc,
        "use_harmonic": use_harmonic,
        "primary_removal": primary_removal,
        "low_threshold": low_threshold,
        "high_threshold": high_threshold,
        "highpass_hz": highpass_hz,
        "highpass_order": highpass_order,
        "highcut_hz": highcut_hz,
        "highcut_order": highcut_order,
        "notch_hz": notch_hz,
        "notch_q": notch_q,
        "eq_5k_db": eq_5k_db,
        "eq_10k_db": eq_10k_db,
        "eq_q": eq_q,
        "gate_enabled": gate_enabled,
        "gate_threshold_db": gate_threshold_db,
        "gate_attack_ms": gate_attack_ms,
        "gate_release_ms": gate_release_ms,
        "denoise_enabled": denoise_enabled,
        "denoise_strength": denoise_strength,
        "denoise_quantile": denoise_quantile,
        "denoise_profile_sec": denoise_profile_sec,
        "denoise_time_smooth": denoise_time_smooth,
        "deesser_enabled": deesser_enabled,
        "deesser_low_hz": deesser_low_hz,
        "deesser_high_hz": deesser_high_hz,
        "deesser_threshold_db": deesser_threshold_db,
        "deesser_ratio": deesser_ratio,
        "deesser_attack_ms": deesser_attack_ms,
        "deesser_release_ms": deesser_release_ms,
        "demucs_model": demucs_model,
        "demucs_device": demucs_device,
        "noise_split_enabled": noise_split_enabled,
        "noise_threshold_db": noise_threshold_db,
        "noise_window_sec": noise_window_sec,
        "clean_gain_db": clean_gain_db,
        "clean_denoise_strength": clean_denoise_strength,
        "clean_deesser_threshold_db": clean_deesser_threshold_db,
        "clean_deesser_ratio": clean_deesser_ratio,
        "noisy_gain_db": noisy_gain_db,
        "noisy_denoise_strength": noisy_denoise_strength,
        "noisy_deesser_threshold_db": noisy_deesser_threshold_db,
        "noisy_deesser_ratio": noisy_deesser_ratio,
        "split_enabled": split_enabled,
        "split_num_samples": len(split_samples_info),
        "split_samples": split_samples_info,
    }

    report_path = run_dir / "stage_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path
