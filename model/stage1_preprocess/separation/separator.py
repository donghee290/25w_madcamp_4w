"""Demucs 4-stem drum extraction for DrumGen-X."""

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict

import librosa
import numpy as np
import soundfile as sf

from ..io.utils import logger, set_torch_home, load_audio, save_audio, ensure_dir


def run_demucs_full(
    src_path: Path,
    output_dir: Path,
    model: str = "htdemucs",
    device: str = "cuda",
) -> Dict[str, Path]:
    """Run demucs full 4-stem separation (drums, bass, vocals, other).

    Returns dict mapping stem name -> output file path.
    """
    set_torch_home()
    ensure_dir(output_dir)

    cmd = [
        sys.executable,
        "-m", "demucs",
        "-n", model,
        "-d", device,
        "-o", str(output_dir),
        str(src_path),
    ]

    logger.info(f"Running demucs 4-stem: {src_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Demucs failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    model_dir = output_dir / model / src_path.stem
    stems = {}
    for stem_name in ["drums", "bass", "vocals", "other"]:
        stem_path = model_dir / f"{stem_name}.wav"
        if not stem_path.exists():
            logger.warning(f"Stem not found: {stem_path}")
        else:
            stems[stem_name] = stem_path

    if "drums" not in stems:
        raise RuntimeError(f"drums.wav not found in demucs output: {model_dir}")

    logger.info(f"Demucs complete: {list(stems.keys())}")
    return stems


def extract_drum_stem(
    audio_path: Path,
    output_dir: Path,
    model: str = "htdemucs",
    device: str = "cuda",
    sr: int = 44100,
    chunk_duration_s: float = 60.0,
) -> Path:
    """Extract drum stem from audio file. Handles chunking for long files.

    Returns path to the extracted drums.wav.
    """
    y, _ = load_audio(audio_path, sr=sr)
    total_duration = len(y) / sr

    drums_output = ensure_dir(output_dir) / "drums.wav"

    if drums_output.exists() and drums_output.stat().st_size > 0:
        logger.info(f"Drums already extracted: {drums_output}")
        return drums_output

    if total_duration <= chunk_duration_s:
        # Short file: process directly
        stems = run_demucs_full(audio_path, output_dir, model, device)
        # Copy/move to standard location
        drums_y, _ = load_audio(stems["drums"], sr=sr)
        save_audio(drums_output, drums_y, sr)
        return drums_output

    # Long file: chunk -> demucs -> concat
    logger.info(f"Long file ({total_duration:.1f}s), chunking at {chunk_duration_s}s")
    chunk_samples = int(chunk_duration_s * sr)
    drum_chunks = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        pos = 0
        chunk_idx = 0

        while pos < len(y):
            end = min(pos + chunk_samples, len(y))
            chunk = y[pos:end]

            chunk_path = tmpdir / f"chunk_{chunk_idx:03d}.wav"
            sf.write(str(chunk_path), chunk, sr)

            chunk_out = tmpdir / f"demucs_out_{chunk_idx:03d}"
            stems = run_demucs_full(chunk_path, chunk_out, model, device)

            drums_chunk, _ = load_audio(stems["drums"], sr=sr)
            drum_chunks.append(drums_chunk)

            logger.info(f"  Chunk {chunk_idx}: {pos/sr:.1f}s-{end/sr:.1f}s -> {len(drums_chunk)} samples")
            pos = end
            chunk_idx += 1

    drums_full = np.concatenate(drum_chunks)
    save_audio(drums_output, drums_full, sr)
    logger.info(f"Drums extracted: {drums_output} ({len(drums_full)/sr:.1f}s)")
    return drums_output
