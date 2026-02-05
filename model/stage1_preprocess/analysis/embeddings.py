"""YAMNet embedding extraction for drum role classification."""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("drumgenx")

# Lazy-load TF to avoid import overhead when not needed
_yamnet_model = None
_yamnet_classes = None


def _load_yamnet():
    """Lazy-load YAMNet model from TensorFlow Hub."""
    global _yamnet_model, _yamnet_classes
    if _yamnet_model is not None:
        return _yamnet_model

    try:
        import tensorflow as tf
        import tensorflow_hub as hub
    except ImportError:
        raise ImportError(
            "YAMNet requires tensorflow and tensorflow_hub. "
            "Install with: pip install tensorflow tensorflow_hub"
        )

    logger.info("Loading YAMNet model from TF Hub...")
    _yamnet_model = hub.load("https://tfhub.dev/google/yamnet/1")
    logger.info("YAMNet loaded successfully")
    return _yamnet_model


def resample_to_16k(y: np.ndarray, sr: int) -> np.ndarray:
    """Resample audio to 16kHz mono float32 for YAMNet input."""
    import librosa
    if sr != 16000:
        y = librosa.resample(y, orig_sr=sr, target_sr=16000)
    # Ensure mono float32
    if y.ndim > 1:
        y = np.mean(y, axis=0)
    return y.astype(np.float32)


def extract_yamnet_embedding(y: np.ndarray, sr: int) -> np.ndarray:
    """Extract 1024-d YAMNet embedding from a single audio sample.

    Args:
        y: Audio waveform
        sr: Sample rate

    Returns:
        1024-d numpy array (mean-pooled over frames)
    """
    model = _load_yamnet()

    # Resample to 16kHz
    y_16k = resample_to_16k(y, sr)

    # YAMNet expects float32 waveform
    scores, embeddings, spectrogram = model(y_16k)

    # embeddings shape: (num_frames, 1024)
    # Mean-pool over time dimension
    emb = np.mean(embeddings.numpy(), axis=0)  # (1024,)

    return emb


def extract_yamnet_scores(y: np.ndarray, sr: int) -> np.ndarray:
    """Extract 521 class scores from YAMNet.

    Returns:
        521-d numpy array (mean-pooled over frames)
    """
    model = _load_yamnet()
    y_16k = resample_to_16k(y, sr)
    scores, embeddings, spectrogram = model(y_16k)
    return np.mean(scores.numpy(), axis=0)  # (521,)


def extract_yamnet_batch(
    samples: List[np.ndarray],
    sr: int,
) -> List[np.ndarray]:
    """Extract YAMNet embeddings for a batch of samples.

    Args:
        samples: List of audio waveforms
        sr: Sample rate

    Returns:
        List of 1024-d embeddings
    """
    embeddings = []
    total = len(samples)

    for i, y in enumerate(samples):
        if (i + 1) % 50 == 0 or i == 0:
            logger.info(f"YAMNet embedding: {i+1}/{total}")

        try:
            emb = extract_yamnet_embedding(y, sr)
            embeddings.append(emb)
        except Exception as e:
            logger.warning(f"YAMNet failed for sample {i}: {e}")
            embeddings.append(np.zeros(1024, dtype=np.float32))

    return embeddings
