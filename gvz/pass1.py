from multiprocessing import Pool
from statistics import median
from typing import Dict, List, Tuple

from .clustering import run_dbscan
from .config import Pass1Config
from .features import extract_features
from .io_utils import list_audio_files
from .manifest import write_manifest
from .scoring import assign_action


def pass1(config: Pass1Config) -> Tuple[str, str]:
    files = list_audio_files(config.input_dir)
    if config.include_name:
        include_name = config.include_name.lower()
        files = [p for p in files if include_name in p.name.lower()]
    if not files:
        raise SystemExit("No audio files found.")

    work_items = [
        (str(p), str(config.input_dir), config.sr, config.n_mfcc, config.use_harmonic)
        for p in files
    ]
    results: List[Dict[str, object]] = []

    if config.num_workers and config.num_workers > 1:
        with Pool(processes=config.num_workers) as pool:
            for item in pool.imap_unordered(extract_features, work_items, chunksize=8):
                results.append(item)
    else:
        for item in map(extract_features, work_items):
            results.append(item)

    run_dbscan(results, config.dbscan_eps, config.dbscan_min_samples)

    scores = [r.get("score") for r in results if isinstance(r.get("score"), float)]
    low_threshold = config.low_threshold
    high_threshold = config.high_threshold
    if scores:
        scores_sorted = sorted(scores)
        p50 = median(scores_sorted)
        p75 = scores_sorted[int(0.75 * (len(scores_sorted) - 1))]
        p90 = scores_sorted[int(0.90 * (len(scores_sorted) - 1))]
        print(f"Score p50={p50:.4f} p75={p75:.4f} p90={p90:.4f}")
        print(f"Suggested thresholds: low~{p75:.4f}, high~{p90:.4f}")
        if config.auto_threshold:
            low_idx = int(config.auto_low_quantile * (len(scores_sorted) - 1))
            high_idx = int(config.auto_high_quantile * (len(scores_sorted) - 1))
            low_threshold = scores_sorted[low_idx]
            high_threshold = scores_sorted[high_idx]
            print(
                f"Auto thresholds: low={low_threshold:.4f} "
                f"high={high_threshold:.4f} "
                f"(q{config.auto_low_quantile:.2f}/q{config.auto_high_quantile:.2f})"
            )

    for item in results:
        speech_segments = item.get("speech_segments") or []
        if not speech_segments:
            item["action"] = "keep"
        else:
            item["action"] = assign_action(item.get("score"), low_threshold, high_threshold)

    json_path, csv_path = write_manifest(config.report_dir, results)
    return str(json_path), str(csv_path)
