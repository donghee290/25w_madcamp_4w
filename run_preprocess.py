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


def process_file(audio_path: Path, output_root: Path, file_idx: int):
    """Process file and save FLATTENED results to output_root."""
    logger.info(f"=== Processing [{file_idx}] {audio_path.name} ===")
    
    # Temp folder for demucs (hidden from user)
    temp_dir = ensure_dir(output_root / ".temp" / f"sample_{file_idx:03d}")
    
    try:
        # 1. Sep
        drums_path = extract_drum_stem(
            audio_path, 
            temp_dir,
            model="htdemucs",
            device="cuda" if sys.platform != "darwin" else "cpu"
        )
        
        # 2. Load
        y, sr = load_audio(drums_path, sr=44100)
        
        # 3. Detect
        onsets = detect_onsets(y, sr, merge_ms=30, backtrack=True)
        if not onsets:
            return

        # 4. Slice
        hits = slice_hits(y, sr, onsets, max_duration_s=1.5, fade_out_ms=10.0)
        if not hits:
            return
            
        # 5. Filter / Dedup (Longest per cluster)
        unique_hits = filter_similar_hits(hits, sr, similarity_threshold=0.88)
        
        # 6. Save FLATTENED (No subfolders!)
        # Prefix with sample ID to prevent name collision
        prefix = f"sample{file_idx:03d}"
        
        for i, hit in enumerate(unique_hits):
            hit = normalize_hit(hit)
            # e.g. preprocess_output/sample001_slice00.wav
            fname = f"{prefix}_slice{i:02d}.wav"
            save_audio(output_root / fname, hit, sr)
            
        logger.info(f"Saved {len(unique_hits)} files to root.")
        
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
    
    # Ensure Output Root exists
    out_root_path = ensure_dir(Path(OUTPUT_ROOT))
    
    for i, f in enumerate(files, 1):
        process_file(f, out_root_path, i)

if __name__ == "__main__":
    main()
