"""Stage 1: Full Audio Preprocessing Pipeline

Executes the complete Stage 1 preprocessing:
  1. Dataset scan & file selection
  2. Demucs drum stem extraction (CPU/GPU auto-select)
  3. Multi-band onset detection
  4. Hit slicing + deduplication
  5. DSP role classification (CORE/ACCENT/MOTION/FILL/TEXTURE)
  6. Pool balancing → master kit output

Usage:
  python -m pipeline.step1_run_preprocess --dataset-root /path/to/audio --output-root /path/to/output
  python -m pipeline.step1_run_preprocess --input /single/file.wav --output-root /path/to/output
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

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
from stage1_preprocess.io.utils import setup_logging, load_audio, save_audio, ensure_dir
from stage1_preprocess.io.ingest import scan_dataset, random_sample
from stage1_preprocess.separation.separator import extract_drum_stem
from stage1_preprocess.analysis.detector import detect_onsets
from stage1_preprocess.analysis.features import extract_dsp_features
from stage1_preprocess.slicing.slicer import (
    slice_hits,
    normalize_hit,
    classify_and_organize,
    build_kit_from_audio,
    save_kit,
)
from stage1_preprocess.cleaning.dedup import deduplicate_hits
from stage1_preprocess.scoring import DrumRole, calculate_role_scores, get_best_role
from stage1_preprocess.pool_balancer import balance_pools
from stage1_preprocess.run_pipeline import process_single_file, merge_kits, run_full_pipeline

logger = logging.getLogger("drumgenx.step1")


# ---------------------------------------------------------------------------
# Pipeline runners
# ---------------------------------------------------------------------------

def run_single_file(
    audio_path: Path,
    output_root: Path,
    config: PipelineConfig,
) -> dict:
    """Process a single audio file through all Stage 1 steps."""
    t0 = time.time()
    file_dir = ensure_dir(output_root / audio_path.stem)
    result = {"file": str(audio_path), "status": "failed", "samples": 0}

    logger.info(f"{'='*60}")
    logger.info(f"Processing: {audio_path.name}")
    logger.info(f"  Output:   {file_dir}")
    logger.info(f"  Device:   {config.demucs_device}")
    logger.info(f"{'='*60}")

    try:
        # Step 1: Drum stem extraction
        logger.info("[1/5] Extracting drum stem via Demucs ...")
        drums_path = extract_drum_stem(
            audio_path, file_dir / "demucs",
            model=config.demucs_model,
            device=config.demucs_device,
            sr=config.sr,
            chunk_duration_s=config.chunk_duration_s,
        )
        y_drums, _ = load_audio(drums_path, sr=config.sr)
        logger.info(f"  Drum stem: {len(y_drums)/config.sr:.1f}s")

        # Step 2: Multi-band onset detection
        logger.info("[2/5] Detecting onsets (multi-band) ...")
        onsets = detect_onsets(
            y_drums, config.sr,
            merge_ms=config.onset_merge_ms,
            backtrack=config.onset_backtrack,
        )
        if not onsets:
            logger.warning(f"  No onsets detected — skipping {audio_path.name}")
            result["status"] = "no_onsets"
            return result
        logger.info(f"  Detected {len(onsets)} onsets")

        # Step 3: Hit slicing
        logger.info("[3/5] Slicing hits ...")
        hits = slice_hits(
            y_drums, config.sr, onsets,
            max_duration_s=config.max_hit_duration_s,
            fade_out_ms=config.fade_out_ms,
            trim_db=config.trim_silence_db,
        )
        # Filter short hits
        min_samples = int(config.min_hit_duration_s * config.sr)
        if min_samples > 0:
            before = len(hits)
            hits = [h for h in hits if len(h) >= min_samples]
            if before != len(hits):
                logger.info(f"  Filtered {before - len(hits)} short hits, {len(hits)} remaining")

        # Step 4: Deduplication
        dedup_stats = None
        if config.dedup_enabled:
            logger.info("[4/5] Deduplicating (MFCC+DSP clustering) ...")
            hits, dedup_stats = deduplicate_hits(hits, config.sr, threshold=config.dedup_threshold)
            logger.info(f"  {dedup_stats['n_representatives']} unique from {dedup_stats['total_hits']} total")
        else:
            logger.info("[4/5] Deduplication disabled — skipping")

        # Step 5: Role classification + save
        logger.info("[5/5] Classifying roles & saving kit ...")
        organized, hit_data = classify_and_organize(hits, config.sr)
        kit_dir = file_dir / "kit"
        manifest_path = save_kit(
            organized, config.sr, kit_dir,
            hit_data=hit_data, dedup_stats=dedup_stats,
        )

        n_samples = sum(len(v) for v in organized.values())
        elapsed = time.time() - t0
        logger.info(f"  Kit saved: {n_samples} samples in {elapsed:.1f}s")

        result["status"] = "success"
        result["samples"] = n_samples
        result["kit_dir"] = str(kit_dir)
        result["manifest"] = str(manifest_path)
        result["elapsed_s"] = round(elapsed, 1)
        if dedup_stats:
            result["dedup"] = dedup_stats

        # Print per-role distribution (supports both DrumRole enum and string keys)
        for role, samples in organized.items():
            role_name = role.value if hasattr(role, 'value') else str(role)
            count = len(samples)
            if count > 0:
                logger.info(f"    {role_name:>8s}: {count}")

    except Exception as e:
        logger.error(f"  FAILED: {e}", exc_info=True)
        result["error"] = str(e)

    return result


def run_batch(
    config: PipelineConfig,
    file_list: list[Path] | None = None,
) -> Path:
    """Run Stage 1 on a batch of files (scan dataset or use provided list)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ensure_dir(config.output_root / f"stage1_{timestamp}")

    logger.info(f"{'='*60}")
    logger.info(f"  Stage 1 Preprocessing Pipeline")
    logger.info(f"  Output: {run_dir}")
    logger.info(f"  Device: {config.demucs_device}")
    logger.info(f"{'='*60}")

    # Gather files
    if file_list:
        selected = file_list
    else:
        all_files = scan_dataset(config.dataset_root)
        selected = random_sample(all_files, config.n_files)
    logger.info(f"Processing {len(selected)} files")

    # Process each file
    results = []
    kit_dirs = []
    for i, audio_path in enumerate(selected, 1):
        logger.info(f"\n[{i}/{len(selected)}] {audio_path.name}")
        result = run_single_file(audio_path, run_dir / "files", config)
        results.append(result)
        if result["status"] == "success" and "kit_dir" in result:
            kit_dirs.append(Path(result["kit_dir"]))

    # Merge kits if multiple
    master_dir = None
    if len(kit_dirs) > 1:
        logger.info(f"\nMerging {len(kit_dirs)} kits into master kit ...")
        master_dir = merge_kits(
            kit_dirs, run_dir,
            sr=config.sr,
            best_per_class=config.best_per_class,
        )
    elif len(kit_dirs) == 1:
        master_dir = kit_dirs[0]
        logger.info(f"\nSingle kit, no merge needed: {master_dir}")

    # Summary report
    success = sum(1 for r in results if r["status"] == "success")
    total_samples = sum(r.get("samples", 0) for r in results)
    report = {
        "timestamp": timestamp,
        "device": config.demucs_device,
        "files_processed": len(selected),
        "files_success": success,
        "files_failed": len(selected) - success,
        "total_samples": total_samples,
        "master_kit": str(master_dir) if master_dir else None,
        "results": results,
    }

    report_path = run_dir / "stage1_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info(f"\n{'='*60}")
    logger.info(f"  Stage 1 Complete")
    logger.info(f"  Success: {success}/{len(selected)} files")
    logger.info(f"  Samples: {total_samples}")
    if master_dir:
        logger.info(f"  Master:  {master_dir}")
    logger.info(f"  Report:  {report_path}")
    logger.info(f"{'='*60}")

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
        "--dataset-root", type=Path,
        help="Root directory with audio files (batch mode)",
    )
    input_group.add_argument(
        "--input", type=Path,
        help="Single audio file to process",
    )

    # Output
    parser.add_argument(
        "--output-root", type=Path, default=Path("stage1_output"),
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
        output_root=args.output_root,
        onset_merge_ms=args.onset_merge_ms,
        max_hit_duration_s=args.max_hit_duration,
        min_hit_duration_s=args.min_hit_duration,
        fade_out_ms=args.fade_out_ms,
        dedup_threshold=args.dedup_threshold,
        dedup_enabled=not args.no_dedup,
        n_files=args.n_files,
        best_per_class=args.best_per_class,
    )

    t_start = time.time()

    if args.input:
        # Single file mode
        audio_path = args.input.resolve()
        if not audio_path.exists():
            print(f"Error: file not found: {audio_path}")
            sys.exit(1)

        config.output_root = args.output_root
        result = run_single_file(audio_path, args.output_root, config)

        if result["status"] == "success":
            print(f"\nDone: {result['samples']} samples -> {result.get('kit_dir', '?')}")
        else:
            print(f"\nFailed: {result.get('error', result['status'])}")
            sys.exit(1)

    else:
        # Batch mode
        config.dataset_root = args.dataset_root.resolve()
        if not config.dataset_root.exists():
            print(f"Error: dataset root not found: {config.dataset_root}")
            sys.exit(1)

        run_dir = run_batch(config)
        elapsed = time.time() - t_start
        print(f"\nStage 1 complete in {elapsed:.0f}s -> {run_dir}")


if __name__ == "__main__":
    main()
