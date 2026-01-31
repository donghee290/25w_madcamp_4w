"""Single-script Audio Preprocessor with Smart Deduplication.

Runs Extraction AND Classification/Filtering:
1. Demucs (Separation)
2. Onset Detection
3. Slicing
4. Smart Filtering (Dedup):
   - Clusters similar sounds together using MFCC Cosine Similarity.
   - Keeps only the BEST (Longest) one per cluster.
   - Drastically reduces output file count.

Usage:
    Running this script will scan DATASET_ROOT and save optimized slices to OUTPUT_ROOT.
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
OUTPUT_ROOT = "preprocess_output_optimized"
# ==========================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("drumgenx")

try:
    from drumgenx.separator import extract_drum_stem
    from drumgenx.detector import detect_onsets
    from drumgenx.slicer import slice_hits, normalize_hit
    from drumgenx.utils import load_audio, save_audio, ensure_dir
except ImportError:
    print("Error: drumgenx package not found.")
    sys.exit(1)


def get_feature_vector(y: np.ndarray, sr: int) -> np.ndarray:
    """Extract MFCC feature vector for similarity comparison."""
    # Short sounds (less than 512 samples) might fail MFCC
    if len(y) < 512:
        # Zero padding or just return zeros
        return np.zeros(13)
        
    # Extract MFCC
    # n_fft needs to be smaller than length if length is small
    n_fft = min(2048, len(y))
    hop_length = 512
    if len(y) < hop_length:
        hop_length = len(y) // 2

    try:
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, n_fft=n_fft, hop_length=hop_length)
        return np.mean(mfcc, axis=1) # Average over time -> 1D vector
    except Exception:
        return np.zeros(13)

def cosine_similarity(a, b):
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return np.dot(a, b) / (norm_a * norm_b)

def filter_similar_hits(hits: list, sr: int, similarity_threshold: float = 0.88) -> list:
    """Group similar hits and keep only the longest/best one per group."""
    if not hits:
        return []
        
    logger.info(f"Filtering {len(hits)} hits...")
    
    # 1. Extract features
    items = []
    for i, h in enumerate(hits):
        feat = get_feature_vector(h, sr)
        items.append({
            "index": i,
            "vector": feat,
            "length": len(h),
            "hit": h
        })
        
    # 2. Greedy Clustering
    # Clusters: list of lists of items
    clusters = []
    
    for item in items:
        best_cluster_idx = -1
        best_sim = -1.0
        
        # Compare with existing cluster representative (the first one added)
        for c_idx, cluster in enumerate(clusters):
            pivot = cluster[0] # Pivot is the first member
            sim = cosine_similarity(item["vector"], pivot["vector"])
            
            if sim > best_sim:
                best_sim = sim
                best_cluster_idx = c_idx
                
        # If similar enough, add to cluster
        if best_sim >= similarity_threshold:
            clusters[best_cluster_idx].append(item)
        else:
            # Create new cluster
            clusters.append([item])
            
    logger.info(f"  -> Reduced {len(hits)} raw hits to {len(clusters)} unique sound groups.")

    # 3. Select Representative per Cluster
    # Rule: Pick the LONGEST one in the cluster.
    final_hits = []
    
    for cluster in clusters:
        # Sort by length descending
        cluster.sort(key=lambda x: x["length"], reverse=True)
        best_item = cluster[0]
        final_hits.append(best_item["hit"])
        
    return final_hits


def process_file(audio_path: Path, output_dir: Path):
    """Process file with Deduplication."""
    logger.info(f"=== {audio_path.name} -> {output_dir.name} ===")
    
    file_dir = ensure_dir(output_dir)
    
    try:
        # 1. Sep
        drums_path = extract_drum_stem(
            audio_path, 
            file_dir / "demucs",
            model="htdemucs",
            device="cuda" if sys.platform != "darwin" else "cpu"
        )
        
        # 2. Load
        y, sr = load_audio(drums_path, sr=44100)
        
        # 3. Detect
        onsets = detect_onsets(y, sr, merge_ms=30, backtrack=True)
        if not onsets:
            logger.warning("No onsets.")
            return

        # 4. Slice
        hits = slice_hits(y, sr, onsets, max_duration_s=1.5, fade_out_ms=10.0)
        if not hits:
            return
            
        # 5. [NEW] Filter / Dedup
        raw_count = len(hits)
        # 0.88 threshold is a good balance. Higher = more strict (more files), Lower = more loose (fewer files).
        unique_hits = filter_similar_hits(hits, sr, similarity_threshold=0.88)
        
        # 6. Save
        slices_dir = ensure_dir(file_dir / "slices")
        logger.info(f"Saving {len(unique_hits)} unique slices (compressed from {raw_count})...")
        
        for i, hit in enumerate(unique_hits):
            hit = normalize_hit(hit)
            fname = f"slice_unique_{i:03d}.wav"
            save_audio(slices_dir / fname, hit, sr)
            
        logger.info(f"Done.")
        
    except Exception as e:
        logger.error(f"Failed {audio_path.name}: {e}")

def main():
    root = Path(DATASET_ROOT)
    if not root.exists():
        print(f"Error: Path not found: {root}")
        sys.exit(1)

    print(f"Scanning {root}...")
    extensions = ["*.wav", "*.mp3", "*.m4a", "*.flac"]
    files = []
    for ext in extensions:
        files.extend(root.rglob(ext))
    
    if not files:
        print("No files found.")
        sys.exit(1)

    print(f"Found {len(files)} files.")
    out_root_path = ensure_dir(Path(OUTPUT_ROOT))
    
    for i, f in enumerate(files, 1):
        folder_name = f"sample_{i:03d}"
        target_dir = out_root_path / folder_name
        process_file(f, target_dir)

if __name__ == "__main__":
    main()
