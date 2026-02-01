"""Full DrumGen-X pipeline orchestrator."""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .config import PipelineConfig
from .scoring import DrumRole, calculate_role_scores
from .features import extract_dsp_features
from .ingest import scan_dataset, random_sample
from .separator import extract_drum_stem
from .detector import detect_onsets
from .slicer import build_kit_from_audio, normalize_hit
from .sequencer import load_kit, render_and_save
from .utils import logger, load_audio, save_audio, ensure_dir
from .pool_balancer import balance_pools
from .events import generate_skeleton, EventGrid

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

        # Step 4: Slice, classify, organize
        kit_dir = file_dir / "kit"
        manifest_path, organized = build_kit_from_audio(
            y_drums, config.sr, onsets, kit_dir,
            max_duration_s=config.max_hit_duration_s,
            fade_out_ms=config.fade_out_ms,
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
    """Merge kits and BALANCE pools using pool_balancer."""
    master_dir = ensure_dir(output_dir / "master_kit")
    
    # 1. Gather all samples and calculate scores
    all_items = []
    all_scores = []
    current_assignments = []
    
    # Track origin for debugging/metadata
    origins = [] 

    logger.info("Merging kits and re-scoring for balancing...")
    
    for kit_dir in kit_dirs:
        kit = load_kit(kit_dir, sr=sr)
        for role, samples in kit.items():
            for i, s in enumerate(samples):
                # Recalculate scores for balancing logic
                feats = extract_dsp_features(s, sr)
                scores = calculate_role_scores(feats)
                # Convert DrumRole enum keys to scores
                # pool_balancer expects Dict[DrumRole, float]
                
                all_items.append(s)
                all_scores.append(scores)
                current_assignments.append(role)
                origins.append(f"{kit_dir.name}/{role.value}_{i}")

    # 2. Run Pool Balancer
    # Initial pool structure for balancer
    # Actually balancer takes lists directly.
    # We construct initial pools just to check counts? Balancer re-builds them.
    
    # Create dummy pool dict for input if needed, but balancer mainly needs the lists.
    # wait, balance_pools signature:
    # (pools: Dict, all_scores, all_items, pool_assignments, ...)
    # It requires 'pools' but seemingly rebuilds it? Let's verify pool_balancer.py
    # assignments = list(pool_assignments) ... returns balanced, assignments
    
    dummy_pools = {r: [] for r in DrumRole} # Not strictly used for logic, just typings
    
    balanced_pool, new_assignments = balance_pools(
        dummy_pools,
        all_scores,
        all_items,
        current_assignments,
        min_core=2,    # Ensure at least 2 kicks
        min_accent=2,  # Ensure at least 2 snares
        min_motion=4,  # Ensure at least 4 hihats
        max_per_role=best_per_class, # Cap size
    )
    
    # 3. Save Master Kit
    manifest = {"sr": sr, "roles": {}}
    total = 0
    
    for role, samples in balanced_pool.items():
        if not samples:
            continue
            
        role_dir = ensure_dir(master_dir / role.value)
        manifest["roles"][role.value] = []
        
        # Sort by energy? Balancer didn't sort them, just grouped.
        # Let's sort by energy for the user
        # Recalc rms or use features?
        samples_with_rms = []
        for s in samples:
            rms = np.sqrt(np.mean(s**2))
            samples_with_rms.append((rms, s))
        
        samples_with_rms.sort(key=lambda x: x[0], reverse=True)
        
        for i, (rms, sample) in enumerate(samples_with_rms, start=1):
            sample = normalize_hit(sample)
            fname = f"{role.value}_{i:03d}.wav"
            save_audio(role_dir / fname, sample, sr)
            
            manifest["roles"][role.value].append({
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
