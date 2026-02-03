"""Stage 1: Full Audio Preprocessing Pipeline

Executes the complete Stage 1 preprocessing:
  1. Dataset scan & file selection
  2. Demucs drum stem extraction (CPU/GPU auto-select)
  3. Multi-band onset detection
  4. Hit slicing + deduplication
  5. DSP role classification (CORE/ACCENT/MOTION/FILL/TEXTURE)
  6. Pool balancing → master kit output

Usage:
  python -m pipeline.step1_run_preprocess --input_dir /path/to/audio --out_dir /path/to/output
  python -m pipeline.step1_run_preprocess --input /single/file.wav --out_dir /path/to/output
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Device auto-detection
# ---------------------------------------------------------------------------

def detect_device() -> str:
    """Auto-detect best available device: cuda > mps > cpu."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            print(f"[Device] CUDA detected: {name}")
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            print("[Device] MPS (Apple Silicon) detected")
            return "mps"
    except ImportError:
        pass
    print("[Device] No GPU found, using CPU")
    return "cpu"


# ---------------------------------------------------------------------------
# Imports from stage1_preprocess
# ---------------------------------------------------------------------------

def _add_model_to_path():
    """Ensure `model/` is on sys.path so stage1_preprocess is importable."""
    model_dir = str(Path(__file__).resolve().parent.parent)
    if model_dir not in sys.path:
        sys.path.insert(0, model_dir)

_add_model_to_path()

from stage1_preprocess.config import PipelineConfig
from stage1_preprocess.io.utils import setup_logging, load_audio, save_audio, ensure_dir, logger
from stage1_preprocess.io.ingest import scan_dataset, random_sample
from stage1_preprocess.separation.separator import extract_drum_stem
from stage1_preprocess.analysis.detector import detect_onsets
from stage1_preprocess.slicing.slicer import build_kit_from_audio, normalize_hit
from stage1_preprocess.sequencer import load_kit, render_and_save
from stage1_preprocess.events import generate_skeleton


# ---------------------------------------------------------------------------
# Pipeline Implementation
# ---------------------------------------------------------------------------

def process_single_file(
    audio_path: Path,
    output_dir: Path,
    config: PipelineConfig,
) -> Optional[Path]:
    """Process a single audio file through the full pipeline."""
    file_dir = ensure_dir(output_dir / audio_path.stem)

    try:
        # Step 1: Extract drum stem
        logger.info(f"=== Processing: {audio_path.name} ===")
        drums_path = extract_drum_stem(
            audio_path,
            file_dir / "demucs",
            model=config.demucs_model,
            device=config.demucs_device,
            sr=config.sr,
            chunk_duration_s=config.chunk_duration_s,
        )

        # Step 2: Load drum stem
        y_drums, _ = load_audio(drums_path, sr=config.sr)
        logger.info(f"Drum stem: {len(y_drums)/config.sr:.1f}s")

        # Step 3: Detect onsets
        onsets = detect_onsets(
            y_drums, config.sr,
            merge_ms=config.onset_merge_ms,
            backtrack=config.onset_backtrack,
        )

        if not onsets:
            logger.warning(f"No onsets detected in {audio_path.name}")
            return None

        # Step 4: Slice, deduplicate, save
        kit_dir = file_dir / "kit"
        _manifest_path, _representatives = build_kit_from_audio(
            y_drums, config.sr, onsets, kit_dir,
            max_duration_s=config.max_hit_duration_s,
            fade_out_ms=config.fade_out_ms,
            trim_db=config.trim_silence_db,
            min_hit_duration_s=config.min_hit_duration_s,
            dedup_enabled=config.dedup_enabled,
            dedup_threshold=config.dedup_threshold,
        )

        return kit_dir

    except Exception as e:
        logger.error(f"Failed to process {audio_path.name}: {e}")
        return None


