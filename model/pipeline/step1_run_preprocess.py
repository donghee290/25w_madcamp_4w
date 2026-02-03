"""Dummy Audio Preprocessor (Extraction + Dedup ONLY)

1. Demucs (Drum Stem Extraction)
2. Onset Detection (Slicing)
3. Strict Deduplication (No Classification)
4. Flat Dummy Output (dummy_XXXXX.wav)
"""

import sys
import logging
from pathlib import Path
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
    from stage1_preprocess.separation.separator import extract_drum_stem
    from stage1_preprocess.analysis.detector import detect_onsets
    from stage1_preprocess.slicing.slicer import slice_hits, normalize_hit
    from stage1_preprocess.io.utils import load_audio, save_audio, ensure_dir
except ImportError:
    print("Error: stage1_preprocess package not found.")
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

def main():
    root = Path(DATASET_ROOT)
    out_root = ensure_dir(Path(OUTPUT_ROOT))
    
    # Hide temp file in subfolder
    temp_root = ensure_dir(out_root / ".processing")

    files = list(root.rglob("*.wav")) + list(root.rglob("*.mp3"))
    if not files:
        print("No audio files found.")
        return

    print(f"Processing {len(files)} files into {OUTPUT_ROOT}...")
    
    global_count = 0
    for f_idx, f_path in enumerate(files, 1):
        try:
            # 1. Extract
            logger.info(f"[{f_idx}/{len(files)}] {f_path.name}")
            drums_path = extract_drum_stem(f_path, temp_root / f"f{f_idx}")
            
            # 2. Slice
            y, sr = load_audio(drums_path, sr=44100)
            onsets = detect_onsets(y, sr, merge_ms=30)
            hits = slice_hits(y, sr, onsets, max_duration_s=1.5)
            
            # 3. Filter overlapping (Strict 0.98)
            unique_hits = filter_hits(hits, sr, threshold=0.98)
            
            # 4. Save as DUMMY
            for h in unique_hits:
                global_count += 1
                h = normalize_hit(h)
                save_audio(out_root / f"dummy_{global_count:05d}.wav", h, sr)
                
            logger.info(f"   -> Added {len(unique_hits)} unique dummy samples.")
            
        except Exception as e:
            logger.error(f"Error matching {f_path.name}: {e}")

    print(f"\nFinished! Total {global_count} dummy samples saved in {OUTPUT_ROOT}")

if __name__ == "__main__":
    main()
