"""One-shot drum hit extraction and kit organization."""

import json
from pathlib import Path
from typing import Dict, List, Tuple

import librosa
import numpy as np

from .scoring import DrumRole, calculate_role_scores, get_best_role
from .features import extract_dsp_features
from .utils import logger, save_audio, ensure_dir


def slice_hits(
    y_drums: np.ndarray,
    sr: int,
    onsets: List[int],
    max_duration_s: float = 0.5,
    fade_out_ms: float = 50.0,
    trim_db: float = 40.0,
) -> List[np.ndarray]:
    """Extract individual drum hits from onset positions.

    Each hit spans from onset to next onset (or onset + max_duration_s).
    Applies fade-out and trims trailing silence.
    """
    hits = []
    fade_samples = int(fade_out_ms / 1000.0 * sr)
    max_samples = int(max_duration_s * sr)

    for i, onset in enumerate(onsets):
        # End = next onset or onset + max_duration
        if i + 1 < len(onsets):
            end = min(onsets[i + 1], onset + max_samples)
        else:
            end = min(onset + max_samples, len(y_drums))

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
) -> Tuple[Dict[DrumRole, List[np.ndarray]], List[Dict]]:
    """Classify hits using DSP features + role scoring.

    Returns (organized_dict, all_hit_data) where all_hit_data has features+scores per hit.
    """
    organized: Dict[DrumRole, List[np.ndarray]] = {role: [] for role in DrumRole}
    all_hit_data = []

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
    organized: Dict[DrumRole, List[np.ndarray]],
    sr: int,
    output_dir: Path,
    normalize: bool = True,
    hit_data: List[Dict] = None,
) -> Path:
    """Save organized hits to disk in role subdirectories.

    Returns path to kit_manifest.json.
    """
    output_dir = ensure_dir(output_dir)

    manifest = {
        "sr": sr,
        "roles": {},
    }

    if hit_data is not None:
        manifest["hit_data"] = hit_data

    total = 0
    for role, samples in organized.items():
        if not samples:
            continue

        role_dir = ensure_dir(output_dir / role.value)
        manifest["roles"][role.value] = []

        for i, hit in enumerate(samples, start=1):
            if normalize:
                hit = normalize_hit(hit)

            fname = f"{role.value}_{i:03d}.wav"
            save_audio(role_dir / fname, hit, sr)
            manifest["roles"][role.value].append({
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


def build_kit_from_audio(
    y_drums: np.ndarray,
    sr: int,
    onsets: List[int],
    output_dir: Path,
    max_duration_s: float = 0.5,
    fade_out_ms: float = 50.0,
) -> Tuple[Path, Dict[DrumRole, List[np.ndarray]]]:
    """Full pipeline: slice -> classify -> organize -> save.

    Returns (manifest_path, organized_dict).
    """
    hits = slice_hits(y_drums, sr, onsets, max_duration_s, fade_out_ms)
    organized, hit_data = classify_and_organize(hits, sr)
    manifest_path = save_kit(organized, sr, output_dir, hit_data=hit_data)
    return manifest_path, organized
