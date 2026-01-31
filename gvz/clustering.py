from typing import Any, Dict, List

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler


def run_dbscan(entries: List[Dict[str, Any]], eps: float, min_samples: int) -> None:
    feature_rows = []
    index_map = []
    for i, entry in enumerate(entries):
        mfcc_mean = entry.get("mfcc_mean")
        if mfcc_mean is not None:
            feature_rows.append(mfcc_mean)
            index_map.append(i)

    if len(feature_rows) < max(2, min_samples):
        for entry in entries:
            entry["cluster"] = None
        return

    X = np.array(feature_rows, dtype=float)
    X = StandardScaler().fit_transform(X)
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(X)

    for idx, label in zip(index_map, labels):
        entries[idx]["cluster"] = int(label)

    for i, entry in enumerate(entries):
        if i not in index_map:
            entry["cluster"] = None
