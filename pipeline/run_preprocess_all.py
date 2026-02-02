from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


HOSPITAL_ROOT = r"C:\Project\kaist\4_week\165.가상공간 환경음 매칭 데이터\01-1.정식개방데이터\Training\01.원천데이터\TS_1.공간_1.현실 공간_환경_002.병원_wav"
LIBRARY_ROOT = r"C:\Project\kaist\4_week\165.가상공간 환경음 매칭 데이터\01-1.정식개방데이터\Training\01.원천데이터\TS_1.공간_1.현실 공간_환경_022.도서관_wav"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--hospital_root", type=str, default=HOSPITAL_ROOT)
    p.add_argument("--library_root", type=str, default=LIBRARY_ROOT)
    p.add_argument("--out_hospital", type=str, default="dummy_dataset_hospital_1.5s2.5s")
    p.add_argument("--out_library", type=str, default="dummy_dataset_library_1.5s2.5s")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--min_sec", type=float, default=1.5)
    p.add_argument("--max_sec", type=float, default=2.5)
    p.add_argument("--dedup_threshold", type=float, default=0.5)
    p.add_argument("--skip_demucs", action="store_true")
    return p.parse_args()


def _run_one(dataset_root: str, output_root: str, args: argparse.Namespace) -> None:
    cmd = [
        sys.executable,
        str(Path(__file__).parent / "run_preprocess.py"),
        "--dataset_root",
        dataset_root,
        "--output_root",
        output_root,
        "--limit",
        str(args.limit),
        "--seed",
        str(args.seed),
        "--min_sec",
        str(args.min_sec),
        "--max_sec",
        str(args.max_sec),
        "--dedup_threshold",
        str(args.dedup_threshold),
    ]
    if args.skip_demucs:
        cmd.append("--skip_demucs")

    subprocess.run(cmd, check=True)


def main() -> None:
    args = _parse_args()

    print("[RUN] Hospital dataset")
    _run_one(args.hospital_root, args.out_hospital, args)

    print("[RUN] Library dataset")
    _run_one(args.library_root, args.out_library, args)

    print("[DONE] All preprocessing complete")


if __name__ == "__main__":
    main()
