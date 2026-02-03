"""One-shot drum hit extraction and kit organization."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import librosa
import numpy as np

from ..scoring import DrumRole, calculate_role_scores, get_best_role
from ..analysis.features import extract_dsp_features
from ..cleaning.dedup import deduplicate_hits
from ..io.utils import logger, save_audio, ensure_dir


def slice_hits(
    y_drums: np.ndarray,
    sr: int,
    onsets: List[int],
    max_duration_s: float = 2.0,
    fade_out_ms: float = 50.0,
    trim_db: float = 60.0,
    min_duration_s: float = 0.05,
) -> List[np.ndarray]:
    """Extract individual drum hits from onset positions.

    Each hit spans from onset to min(next_onset, onset+max_duration).
    A minimum duration is guaranteed so release tails are preserved.
    Applies fade-out and trims trailing silence.
    """
    hits = []
    fade_samples = int(fade_out_ms / 1000.0 * sr)
    max_samples = int(max_duration_s * sr)
    min_samples = int(min_duration_s * sr)

    for i, onset in enumerate(onsets):
        # End = next onset or onset + max_duration, but at least min_duration
        if i + 1 < len(onsets):
            next_onset = onsets[i + 1]
            end = min(max(next_onset, onset + min_samples), onset + max_samples)
        else:
            end = min(onset + max_samples, len(y_drums))

        end = min(end, len(y_drums))
        hit = y_drums[onset:end].copy()

        if hit.size == 0:
            continue

        # Trim trailing silence
        trimmed, _ = librosa.effects.trim(hit, top_db=trim_db)
        if trimmed.size < int(0.005 * sr):  # Less than 5ms: skip
            continue

        # Apply fade-out
        if fade_samples > 0 and fade_samples < len(trimmed):
            fade = np.linspace(1.0, 0.0, fade_samples)
            trimmed[-fade_samples:] *= fade

        hits.append(trimmed)

    logger.info(f"Sliced {len(hits)} hits from {len(onsets)} onsets")
    return hits


def normalize_hit(y: np.ndarray, target_db: float = -1.0) -> np.ndarray:
    """Peak normalize a hit to target dB."""
    peak = np.max(np.abs(y))
    if peak < 1e-8:
        return y
    target_amp = 10.0 ** (target_db / 20.0)
    return y * (target_amp / peak)


def classify_and_organize(
    hits: List[np.ndarray],
    sr: int,
    skip_classification: bool = True,
) -> Tuple[Dict[str, List[np.ndarray]], List[Dict]]:
    """Classify hits using DSP features + role scoring.

    Returns (organized_dict, all_hit_data) where all_hit_data has features+scores per hit.

    If skip_classification=True (default), saves all hits as "dummy" without role classification.
    """
    all_hit_data = []

    if skip_classification:
        # Save all hits as dummy without classification
        organized = {"dummy": hits}
        for i, hit in enumerate(hits):
            all_hit_data.append({
                "role": "dummy",
                "index": i,
                "duration_s": round(len(hit) / sr, 4),
            })
        logger.info(f"  dummy: {len(hits)} hits (classification skipped)")
        return organized, all_hit_data

    # Original classification logic (disabled by default)
    organized: Dict[DrumRole, List[np.ndarray]] = {role: [] for role in DrumRole}

    for hit in hits:
        feats = extract_dsp_features(hit, sr)
        scores = calculate_role_scores(feats)
        role, score = get_best_role(scores)
        organized[role].append(hit)
        all_hit_data.append({
            "features": feats,
            "scores": {r.value: float(s) for r, s in scores.items()},
            "role": role.value,
            "best_score": float(score),
        })

    # Log distribution
    for role, samples in organized.items():
        if samples:
            logger.info(f"  {role.value}: {len(samples)} hits")

    return organized, all_hit_data


def save_kit(
    organized: Dict,
    sr: int,
    output_dir: Path,
    normalize: bool = True,
    hit_data: List[Dict] = None,
    dedup_stats: Optional[Dict] = None,
) -> Path:
    """Save organized hits to disk in role subdirectories.

    Returns path to kit_manifest.json.
    Supports both DrumRole enum keys and string keys (e.g., "dummy").
    """
    output_dir = ensure_dir(output_dir)

    manifest = {
        "sr": sr,
        "roles": {},
    }

    if hit_data is not None:
        manifest["hit_data"] = hit_data
    if dedup_stats is not None:
        manifest["dedup_stats"] = dedup_stats

    total = 0
    for role, samples in organized.items():
        if not samples:
            continue

        # Handle both DrumRole enum and string keys
        role_name = role.value if hasattr(role, 'value') else str(role)
        role_dir = ensure_dir(output_dir / role_name)
        manifest["roles"][role_name] = []

        for i, hit in enumerate(samples, start=1):
            if normalize:
                hit = normalize_hit(hit)

            fname = f"{role_name}_{i:03d}.wav"
            save_audio(role_dir / fname, hit, sr)
            manifest["roles"][role_name].append({
                "file": fname,
                "duration_s": round(len(hit) / sr, 4),
            })
            total += 1

    manifest["total_samples"] = total

    manifest_path = output_dir / "kit_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"Kit saved: {total} samples -> {output_dir}")
    return manifest_path


def save_deduped_kit(
    representatives: List[np.ndarray],
    sr: int,
    output_dir: Path,
    dedup_stats: dict,
    normalize: bool = True,
    classify: bool = True,
) -> Path:
    """Save deduplicated hits with optional role classification.

    If classify=True, organizes into role subdirs (like save_kit).
    If classify=False, saves to flat samples/ directory.
    Returns path to kit_manifest.json.
    """
    output_dir = ensure_dir(output_dir)

    if classify and representatives:
        organized, hit_data = classify_and_organize(representatives, sr)
        return save_kit(organized, sr, output_dir, hit_data=hit_data, dedup_stats=dedup_stats, normalize=normalize)

    # Flat save (no classification)
    samples_dir = ensure_dir(output_dir / "samples")
    samples_info = []
    for i, hit in enumerate(representatives, start=1):
        feats = extract_dsp_features(hit, sr)
        scores = calculate_role_scores(feats)
        role, score = get_best_role(scores)

        if normalize:
            hit = normalize_hit(hit)

        fname = f"sample_{i:03d}.wav"
        save_audio(samples_dir / fname, hit, sr)
        samples_info.append({
            "file": fname,
            "duration_s": round(len(hit) / sr, 4),
            "features": feats,
            "role": role.value,
            "role_score": round(float(score), 4),
            "all_scores": {r.value: round(float(s), 4) for r, s in scores.items()},
            "cluster_id": i,
        })

    manifest = {
        "sr": sr,
        "total_samples": len(representatives),
        "dedup_stats": dedup_stats,
        "samples": samples_info,
    }

    manifest_path = output_dir / "kit_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"Deduped kit saved: {len(representatives)} samples -> {output_dir}")
    return manifest_path


def build_kit_from_audio(
    y_drums: np.ndarray,
    sr: int,
    onsets: List[int],
    output_dir: Path,
    max_duration_s: float = 2.0,
    fade_out_ms: float = 50.0,
    trim_db: float = 60.0,
    min_hit_duration_s: float = 0.0,
    dedup_enabled: bool = True,
    dedup_threshold: float = 0.5,
) -> Tuple[Path, List[np.ndarray]]:
    """Full pipeline: slice -> filter short -> deduplicate -> classify -> save.

    Returns (manifest_path, representative_hits).
    """
    hits = slice_hits(y_drums, sr, onsets, max_duration_s, fade_out_ms, trim_db)

    min_samples = int(min_hit_duration_s * sr)
    before = len(hits)
    hits = [h for h in hits if len(h) >= min_samples]
    if before != len(hits):
        logger.info(
            f"Filtered {before - len(hits)} short hits (<{min_hit_duration_s}s), {len(hits)} remaining"
        )

    representatives = hits
    dedup_stats = None
    if dedup_enabled:
        representatives, dedup_stats = deduplicate_hits(hits, sr, threshold=dedup_threshold)

    organized, hit_data = classify_and_organize(representatives, sr)
    manifest_path = save_kit(organized, sr, output_dir, hit_data=hit_data, dedup_stats=dedup_stats)

    return manifest_path, representatives
