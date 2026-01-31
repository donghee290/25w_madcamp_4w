import math
from typing import Optional

import numpy as np


def assign_action(score: Optional[float], low: float, high: float) -> str:
    if score is None:
        return "error"
    if score >= low:
        return "suppress"
    return "keep"


def apply_gain(y: np.ndarray, gain_db: float) -> np.ndarray:
    gain = math.pow(10.0, gain_db / 20.0)
    return y * gain
