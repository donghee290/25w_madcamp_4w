"""Dummy Audio Preprocessor (Extraction + Dedup ONLY)

1. Demucs (Drum Stem Extraction)
2. Onset Detection (Slicing)
3. Strict Deduplication (No Classification)
4. Flat Dummy Output (dummy_XXXXX.wav)
"""

import sys
import logging
from pathlib import Path
import argparse
import random

# Ensure repo root is on sys.path when running as a script
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import numpy as np
import librosa

# ==========================================
# [USER CONFIG]
# ==========================================
DATASET_ROOT = r"C:\Project\kaist\4_week\165.가상공간 환경음 매칭 데이터\01-1.정식개방데이터\Training\01.원천데이터\TS_1.공간_1.현실 공간_환경_002.병원_wav"
OUTPUT_ROOT = "dummy_dataset"
# ==========================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("dummy_gen")

try:
    from stage1_drumgenx.separator import extract_drum_stem
    from stage1_drumgenx.detector import detect_onsets
    from stage1_drumgenx.slicer import slice_hits, normalize_hit
    from stage1_drumgenx.utils import load_audio, save_audio, ensure_dir
    from stage1_drumgenx.dedup import deduplicate_hits
except ImportError:
    print("Error: drumgenx package not found.")
    sys.exit(1)

def get_fingerprint(y, sr):
    """Simple feature vector for similarity check."""
    if len(y) < 512: return np.zeros(13)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    return np.mean(mfcc, axis=1)

def cosine_sim(a, b):
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0: return 0.0
    return np.dot(a, b) / (na * nb)

def filter_hits(hits, sr, threshold=0.98):
    """Keep only one representative for overlapping/similar sounds."""
    if not hits: return []
    
    # Extract fingerprints
    data = []
    for h in hits:
        data.append({'fp': get_fingerprint(h, sr), 'len': len(h), 'hit': h})
        
    clusters = []
    for item in data:
        found = False
        for cluster in clusters:
            if cosine_sim(item['fp'], cluster[0]['fp']) > threshold:
                cluster.append(item)
                found = True
                break
        if not found:
            clusters.append([item])
            
    # Pick the longest from each cluster
    results = []
    for cluster in clusters:
        cluster.sort(key=lambda x: x['len'], reverse=True)
        results.append(cluster[0]['hit'])
    return results

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset_root", type=str, default=DATASET_ROOT)
    p.add_argument("--output_root", type=str, default=OUTPUT_ROOT)
    p.add_argument("--limit", type=int, default=0, help="0이면 전체, 아니면 랜덤 N개")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--skip_demucs", action="store_true", help="Demucs 분리 없이 원본 오디오로 처리")
    p.add_argument("--min_sec", type=float, default=1.0, help="출력 히트 최소 길이(초)")
    p.add_argument("--max_sec", type=float, default=2.0, help="출력 히트 최대 길이(초)")
    p.add_argument("--dedup_threshold", type=float, default=0.5, help="중복 제거 거리 임계값")
    return p.parse_args()


def _trim_max(y, sr, max_sec):
    if not max_sec or max_sec <= 0:
        return y
    max_len = int(sr * float(max_sec))
    if len(y) > max_len:
        return y[:max_len]
    return y


def _pad_min(y, sr, min_sec):
    if not min_sec or min_sec <= 0:
        return y
    min_len = int(sr * float(min_sec))
    if len(y) >= min_len:
        return y
    pad = min_len - len(y)
    return np.pad(y, (0, pad), mode="constant")


def main():
    args = _parse_args()
    root = Path(args.dataset_root)
    out_root = ensure_dir(Path(args.output_root))
    
    # Hide temp file in subfolder
    temp_root = ensure_dir(out_root / ".processing")

    files = list(root.rglob("*.wav")) + list(root.rglob("*.mp3"))
    if not files:
        print("No audio files found.")
        return
    if args.limit and args.limit > 0:
        rng = random.Random(int(args.seed))
        rng.shuffle(files)
        files = files[: args.limit]

    if args.min_sec > args.max_sec:
        logger.warning("min_sec > max_sec, swapping values")
        args.min_sec, args.max_sec = args.max_sec, args.min_sec

    print(f"Processing {len(files)} files into {out_root}...")
    
    global_count = 0
    for f_idx, f_path in enumerate(files, 1):
        try:
            # 1. Extract (or skip Demucs)
            logger.info(f"[{f_idx}/{len(files)}] {f_path.name}")
            if args.skip_demucs:
                drums_path = f_path
            else:
                drums_path = extract_drum_stem(f_path, temp_root / f"f{f_idx}")
            
            # 2. Slice
            y, sr = load_audio(drums_path, sr=44100)
            onsets = detect_onsets(y, sr, merge_ms=30)
            hits = slice_hits(y, sr, onsets, max_duration_s=float(args.max_sec))

            # 3. Deduplicate (MFCC+DSP clustering)
            trimmed_hits = [_trim_max(h, sr, args.max_sec) for h in hits]
            unique_hits, stats = deduplicate_hits(trimmed_hits, sr, threshold=float(args.dedup_threshold))
            
            # 4. Save as DUMMY
            for h in unique_hits:
                global_count += 1
                h = _pad_min(h, sr, args.min_sec)
                h = normalize_hit(h)
                save_audio(out_root / f"dummy_{global_count:05d}.wav", h, sr)
                
            logger.info(
                f"   -> Added {len(unique_hits)} unique dummy samples. "
                f"(clusters={stats.get('n_clusters')}, total_hits={stats.get('total_hits')})"
            )
            
        except Exception as e:
            logger.error(f"Error matching {f_path.name}: {e}")

    print(f"\nFinished! Total {global_count} dummy samples saved in {out_root}")

if __name__ == "__main__":
    main()
