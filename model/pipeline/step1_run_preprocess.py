"""Stage 1: Full Audio Preprocessing Pipeline

Executes the complete Stage 1 preprocessing:
  1. Dataset scan & file selection
  2. Demucs drum stem extraction (CPU/GPU auto-select)
  3. Multi-band onset detection
  4. Hit slicing + deduplication
  5. Save as flat samples

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
from stage1_preprocess.slicing.slicer import extract_samples, normalize_hit


# ---------------------------------------------------------------------------
# Pipeline Implementation
# ---------------------------------------------------------------------------

def process_single_file(
    audio_path: Path,
    samples_dir: Path,
    config: PipelineConfig,
) -> int:
    """Process a single audio file and save samples to samples_dir."""
    # Use a temp dir for demucs
    # samples_dir is run_dir/samples. We want run_dir/temp_demucs
    temp_work_dir = samples_dir.parent / "temp_demucs" / audio_path.stem
    ensure_dir(temp_work_dir)

    try:
        # Step 0: Check duration for one-shot bypass
        # Load briefly or use librosa.get_duration if possible. 
        # Here we just load with librosa to check duration before demucs
        import librosa
        duration = librosa.get_duration(path=audio_path)
        
        if duration < config.one_shot_threshold_s:
            logger.info(f"Header duration: {duration:.2f}s. Verifying with robust check...")
            
            # Helper to get duration via ffmpeg/ffprobe
            def get_duration_ffmpeg(path):
                import subprocess
                try:
                    # Use ffprobe to get duration
                    cmd = [
                        "ffprobe", "-v", "error", "-show_entries", "format=duration", 
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
                    ]
                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if result.returncode == 0 and result.stdout.strip():
                        return float(result.stdout.strip())
                except Exception as e:
                    logger.warning(f"ffprobe failed: {e}")
                return None

            real_duration = None
            
            # Try ffprobe first (most robust for containers)
            ff_dur = get_duration_ffmpeg(audio_path)
            if ff_dur is not None:
                real_duration = ff_dur
                logger.info(f"ffprobe duration: {real_duration:.2f}s")
            
            # Fallback to loading if ffprobe failed
            if real_duration is None:
                try:
                    y, sr = load_audio(audio_path, sr=config.sr)
                    real_duration = len(y) / sr
                except Exception as e:
                    logger.warning(f"Failed to load audio for verification: {e}")
                    # CRITICAL CHANGE: If we can't verify it's short, assume it's LONG to avoid mis-processing long files as one-shots.
                    real_duration = 999.0 

            if real_duration < config.one_shot_threshold_s:
                logger.info(f"Short file confirmed ({real_duration:.2f}s). Treating as one-shot.")
                
                # Load if not loaded
                if 'y' not in locals() or y is None:
                    y, sr = load_audio(audio_path, sr=config.sr)

                # Simple One-Shot Path: Load -> Trim -> Normalize -> Save
                
                # Trim silence
                trimmed, _ = librosa.effects.trim(y, top_db=config.trim_silence_db)
                
                # Normalize
                from stage1_preprocess.slicing.slicer import normalize_hit
                norm_y = normalize_hit(trimmed)
                
                # Save
                out_name = f"{audio_path.stem}_001.wav"
                out_path = samples_dir / out_name
                
                save_audio(out_path, norm_y, sr)
                logger.info(f"Saved one-shot: {out_path}")
                return 1
            else:
                logger.warning(f"File duration judged as {real_duration:.2f}s (header said {duration:.2f}s). LEAVING One-Shot path, proceeding to Demucs pipeline.")
                # Fall through to Demucs path

        # Step 1: Extract drum stem
        logger.info(f"=== Processing: {audio_path.name} ===")
        drums_path = extract_drum_stem(
            audio_path,
            temp_work_dir,
            model=config.demucs_model,
            device=config.demucs_device,
            sr=config.sr,
            chunk_duration_s=config.chunk_duration_s,
        )

        if not drums_path or not drums_path.exists():
            logger.warning(f"Demucs failed for {audio_path.name}")
            return 0

        y_drums, _ = load_audio(drums_path, sr=config.sr)
        logger.info(f"Drum stem: {len(y_drums)/config.sr:.1f}s")
        
        # Cleanup Demucs output immediately
        import shutil
        try:
            shutil.rmtree(temp_work_dir)
        except Exception:
            pass

        # Step 3: Detect onsets
        onsets = detect_onsets(
            y_drums, config.sr,
            merge_ms=config.onset_merge_ms,
            backtrack=config.onset_backtrack,
        )

        if not onsets:
            logger.warning(f"No onsets detected in {audio_path.name}")
            return 0

        # Step 4: Slice and save directly to common samples dir
        # We assume file_stem ensures uniqueness. Step 1 usually runs sequentially or needs careful naming if parallel.
        saved_paths = extract_samples(
            y_drums, config.sr, onsets,
            output_dir=samples_dir,
            file_stem=audio_path.stem,
            max_duration_s=config.max_hit_duration_s,
            fade_out_ms=config.fade_out_ms,
            trim_db=config.trim_silence_db,
            min_hit_duration_s=config.min_hit_duration_s,
            dedup_enabled=config.dedup_enabled,
            dedup_threshold=config.dedup_threshold,
            max_extracted_samples=config.max_extracted_samples,
        )
        
        return len(saved_paths)

    except Exception as e:
        logger.error(f"Failed to process {audio_path.name}: {e}")
        return 0


def run_full_pipeline(config: PipelineConfig) -> Path:
    """Run complete pipeline."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ensure_dir(config.output_root / f"stage1_{timestamp}")
    
    # We create a single 'samples' directory for all outputs
    master_samples_dir = ensure_dir(run_dir / "samples")

    logger.info(f"=== DrumGen-X Pipeline ===")
    
    # 1. Scan & Select
    all_files = scan_dataset(config.dataset_root)
    # If config.n_files is 0, process all? Assuming logic in main handles this or ingestion.
    # Usually random_sample handles limiting.
    selected = random_sample(all_files, config.n_files)
    logger.info(f"Selected {len(selected)} / {len(all_files)} files")

    # 2. Process
    results = []
    total_samples = 0
    
    for audio_path in selected:
        n_samples = process_single_file(audio_path, master_samples_dir, config)
        status = "success" if n_samples > 0 else "no_samples"
        results.append({"file": audio_path.name, "status": status, "samples": n_samples})
        total_samples += n_samples

    # 3. Report
    report = {
        "timestamp": timestamp,
        "results": results,
        "total_samples": total_samples,
        "samples_dir": str(master_samples_dir),
    }
    (run_dir / "pipeline_report.json").write_text(json.dumps(report, indent=2))
    
    # Try to cleanup temp dir if it exists
    temp_dir = run_dir / "temp_demucs"
    if temp_dir.exists():
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    logger.info(f"Stage 1 complete: {total_samples} samples -> {master_samples_dir}")
    return run_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage 1: Audio Preprocessing (Demucs → Onset → Slice → Dedup)",
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
    )

    t_start = time.time()

    if args.input:
        # Single file mode
        audio_path = args.input.resolve()
        if not audio_path.exists():
            print(f"Error: file not found: {audio_path}")
            sys.exit(1)

        config.output_root = args.out_dir
        # For single file, mimicking structure
        run_dir = ensure_dir(args.out_dir / "single_run")
        samples_dir = ensure_dir(run_dir / "samples")
        
        n_samples = process_single_file(audio_path, samples_dir, config)
        
        if n_samples > 0:
            print(f"\nDone: Stage 1 single file -> {samples_dir} ({n_samples} samples)")
        else:
            print(f"\nCompleted with 0 samples extracted.")

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
