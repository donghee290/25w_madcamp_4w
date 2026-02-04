# backend/model_loader.py
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


def _run_step(project_root: Path, pipeline_dir: Path, step_name: str, cmd_args: list[str]) -> None:
    cmd = [sys.executable, str(pipeline_dir / step_name)] + cmd_args
    print(f"\n[pipeline] Running {step_name} ...")
    print(f"[cmd] {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=str(project_root))
    print(f"[pipeline] {step_name} Success.\n")


def _get_latest_file(directory: Path, pattern: str) -> Path:
    files = list(directory.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files matching {pattern} in {directory}")

    def extract_version(p: Path) -> int:
        try:
            return int(p.stem.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            return 0

    return sorted(files, key=extract_version)[-1]


def _get_latest_stage_dir(parent: Path, prefix: str) -> Path:
    # 예: stage1_YYYYMMDD_HHMMSS
    dirs = sorted([p for p in parent.glob(f"{prefix}*") if p.is_dir()])
    if not dirs:
        raise FileNotFoundError(f"No directory starting with {prefix} in {parent}")
    return dirs[-1]


@dataclass
class PipelineResult:
    project_name: str
    bpm: float
    seed: int
    style: str
    output_root: str
    mp3_path: str
    wav_path: str
    elapsed_sec: float


class SoundRoutineModel:
    """
    - model/main.py 구조 그대로: subprocess로 step1~7 실행
    - Flask에서 단일 인스턴스로 사용
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.model_dir = (self.project_root / "model").resolve()
        self.pipeline_dir = (self.model_dir / "pipeline").resolve()
        self.outs_root = (self.project_root / "outs").resolve()

        if not self.pipeline_dir.exists():
            raise RuntimeError(f"pipeline dir not found: {self.pipeline_dir}")

    def run_pipeline(
        self,
        input_dir: Path,
        project_name: str = "project_001",
        bpm: float = 120.0,
        seed: int = 42,
        style: str = "rock",
        progressive: bool = True,
        repeat_full: int = 8,
    ) -> Dict:
        """
        input_dir: raw audio directory (uploaded files)
        returns: dict for JSON response
        """
        start_time = time.time()

        project_name = project_name.strip() or "project_001"
        output_root = (self.outs_root / project_name).resolve()
        output_root.mkdir(parents=True, exist_ok=True)

        dirs = {
            "s1": output_root / "1_preprocess",
            "s2": output_root / "2_role",
            "s3": output_root / "3_grid",
            "s4": output_root / "4_model_gen",
            "s5": output_root / "5_midi",
            "s6": output_root / "6_editor",
            "s7": output_root / "7_final",
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)

        # Stage 1
        _run_step(self.project_root, self.pipeline_dir, "step1_run_preprocess.py", [
            "--input_dir", str(input_dir),
            "--out_dir", str(dirs["s1"]),
        ])
        latest_s1_dir = _get_latest_stage_dir(dirs["s1"], "stage1_")

        # Stage 2
        _run_step(self.project_root, self.pipeline_dir, "step2_run_role_assignment.py", [
            "--input_dir", str(latest_s1_dir),
            "--out_dir", str(dirs["s2"]),
            "--limit", "0",
        ])
        pools_json = _get_latest_file(dirs["s2"], "role_pools_*.json")

        # Stage 3
        _run_step(self.project_root, self.pipeline_dir, "step3_run_grid_and_skeleton.py", [
            "--out_dir", str(dirs["s3"]),
            "--bpm", str(float(bpm)),
            "--style", str(style),
            "--seed", str(int(seed)),
            "--pools_json", str(pools_json),
        ])
        grid_json = _get_latest_file(dirs["s3"], "grid_*.json")
        # (주의) 사용자가 올려준 model/main.py에선 skeleton_*.json을 기대
        # 현재 코드베이스에선 event_grid_*.json일 수도 있으니 둘 다 대응
        try:
            skeleton_json = _get_latest_file(dirs["s3"], "skeleton_*.json")
        except FileNotFoundError:
            skeleton_json = _get_latest_file(dirs["s3"], "event_grid_*.json")

        # Stage 4
        # main.py에선 --skeleton_json, 기존엔 --events_json인 적도 있었음.
        # 여기서는 둘 다 시도: 먼저 skeleton_json 옵션으로, 실패하면 events_json으로 재시도.
        try:
            _run_step(self.project_root, self.pipeline_dir, "step4_run_model_transformer.py", [
                "--grid_json", str(grid_json),
                "--skeleton_json", str(skeleton_json),
                "--pools_json", str(pools_json),
                "--out_dir", str(dirs["s4"]),
                "--seed", str(int(seed)),
                "--sample_root", str(dirs["s1"]),
            ])
        except subprocess.CalledProcessError:
            _run_step(self.project_root, self.pipeline_dir, "step4_run_model_transformer.py", [
                "--grid_json", str(grid_json),
                "--events_json", str(skeleton_json),
                "--pools_json", str(pools_json),
                "--out_dir", str(dirs["s4"]),
                "--seed", str(int(seed)),
                "--sample_root", str(dirs["s1"]),
            ])

        notes_json = _get_latest_file(dirs["s4"], "event_grid_transformer_*.json")

        # Stage 5
        cmd5 = [
            "--grid_json", str(grid_json),
            "--notes_json", str(notes_json),
            "--pools_json", str(pools_json),
            "--out_dir", str(dirs["s5"]),
            "--seed", str(int(seed)),
        ]
        if progressive:
            cmd5 += ["--progressive", "1", "--repeat_full", str(int(repeat_full))]

        _run_step(self.project_root, self.pipeline_dir, "step5_run_note_and_midi.py", cmd5)

        final_events_json = _get_latest_file(dirs["s5"], "event_grid_*.json")
        # stage5에서 grid_*.json이 새로 나오면 그걸 사용
        try:
            grid_json = _get_latest_file(dirs["s5"], "grid_*.json")
        except FileNotFoundError:
            pass

        # Stage 6
        _run_step(self.project_root, self.pipeline_dir, "step6_run_editor.py", [
            "--grid_json", str(grid_json),
            "--event_grid", str(final_events_json),
            "--out_dir", str(dirs["s6"]),
            "--seed", str(int(seed)),
            "--sample_root", str(dirs["s1"]),
            "--render_preview", "1",
        ])
        editor_events_json = _get_latest_file(dirs["s6"], "event_grid_*.json")

        # Stage 7
        name = f"{project_name}_final"
        _run_step(self.project_root, self.pipeline_dir, "step7_run_render_final.py", [
            "--grid_json", str(grid_json),
            "--event_grid_json", str(editor_events_json),
            "--sample_root", str(dirs["s1"]),
            "--out_dir", str(dirs["s7"]),
            "--name", name,
        ])

        mp3_path = (dirs["s7"] / f"{name}.mp3").resolve()
        wav_path = (dirs["s7"] / f"{name}.wav").resolve()

        elapsed = time.time() - start_time
        res = PipelineResult(
            project_name=project_name,
            bpm=float(bpm),
            seed=int(seed),
            style=str(style),
            output_root=str(output_root),
            mp3_path=str(mp3_path),
            wav_path=str(wav_path),
            elapsed_sec=float(elapsed),
        )
        return res.__dict__

    def get_latest_output(self, project_name: str) -> Dict:
        project_name = project_name.strip()
        output_root = (self.outs_root / project_name).resolve()
        final_dir = output_root / "7_final"
        if not final_dir.exists():
            raise FileNotFoundError(f"final dir not found: {final_dir}")

        # *_final.mp3 중 최신 mtime
        mp3s = list(final_dir.glob("*_final.mp3"))
        if not mp3s:
            raise FileNotFoundError(f"No final mp3 found in: {final_dir}")

        latest_mp3 = max(mp3s, key=lambda p: p.stat().st_mtime)
        latest_wav = latest_mp3.with_suffix(".wav")

        return {
            "project_name": project_name,
            "mp3_path": str(latest_mp3.resolve()),
            "wav_path": str(latest_wav.resolve()),
            "final_dir": str(final_dir.resolve()),
        }