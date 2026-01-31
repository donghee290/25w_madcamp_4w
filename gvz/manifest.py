import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


def write_manifest(report_dir: Path, entries: List[Dict[str, Any]]) -> Tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = report_dir / f"manifest_{timestamp}.json"
    csv_path = report_dir / f"manifest_{timestamp}.csv"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)

    fieldnames = [
        "path",
        "rel_path",
        "duration",
        "score",
        "action",
        "cluster",
        "speech_segments",
        "transient_segments",
        "error",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            row = {key: entry.get(key) for key in fieldnames}
            for key in ("speech_segments", "transient_segments"):
                if row.get(key) is not None:
                    row[key] = json.dumps(row[key], ensure_ascii=False)
            writer.writerow(row)

    return json_path, csv_path


def read_manifest(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    if path.suffix.lower() == ".csv":
        with path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            entries = []
            for row in reader:
                row["score"] = float(row["score"]) if row.get("score") else None
                for key in ("speech_segments", "transient_segments"):
                    if row.get(key):
                        row[key] = json.loads(row[key])
                entries.append(row)
            return entries

    raise SystemExit("Manifest must be .json or .csv")
