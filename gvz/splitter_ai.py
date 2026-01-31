"""AI-based audio splitter using pretrained frame embeddings + novelty detection."""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import librosa
import numpy as np
import soundfile as sf
import torch
from .filters import highpass_filter, spectral_denoise


def _load_model(device: str = "cuda"):
    """Load Wav2Vec2 model for frame-level feature extraction."""
    from transformers import Wav2Vec2Model, Wav2Vec2Processor

    model_name = "facebook/wav2vec2-base"
    processor = Wav2Vec2Processor.from_pretrained(model_name)
    model = Wav2Vec2Model.from_pretrained(model_name, use_safetensors=False).to(device).eval()
    return processor, model


def extract_frame_embeddings(
    y: np.ndarray,
    sr: int,
    processor,
    model,
    device: str = "cuda",
) -> np.ndarray:
    """Extract frame-level embeddings from audio.

    Returns (num_frames, embed_dim) array.
    """
    # Wav2Vec2 expects 16kHz
    if sr != 16000:
        y = librosa.resample(y, orig_sr=sr, target_sr=16000)

    inputs = processor(y, sampling_rate=16000, return_tensors="pt", padding=True)
    input_values = inputs.input_values.to(device)

    with torch.no_grad():
        outputs = model(input_values)
        # hidden_states: (1, num_frames, 768)
        embeddings = outputs.last_hidden_state.squeeze(0).cpu().numpy()

    return embeddings


def compute_novelty(embeddings: np.ndarray, kernel_size: int = 15) -> np.ndarray:
    """Compute novelty function from frame embeddings using checkerboard kernel."""
    n_frames = embeddings.shape[0]
    if n_frames < kernel_size * 2:
        return np.zeros(n_frames)

    # Cosine similarity between consecutive frame windows
    novelty = np.zeros(n_frames)
    half = kernel_size

    for i in range(half, n_frames - half):
        left = embeddings[i - half:i]
        right = embeddings[i:i + half]
        left_mean = left.mean(axis=0)
        right_mean = right.mean(axis=0)

        cos_sim = np.dot(left_mean, right_mean) / (
            np.linalg.norm(left_mean) * np.linalg.norm(right_mean) + 1e-8
        )
        novelty[i] = 1.0 - cos_sim

    return novelty


def detect_boundaries(
    novelty: np.ndarray,
    threshold_factor: float = 1.5,
    min_gap_frames: int = 20,
) -> List[int]:
    """Detect segment boundaries from novelty curve using adaptive thresholding."""
    if novelty.max() < 1e-6:
        return []

    threshold = novelty.mean() + threshold_factor * novelty.std()
    peaks = []

    i = 0
    while i < len(novelty):
        if novelty[i] >= threshold:
            # Find the peak in this region
            j = i
            while j < len(novelty) and novelty[j] >= threshold * 0.5:
                j += 1
            peak_idx = i + np.argmax(novelty[i:j])
            peaks.append(int(peak_idx))
            i = peak_idx + min_gap_frames
        else:
            i += 1

    return peaks


def frames_to_seconds(frame_idx: int, sr: int = 16000) -> float:
    """Convert Wav2Vec2 frame index to seconds.

    Wav2Vec2 outputs ~50 frames per second (320 samples per frame at 16kHz).
    """
    return frame_idx * 320 / sr


