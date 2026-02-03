"""Full DrumGen-X pipeline orchestrator."""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np

from .config import PipelineConfig
from .io.ingest import scan_dataset, random_sample
from .separation.separator import extract_drum_stem
from .analysis.detector import detect_onsets
from .slicing.slicer import build_kit_from_audio, normalize_hit
from .sequencer import load_kit, render_and_save
from .io.utils import logger, load_audio, save_audio, ensure_dir
from .events import generate_skeleton

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
    origins = []

    logger.info("Merging kits (simplified - no role classification)...")

    for kit_dir in kit_dirs:
        kit = load_kit(kit_dir, sr=sr)
        for role, role_samples in kit.items():
            role_name = role.value if hasattr(role, 'value') else str(role)
            for i, s in enumerate(role_samples):
                all_samples.append(s)
                origins.append(f"{kit_dir.name}/{role_name}_{i}")

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
    
    # 2. HipHop (Variation of skeleton? or different generator?)
    # Currently generate_skeleton produces a generic beat.
    # We can modify it via 'motion_density' or just let it be.
    # Let's add variations.
    
    grid_dense = generate_skeleton(bars=bars, bpm=bpm, motion_density=8, seed=99)
    path_dense = render_and_save(grid_dense, kit, loops_dir / f"test_dense_{int(bpm)}.wav", sr=sr, reverb=True)
    outputs.append(path_dense)

    return outputs


def run_full_pipeline(config: PipelineConfig) -> Path:
    """Run complete pipeline."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ensure_dir(config.output_root / f"run_{timestamp}")

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