def merge_kits(
    kit_dirs: List[Path],
    output_dir: Path,
    sr: int = 44100,
    best_per_class: int = 20,
) -> Path:
    """Merge kits into master kit (simplified - no role balancing)."""
    master_dir = ensure_dir(output_dir / "master_kit")

    # Gather all samples from all kits
    all_samples = []

    logger.info("Merging kits (simplified - no role classification)...")

    for kit_dir in kit_dirs:
        kit = load_kit(kit_dir, sr=sr)
        for role, role_samples in kit.items():
            for s in role_samples:
                all_samples.append(s)

    # Save all samples to dummy folder
    dummy_dir = ensure_dir(master_dir / "dummy")
    manifest = {"sr": sr, "roles": {"dummy": []}}
    total = 0

    # Sort by energy (RMS)
    samples_with_rms = []
    for s in all_samples:
        rms = np.sqrt(np.mean(s**2))
        samples_with_rms.append((rms, s))

    samples_with_rms.sort(key=lambda x: x[0], reverse=True)

    # Limit to best_per_class if needed
    if best_per_class > 0:
        samples_with_rms = samples_with_rms[:best_per_class]

    for i, (rms, sample) in enumerate(samples_with_rms, start=1):
        sample = normalize_hit(sample)
        fname = f"dummy_{i:03d}.wav"
        save_audio(dummy_dir / fname, sample, sr)

        manifest["roles"]["dummy"].append({
            "file": fname,
            "duration_s": round(len(sample) / sr, 4),
            "rms": round(float(rms), 6)
        })
        total += 1

    manifest["total_samples"] = total
    (master_dir / "kit_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    logger.info(f"Master kit created: {total} samples in {master_dir}")
    return master_dir


def generate_test_loops(
    kit_dir: Path,
    output_dir: Path,
    sr: int = 44100,
    bpm: float = 120.0,
    bars: int = 4,
) -> List[Path]:
    """Generate test loops using EventGrid generator."""
    loops_dir = ensure_dir(output_dir / "test_loops")
    kit = load_kit(kit_dir, sr=sr)

    if not kit:
        logger.warning("Empty kit, cannot generate loops")
        return []

    outputs = []
    
    # 1. Rock (Core Beat)
    grid_rock = generate_skeleton(bars=bars, bpm=bpm, kit_dir=str(kit_dir), seed=42)
    path = render_and_save(grid_rock, kit, loops_dir / f"test_rock_{int(bpm)}.wav", sr=sr, reverb=True)
    outputs.append(path)
    
    # 2. Dense Beat
    grid_dense = generate_skeleton(bars=bars, bpm=bpm, motion_density=8, seed=99)
    path_dense = render_and_save(grid_dense, kit, loops_dir / f"test_dense_{int(bpm)}.wav", sr=sr, reverb=True)
    outputs.append(path_dense)

    return outputs


def run_full_pipeline(config: PipelineConfig) -> Path:
    """Run complete pipeline."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ensure_dir(config.output_root / f"stage1_{timestamp}")

    logger.info(f"=== DrumGen-X Pipeline ===")
    
    # 1. Scan & Select
    all_files = scan_dataset(config.dataset_root)
    selected = random_sample(all_files, config.n_files)
    logger.info(f"Selected {len(selected)} / {len(all_files)} files")

    # 2. Process
    kit_dirs = []
    results = []
    for audio_path in selected:
        kit_dir = process_single_file(audio_path, run_dir / "files", config)
        status = "success" if kit_dir else "failed"
        results.append({"file": audio_path.name, "status": status})
        if kit_dir:
            kit_dirs.append(kit_dir)

    if not kit_dirs:
        logger.error("Pipeline failed: No kits produced.")
        return run_dir

    # 3. Merge & Balance
    master_dir = merge_kits(kit_dirs, run_dir, sr=config.sr, best_per_class=config.best_per_class)

    # 4. Loop Gen
    loops = generate_test_loops(master_dir, run_dir, sr=config.sr)

    # 5. Report
    report = {
        "timestamp": timestamp,
        "results": results,
        "master_kit": str(master_dir),
        "loops": [str(p) for p in loops]
    }
    (run_dir / "pipeline_report.json").write_text(json.dumps(report, indent=2))
    
    return run_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage 1: Audio Preprocessing (Demucs → Onset → Slice → Dedup → Classify)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Input source (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input_dir", type=Path,
        help="Root directory with audio files (batch mode)",
    )
    input_group.add_argument(
        "--input", type=Path,
        help="Single audio file to process",
    )

    # Output
    parser.add_argument(
        "--out_dir", type=Path, default=Path("stage1_output"),
        help="Output directory for results",
    )

    # Device
    parser.add_argument(
        "--device", type=str, default="auto",
        choices=["auto", "cuda", "mps", "cpu"],
        help="Compute device (auto = detect best available)",
    )

    # Demucs
    parser.add_argument("--model", type=str, default="htdemucs",
                        help="Demucs model name")
    parser.add_argument("--sr", type=int, default=44100,
                        help="Sample rate")
    parser.add_argument("--chunk-duration", type=float, default=60.0,
                        help="Max chunk duration for Demucs (seconds)")

    # Onset detection
    parser.add_argument("--onset-merge-ms", type=float, default=30.0,
                        help="Merge onsets within this window (ms)")

    # Slicing
    parser.add_argument("--max-hit-duration", type=float, default=2.0,
                        help="Maximum hit duration (seconds)")
    parser.add_argument("--min-hit-duration", type=float, default=0.0,
                        help="Minimum hit duration filter (seconds, 0=off)")
    parser.add_argument("--fade-out-ms", type=float, default=50.0,
                        help="Fade-out duration for hit tails (ms)")

    # Dedup
    parser.add_argument("--dedup-threshold", type=float, default=0.5,
                        help="Cosine distance threshold for dedup clustering")
    parser.add_argument("--no-dedup", action="store_true",
                        help="Disable deduplication")

    # Batch
    parser.add_argument("--n-files", type=int, default=5,
                        help="Number of files to process in batch mode")
    parser.add_argument("--best-per-class", type=int, default=10,
                        help="Max samples per role in master kit")

    # Logging
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")

    return parser.parse_args()


def main():
    args = parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(level)

    # Device selection
    device = args.device
    if device == "auto":
        device = detect_device()

    # Build config
    config = PipelineConfig(
        sr=args.sr,
        demucs_model=args.model,
        demucs_device=device,
        chunk_duration_s=args.chunk_duration,
        output_root=args.out_dir,
        onset_merge_ms=args.onset_merge_ms,
        max_hit_duration_s=args.max_hit_duration,
        min_hit_duration_s=args.min_hit_duration,
        fade_out_ms=args.fade_out_ms,
        dedup_threshold=args.dedup_threshold,
        dedup_enabled=not args.no_dedup,
        n_files=args.n_files,
        dataset_root=args.input_dir, # Will be None if single file mode
        best_per_class=args.best_per_class,
    )

    t_start = time.time()

    if args.input:
        # Single file mode
        audio_path = args.input.resolve()
        if not audio_path.exists():
            print(f"Error: file not found: {audio_path}")
            sys.exit(1)

        config.output_root = args.out_dir
        result_dir = process_single_file(audio_path, args.out_dir, config)
        
        if result_dir:
            print(f"\nDone: Stage 1 single file -> {result_dir}")
        else:
            print(f"\nFailed: Processing returned None")
            sys.exit(1)

    else:
        # Batch mode
        config.dataset_root = args.input_dir.resolve()
        if not config.dataset_root.exists():
            print(f"Error: dataset root not found: {config.dataset_root}")
            sys.exit(1)

        run_dir = run_full_pipeline(config)
        
        elapsed = time.time() - t_start
        print(f"\nStage 1 complete in {elapsed:.0f}s -> {run_dir}")


if __name__ == "__main__":
    main()
