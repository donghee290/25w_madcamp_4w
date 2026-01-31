"""Audio splitter: split preprocessed audio into individual sound events."""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import librosa
import numpy as np
import soundfile as sf


def detect_segments(
    y: np.ndarray,
    sr: int,
    top_db: float = 30.0,
    min_duration_ms: float = 50.0,
    merge_gap_ms: float = 100.0,
    pad_ms: float = 30.0,
) -> List[Tuple[int, int]]:
    """Detect non-silent segments with merging and filtering.

    Returns list of (start_sample, end_sample) tuples.
    """
    intervals = librosa.effects.split(y, top_db=top_db)
    if len(intervals) == 0:
        return []

    merge_gap = int(merge_gap_ms / 1000.0 * sr)
    min_len = int(min_duration_ms / 1000.0 * sr)
    pad = int(pad_ms / 1000.0 * sr)

    # Merge segments closer than merge_gap
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start - merged[-1][1] <= merge_gap:
            merged[-1][1] = end
        else:
            merged.append([start, end])

    # Filter by minimum duration and add padding
    result = []
    for start, end in merged:
        if end - start < min_len:
            continue
        s = max(0, start - pad)
        e = min(len(y), end + pad)
        result.append((s, e))

    return result


def split_audio(
    input_file: Path,
    output_dir: Path,
    sr: int = 16000,
    top_db: float = 30.0,
    min_duration_ms: float = 50.0,
    merge_gap_ms: float = 100.0,
    pad_ms: float = 30.0,
) -> Path:
    """Split a single audio file into individual segment files.

    Returns path to the manifest JSON.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = input_file.stem
    run_dir = output_dir / f"{stem}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    y, _ = librosa.load(input_file, sr=sr, mono=True)
    segments = detect_segments(
        y, sr,
        top_db=top_db,
        min_duration_ms=min_duration_ms,
        merge_gap_ms=merge_gap_ms,
        pad_ms=pad_ms,
    )

    manifest = {
        "input": str(input_file),
        "sr": sr,
        "total_duration_s": len(y) / sr,
        "params": {
            "top_db": top_db,
            "min_duration_ms": min_duration_ms,
            "merge_gap_ms": merge_gap_ms,
            "pad_ms": pad_ms,
        },
        "num_segments": len(segments),
        "segments": [],
    }

    for i, (start, end) in enumerate(segments):
        seg = y[start:end]
        filename = f"{stem}_{i:04d}.wav"
        out_path = run_dir / filename
        sf.write(out_path, seg, sr)

        manifest["segments"].append({
            "index": i,
            "file": filename,
            "start_s": round(start / sr, 4),
            "end_s": round(end / sr, 4),
            "duration_s": round((end - start) / sr, 4),
        })

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def split_directory(
    input_dir: Path,
    output_dir: Path,
    sr: int = 16000,
    top_db: float = 30.0,
    min_duration_ms: float = 50.0,
    merge_gap_ms: float = 100.0,
    pad_ms: float = 30.0,
) -> Path:
    """Split all audio files in a directory."""
    audio_exts = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".aif", ".aiff"}
    files = sorted(p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in audio_exts)

    all_manifests = []
    for f in files:
        m_path = split_audio(f, output_dir, sr, top_db, min_duration_ms, merge_gap_ms, pad_ms)
        m = json.loads(m_path.read_text(encoding="utf-8"))
        all_manifests.append(m)
        print(f"  {f.name}: {m['num_segments']} segments")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = output_dir / f"split_summary_{timestamp}.json"
    summary = {
        "total_files": len(all_manifests),
        "total_segments": sum(m["num_segments"] for m in all_manifests),
        "files": [{
            "input": m["input"],
            "num_segments": m["num_segments"],
        } for m in all_manifests],
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary_path


def split_to_samples(
    input_path: Path,
    output_dir: Path = None,
    sr: int = 16000,
    top_db: float = 30.0,
    min_duration_ms: float = 50.0,
    merge_gap_ms: float = 100.0,
    pad_ms: float = 30.0,
    normalize: bool = False,
    gain_db: float = 0.0,
) -> Path:
    """Split preprocessed audio into sample1.wav, sample2.wav, ...

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

    y, _ = librosa.load(input_file, sr=sr, mono=True)
    segments = detect_segments(
        y, sr,
        top_db=top_db,
        min_duration_ms=min_duration_ms,
        merge_gap_ms=merge_gap_ms,
        pad_ms=pad_ms,
    )

    manifest = {
        "input": str(input_file),
        "sr": sr,
        "total_duration_s": round(len(y) / sr, 4),
        "params": {
            "top_db": top_db,
            "min_duration_ms": min_duration_ms,
            "merge_gap_ms": merge_gap_ms,
            "pad_ms": pad_ms,
            "normalize": normalize,
            "gain_db": gain_db,
            "mode": "cpu",
        },
        "num_samples": len(segments),
        "samples": [],
    }

    for i, (start, end) in enumerate(segments, start=1):
        seg = y[start:end]
        if normalize:
            peak = np.max(np.abs(seg))
            if peak > 0:
                seg = seg / peak
        if gain_db != 0.0:
            seg = seg * (10.0 ** (gain_db / 20.0))
            seg = np.clip(seg, -1.0, 1.0)
        filename = f"sample{i}.wav"
        sf.write(output_dir / filename, seg, sr)

        manifest["samples"].append({
            "name": filename,
            "start_s": round(start / sr, 4),
            "end_s": round(end / sr, 4),
            "duration_s": round((end - start) / sr, 4),
        })

    manifest_path = output_dir / "split_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[CPU split] {len(segments)} samples -> {output_dir}")
    return output_dir
