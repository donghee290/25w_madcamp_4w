"""Deduplication of similar drum hits via MFCC+DSP clustering."""

import numpy as np
from typing import List, Tuple
from scipy.spatial.distance import pdist, squareform
from scipy.cluster.hierarchy import linkage, fcluster
import librosa
from ..analysis.features import extract_dsp_features
from ..io.utils import logger


def extract_mfcc_features(y: np.ndarray, sr: int) -> np.ndarray:
    """Extract 13-dimensional MFCC mean vector from audio.

    Args:
        y: Audio time series
        sr: Sample rate

    Returns:
        13-dimensional MFCC mean vector
    """
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    return np.mean(mfcc, axis=1)


def build_feature_vector(y: np.ndarray, sr: int) -> np.ndarray:
    """Combine MFCC (13 dims) + DSP features (7 dims) = 20-dimensional vector.

    Args:
        y: Audio time series
        sr: Sample rate

    Returns:
        20-dimensional normalized feature vector
    """
    # Extract MFCC features (13 dims)
    mfcc_features = extract_mfcc_features(y, sr)

    # Extract DSP features (7 dims)
    dsp_dict = extract_dsp_features(y, sr)
    dsp_features = np.array([
        dsp_dict['energy'],
        dsp_dict['sharpness'],
        dsp_dict['band_low'],
        dsp_dict['band_mid'],
        dsp_dict['band_high'],
        dsp_dict['attack_time'],
        dsp_dict['decay_time']
    ])

    # Concatenate into 20-dim vector (Raw values)
    # Normalization should be done across the dataset/batch, not per-sample features.
    feature_vector = np.concatenate([mfcc_features, dsp_features])

    return feature_vector


def deduplicate_hits(hits: List[np.ndarray], sr: int, threshold: float = 0.5, max_count: int = None) -> Tuple[List[np.ndarray], dict]:
    """Deduplicate drum hits using MFCC+DSP clustering.

    Args:
        hits: List of audio arrays (drum hit samples)
        sr: Sample rate
        threshold: Distance threshold for clustering (default: 0.5)

    Returns:
        Tuple of (representative_hits_list, stats_dict)
        - representative_hits_list: List of representative samples (one per cluster)
        - stats_dict: Dictionary with deduplication statistics
    """
    # Edge case: 0 or 1 hits
    if len(hits) == 0:
        return [], {
            "total_hits": 0,
            "n_clusters": 0,
            "n_representatives": 0,
            "cluster_sizes": []
        }

    if len(hits) == 1:
        return hits, {
            "total_hits": 1,
            "n_clusters": 1,
            "n_representatives": 1,
            "cluster_sizes": [1]
        }

    logger.info(f"Building feature vectors for {len(hits)} hits...")

    # Step 1: Build 20-dim feature vectors for all hits
    feature_matrix = []
    for hit in hits:
        feature_vector = build_feature_vector(hit, sr)
        feature_matrix.append(feature_vector)

    feature_matrix = np.array(feature_matrix)

    # Normalize features across the batch (StandardScaler style)
    # Each feature dimension should have mean=0, std=1 across all hits.
    # tailored for distance metric stability.
    
    # Avoid div by zero
    eps = 1e-8
    mean = np.mean(feature_matrix, axis=0)
    std = np.std(feature_matrix, axis=0) + eps
    
    feature_matrix = (feature_matrix - mean) / std
    
    # Optional: Weight MFCC vs DSP? 
    # Currently treating all 20 dims equally.


    # Check if all features are identical (edge case)
    if np.allclose(feature_matrix, feature_matrix[0], rtol=1e-5, atol=1e-8):
        logger.warning("All feature vectors are identical, returning first hit only")
        return [hits[0]], {
            "total_hits": len(hits),
            "n_clusters": 1,
            "n_representatives": 1,
            "cluster_sizes": [len(hits)]
        }

    # Step 2: Compute pairwise cosine distance matrix
    distances = pdist(feature_matrix, metric='cosine')
    distance_matrix = squareform(distances)

    # Step 3: Hierarchical clustering
    linkage_matrix = linkage(distances, method='average')
    cluster_labels = fcluster(linkage_matrix, t=threshold, criterion='distance')

    n_clusters = len(np.unique(cluster_labels))
    logger.info(f"Clustered {len(hits)} hits → {n_clusters} clusters (threshold={threshold})")

    # Step 4: Select representative from each cluster
    # Score = RMS energy × sqrt(duration) — prefers loud AND long samples
    representative_hits = []
    cluster_sizes = []

    for cluster_id in np.unique(cluster_labels):
        cluster_indices = np.where(cluster_labels == cluster_id)[0]
        cluster_hits = [hits[i] for i in cluster_indices]

        scores = [
            np.sqrt(np.mean(hit ** 2)) * np.sqrt(len(hit) / sr)
            for hit in cluster_hits
        ]

        best_idx = np.argmax(scores)
        representative_hits.append((len(cluster_hits), cluster_hits[best_idx])) # Store (size, hit)
        cluster_sizes.append(len(cluster_hits))

    # Sort by cluster size (descending) to keep most frequent/meaningful sounds
    representative_hits.sort(key=lambda x: x[0], reverse=True)
    
    # Unwrap hits
    sorted_hits = [x[1] for x in representative_hits]
    
    if max_count is not None and len(sorted_hits) > max_count:
        sorted_hits = sorted_hits[:max_count]
        logger.info(f"Limited output to top {max_count} samples (from {len(representative_hits)} clusters)")

    representative_hits = sorted_hits

    logger.info(f"Selected {len(representative_hits)} representative samples")

    stats = {
        "total_hits": len(hits),
        "n_clusters": n_clusters,
        "n_representatives": len(representative_hits),
        "cluster_sizes": cluster_sizes
    }

    return representative_hits, stats