def split_audio_ai(
    input_file: Path,
    output_dir: Path,
    sr: int = 16000,
    device: str = "cuda",
    threshold_factor: float = 1.5,
    min_segment_ms: float = 100.0,
    min_gap_frames: int = 20,
    kernel_size: int = 15,
    pad_ms: float = 50.0,
    denoise: bool = False,
    denoise_strength: float = 0.8,
) -> Path:
    """Split audio using AI-based novelty detection.

    Returns path to manifest JSON.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = input_file.stem
    run_dir = output_dir / f"{stem}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading model...")
    processor, model = _load_model(device)

    print(f"Loading audio: {input_file.name}")
    y, _ = librosa.load(input_file, sr=sr, mono=True)
    total_duration = len(y) / sr

    # Preprocessing
    print("Preprocessing audio...")
    # 1. Highpass to remove rumble
    y = highpass_filter(y, sr, cutoff_hz=80.0)
    
    # 2. Denoise if requested
    if denoise:
        print(f"Applying denoise (strength={denoise_strength})...")
        y = spectral_denoise(y, sr, prop_decrease=denoise_strength)

    print(f"Extracting embeddings...")
    embeddings = extract_frame_embeddings(y, sr, processor, model, device)

    print(f"Computing novelty ({embeddings.shape[0]} frames)...")
    novelty = compute_novelty(embeddings, kernel_size=kernel_size)

    print(f"Detecting boundaries...")
    boundary_frames = detect_boundaries(novelty, threshold_factor, min_gap_frames)
    boundary_secs = [frames_to_seconds(f, 16000) for f in boundary_frames]

    # Build segment intervals: [0, b1], [b1, b2], ..., [bn, end]
    # Filter boundaries to enforce min_segment_ms
    min_seg_sec = min_segment_ms / 1000.0
    final_boundaries = []
    last_boundary = 0.0
    
    for b in boundary_secs:
        if b - last_boundary >= min_seg_sec:
            final_boundaries.append(b)
            last_boundary = b
    
    # Check last segment duration
    if total_duration - last_boundary < min_seg_sec:
        # If last segment is too short, remove the last boundary (merge into previous)
        if final_boundaries:
            final_boundaries.pop()
            
    # Construct segments
    points = [0.0] + final_boundaries + [total_duration]
    final_segments = []
    for i in range(len(points) - 1):
        final_segments.append((points[i], points[i+1]))

    # Skip very quiet segments check for now or make it optional? 
    # The user wants "separation", so let's keep all segments that novelty detected.
    # If we want to filter silence, we should use a VAD or the energy check properly.
    # For "noise" file, energy might be consistent, so let's skip the energy filter to ensure we output splits.


    # Export
    pad_s = pad_ms / 1000.0
    print(f"Exporting {len(final_segments)} segments...")
    manifest = {
        "input": str(input_file),
        "sr": sr,
        "total_duration_s": round(total_duration, 4),
        "params": {
            "model": "wav2vec2-base",
            "device": device,
            "threshold_factor": threshold_factor,
            "min_segment_ms": min_segment_ms,
            "min_gap_frames": min_gap_frames,
            "kernel_size": kernel_size,
            "pad_ms": pad_ms,
        },
        "num_boundaries": len(boundary_frames),
        "num_segments": len(final_segments),
        "segments": [],
    }

    for i, (start_s, end_s) in enumerate(final_segments):
        s = max(0, int((start_s - pad_s) * sr))
        e = min(len(y), int((end_s + pad_s) * sr))
        seg = y[s:e]

        filename = f"{stem}_{i:04d}.wav"
        sf.write(run_dir / filename, seg, sr)

        manifest["segments"].append({
            "index": i,
            "file": filename,
            "start_s": round(start_s, 4),
            "end_s": round(end_s, 4),
            "duration_s": round(end_s - start_s, 4),
        })

    # Save novelty curve for debugging
    np.save(run_dir / "novelty.npy", novelty)

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Done: {len(final_segments)} segments -> {run_dir}")
    return manifest_path


def split_to_samples_ai(
    input_path: Path,
    output_dir: Path = None,
    sr: int = 16000,
    device: str = "cuda",
    threshold_factor: float = 1.5,
    min_segment_ms: float = 100.0,
    min_gap_frames: int = 20,
    kernel_size: int = 15,
    pad_ms: float = 50.0,
    denoise: bool = False,
    denoise_strength: float = 0.8,
) -> Path:
    """Split preprocessed audio into sample1.wav, sample2.wav, ... using AI novelty detection.

    input_path can be a .wav file or a stages run directory (will use 05_keep.wav).
    Returns path to output directory containing samples.
    """
    # Resolve input file
    if input_path.is_dir():
        keep_file = input_path / "05_keep.wav"
        if not keep_file.exists():
            raise FileNotFoundError(f"05_keep.wav not found in {input_path}")
        input_file = keep_file
    else:
        input_file = input_path

    # Resolve output directory
    if output_dir is None:
        output_dir = input_file.parent / "samples"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading model on {device}...")
    processor, model = _load_model(device)

    print(f"Loading audio: {input_file.name}")
    y, _ = librosa.load(input_file, sr=sr, mono=True)
    total_duration = len(y) / sr

    # Preprocessing
    y_proc = highpass_filter(y, sr, cutoff_hz=80.0)
    if denoise:
        print(f"Applying denoise (strength={denoise_strength})...")
        y_proc = spectral_denoise(y_proc, sr, prop_decrease=denoise_strength)

    print(f"Extracting embeddings...")
    embeddings = extract_frame_embeddings(y_proc, sr, processor, model, device)

    print(f"Computing novelty ({embeddings.shape[0]} frames)...")
    novelty = compute_novelty(embeddings, kernel_size=kernel_size)

    print(f"Detecting boundaries...")
    boundary_frames = detect_boundaries(novelty, threshold_factor, min_gap_frames)
    boundary_secs = [frames_to_seconds(f, 16000) for f in boundary_frames]

    # Build segments with minimum duration enforcement
    min_seg_sec = min_segment_ms / 1000.0
    final_boundaries = []
    last_boundary = 0.0

    for b in boundary_secs:
        if b - last_boundary >= min_seg_sec:
            final_boundaries.append(b)
            last_boundary = b

    if total_duration - last_boundary < min_seg_sec and final_boundaries:
        final_boundaries.pop()

    points = [0.0] + final_boundaries + [total_duration]
    final_segments = [(points[i], points[i + 1]) for i in range(len(points) - 1)]

    # Export
    pad_s = pad_ms / 1000.0
    manifest = {
        "input": str(input_file),
        "sr": sr,
        "total_duration_s": round(total_duration, 4),
        "params": {
            "model": "wav2vec2-base",
            "device": device,
            "threshold_factor": threshold_factor,
            "min_segment_ms": min_segment_ms,
            "min_gap_frames": min_gap_frames,
            "kernel_size": kernel_size,
            "pad_ms": pad_ms,
            "mode": "gpu",
        },
        "num_samples": len(final_segments),
        "samples": [],
    }

    for i, (start_s, end_s) in enumerate(final_segments, start=1):
        s = max(0, int((start_s - pad_s) * sr))
        e = min(len(y), int((end_s + pad_s) * sr))
        seg = y[s:e]

        filename = f"sample{i}.wav"
        sf.write(output_dir / filename, seg, sr)

        manifest["samples"].append({
            "name": filename,
            "start_s": round(start_s, 4),
            "end_s": round(end_s, 4),
            "duration_s": round(end_s - start_s, 4),
        })

    np.save(output_dir / "novelty.npy", novelty)

    manifest_path = output_dir / "split_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[GPU split] {len(final_segments)} samples -> {output_dir}")
    return output_dir
