"""Logistic regression classifier for drum role prediction."""

import json
import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .scoring import DrumRole

logger = logging.getLogger("drumgenx")


class RoleClassifier:
    """Logistic regression classifier combining YAMNet + DSP + rule scores.

    Input vector v(si) = concat(z(si), x_dsp(si), s_rule(si))
    - z: 1024-d YAMNet embedding
    - x_dsp: 7-d DSP features (energy, sharpness, band_low/mid/high, attack, decay)
    - s_rule: 5-d rule-based scores
    Total: 1036-d
    """

    EMBEDDING_DIM = 1024
    DSP_DIM = 7
    RULE_DIM = 5
    TOTAL_DIM = EMBEDDING_DIM + DSP_DIM + RULE_DIM

    ROLE_NAMES = [r.value for r in DrumRole]

    def __init__(self):
        self.model = None
        self._fitted = False

    @staticmethod
    def build_feature_vector(
        yamnet_embedding: Optional[np.ndarray],
        dsp_features: Dict[str, float],
        rule_scores: Dict[DrumRole, float],
    ) -> np.ndarray:
        """Concatenate all features into input vector v(si).

        Args:
            yamnet_embedding: 1024-d vector (or None, filled with zeros)
            dsp_features: dict with keys energy, sharpness, band_low/mid/high, attack_time, decay_time
            rule_scores: dict DrumRole -> float

        Returns:
            1036-d numpy array
        """
        # z: 1024
        if yamnet_embedding is not None:
            z = np.asarray(yamnet_embedding, dtype=np.float32)
        else:
            z = np.zeros(RoleClassifier.EMBEDDING_DIM, dtype=np.float32)

        # x_dsp: 7
        x_dsp = np.array([
            dsp_features.get("energy", 0.0),
            dsp_features.get("sharpness", 0.0),
            dsp_features.get("band_low", 0.0),
            dsp_features.get("band_mid", 0.0),
            dsp_features.get("band_high", 0.0),
            dsp_features.get("attack_time", 0.0),
            dsp_features.get("decay_time", 0.0),
        ], dtype=np.float32)

        # s_rule: 5
        s_rule = np.array([
            rule_scores.get(DrumRole.CORE, 0.0),
            rule_scores.get(DrumRole.ACCENT, 0.0),
            rule_scores.get(DrumRole.MOTION, 0.0),
            rule_scores.get(DrumRole.FILL, 0.0),
            rule_scores.get(DrumRole.TEXTURE, 0.0),
        ], dtype=np.float32)

        return np.concatenate([z, x_dsp, s_rule])

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        max_iter: int = 1000,
    ) -> None:
        """Train the logistic regression classifier.

        Args:
            X: (n_samples, 1036) feature matrix
            y: (n_samples,) integer labels (0-4 for 5 roles)
        """
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        self._scaler = StandardScaler()
        X_scaled = self._scaler.fit_transform(X)

        self.model = LogisticRegression(
            multi_class="multinomial",
            solver="lbfgs",
            max_iter=max_iter,
            C=1.0,
        )
        self.model.fit(X_scaled, y)
        self._fitted = True

        logger.info(f"Classifier trained on {len(X)} samples, "
                     f"accuracy: {self.model.score(X_scaled, y):.3f}")

    def predict_proba(self, v: np.ndarray) -> Dict[DrumRole, float]:
        """Predict role probabilities for a single sample.

        Args:
            v: 1036-d feature vector

        Returns:
            Dict[DrumRole, float] - 5-class softmax probabilities
        """
        if not self._fitted:
            raise RuntimeError("Classifier not fitted. Call fit() or load() first.")

        v_scaled = self._scaler.transform(v.reshape(1, -1))
        probs = self.model.predict_proba(v_scaled)[0]

        return {DrumRole(self.ROLE_NAMES[i]): float(p)
                for i, p in enumerate(probs)}

    def predict_batch(self, X: np.ndarray) -> List[Dict[DrumRole, float]]:
        """Predict probabilities for a batch of samples."""
        if not self._fitted:
            raise RuntimeError("Classifier not fitted.")

        X_scaled = self._scaler.transform(X)
        all_probs = self.model.predict_proba(X_scaled)

        results = []
        for probs in all_probs:
            results.append({
                DrumRole(self.ROLE_NAMES[i]): float(p)
                for i, p in enumerate(probs)
            })
        return results

    def save(self, path: Path) -> None:
        """Save fitted model to disk."""
        if not self._fitted:
            raise RuntimeError("Cannot save unfitted classifier.")

        data = {
            "model": self.model,
            "scaler": self._scaler,
        }
        with open(path, "wb") as f:
            pickle.dump(data, f)
        logger.info(f"Classifier saved to {path}")

    def load(self, path: Path) -> None:
        """Load fitted model from disk."""
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.model = data["model"]
        self._scaler = data["scaler"]
        self._fitted = True
        logger.info(f"Classifier loaded from {path}")

    @staticmethod
    def role_to_label(role: DrumRole) -> int:
        """Convert DrumRole to integer label."""
        return RoleClassifier.ROLE_NAMES.index(role.value)

    @staticmethod
    def label_to_role(label: int) -> DrumRole:
        """Convert integer label back to DrumRole."""
        return DrumRole(RoleClassifier.ROLE_NAMES[label])


def self_label_bootstrap(
    all_dsp_features: List[Dict[str, float]],
    all_rule_scores: List[Dict[DrumRole, float]],
    all_yamnet_embeddings: Optional[List[np.ndarray]] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Create training data using rule-based labels as ground truth (bootstrap).

    This is used when no manual labels are available. The rule-based classifier
    provides initial labels, and the logistic regression learns to combine
    YAMNet embeddings with DSP features for potentially better classification.

    Returns:
        (X, y) training data
    """
    from .scoring import get_best_role

    n = len(all_dsp_features)
    X_list = []
    y_list = []

    for i in range(n):
        yamnet_emb = all_yamnet_embeddings[i] if all_yamnet_embeddings else None

        v = RoleClassifier.build_feature_vector(
            yamnet_embedding=yamnet_emb,
            dsp_features=all_dsp_features[i],
            rule_scores=all_rule_scores[i],
        )
        X_list.append(v)

        # Use rule-based label as ground truth
        role, _ = get_best_role(all_rule_scores[i])
        y_list.append(RoleClassifier.role_to_label(role))

    return np.array(X_list), np.array(y_list)
