# backend/model_loader.py
from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, List

# Logger setup
logger = logging.getLogger(__name__)

AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


def _run_step(project_root: Path, pipeline_dir: Path, step_name: str, cmd_args: list[str]) -> None:
    cmd = [sys.executable, str(pipeline_dir / step_name)] + cmd_args
    logger.info(f"[pipeline] Running {step_name} with args: {cmd_args}")
    print(f"[pipeline] Running {step_name} ...")
    subprocess.check_call(cmd, cwd=str(project_root))
    print(f"[pipeline] {step_name} Success.")


def _get_latest_file(directory: Path, pattern: str) -> Path:
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
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
    if not parent.exists():
        raise FileNotFoundError(f"Parent directory not found: {parent}")
    dirs = sorted([p for p in parent.glob(f"{prefix}*") if p.is_dir()])
    if not dirs:
        raise FileNotFoundError(f"No directory starting with {prefix} in {parent}")
    return dirs[-1]


@dataclass
class JobInfo:
    job_id: str
    project_name: str
    status: str  # "running", "completed", "failed"
    progress: str  # e.g., "Step 3/7"
    result: Optional[Dict] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)


class SoundRoutineModel:
    """
    Manages SoundRoutine pipeline execution with state persistence and job tracking.
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.model_dir = (self.project_root / "model").resolve()
        self.pipeline_dir = (self.model_dir / "pipeline").resolve()
        self.outs_root = (self.project_root / "outs").resolve()

        if not self.pipeline_dir.exists():
            raise RuntimeError(f"pipeline dir not found: {self.pipeline_dir}")

        # In-memory job store
        self._jobs: Dict[str, JobInfo] = {}
        self._job_lock = threading.Lock()

    # ---- State Management ----

    def _get_project_dir(self, project_name: str) -> Path:
        return self.outs_root / project_name

    def _get_state_path(self, project_name: str) -> Path:
        return self._get_project_dir(project_name) / "state.json"

    def get_state(self, project_name: str) -> Dict[str, Any]:
        """Reads state.json for the project."""
        p = self._get_state_path(project_name)
        if not p.exists():
            return {}
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read state.json for {project_name}: {e}")
            return {}

    def update_state(self, project_name: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Updates specific keys in state.json and saves it."""
        current = self.get_state(project_name)
        current.update(updates)
        current["updated_at"] = time.time()

        p = self._get_state_path(project_name)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
        return current

    # ---- Job Management ----

    def start_job(self, func, *args, **kwargs) -> str:
        """Starts a background thread for the given function and returns a job_id."""
        job_id = str(uuid.uuid4())
        project_name = kwargs.get("project_name", "unknown")

        with self._job_lock:
            self._jobs[job_id] = JobInfo(
                job_id=job_id,
                project_name=project_name,
                status="running",
                progress="Starting...",
            )

        def wrapper():
            try:
                # Execute the function
                # Note: func is expected to return a result dict
                res = func(*args, **kwargs)
                with self._job_lock:
                    job = self._jobs[job_id]
                    job.status = "completed"
                    job.progress = "Done"
                    job.result = res
            except Exception as e:
                logger.exception(f"Job {job_id} failed: {e}")
                with self._job_lock:
                    job = self._jobs[job_id]
                    job.status = "failed"
                    job.error = str(e)

        t = threading.Thread(target=wrapper, daemon=True)
        t.start()
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict]:
        with self._job_lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return {
                "job_id": job.job_id,
                "project_name": job.project_name,
                "status": job.status,
                "progress": job.progress,
                "result": job.result,
                "error": job.error,
                "created_at": job.created_at,
            }

    def _update_job_progress(self, project_name: str, progress: str):
        # Find active job for this project (simple approximation)
        # In a real system, we'd pass job_id down.
        # For MVP, we just log it or update most recent running job for project
        with self._job_lock:
            for job in self._jobs.values():
                if job.project_name == project_name and job.status == "running":
                    job.progress = progress

    # ---- Pipeline Execution ----

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
        Legacy wrapper for full pipeline execution (Stage 1-7).
        Updates state.json throughout the process.
        This is SYNCHRONOUS (blocks).
        """
        # 1. Initialize State
        self.update_state(project_name, {
            "uploads_dir": str(input_dir),
            "config": {
                "bpm": bpm,
                "seed": seed,
                "style": style,
                "progressive": progressive,
                "repeat_full": repeat_full
            }
        })

        # 2. Run from Stage 1
        return self.run_from_stage(project_name, from_stage=1)

    def run_from_stage(
        self,
        project_name: str,
        from_stage: int,
        config_overrides: Optional[Dict] = None
    ) -> Dict:
        """
        Executes pipeline starting from `from_stage`.
        Reads inputs from `state.json` and updates it after each step.
        """
        start_time = time.time()
        project_dir = self._get_project_dir(project_name)
        project_dir.mkdir(parents=True, exist_ok=True)

        # Merge config
        state = self.get_state(project_name)
        config = state.get("config", {})
        if config_overrides:
            config.update(config_overrides)
            self.update_state(project_name, {"config": config})

        # Parameters
        bpm = float(config.get("bpm", 120.0))
        seed = int(config.get("seed", 42))
        style = str(config.get("style", "rock"))
        progressive = bool(config.get("progressive", True))
        repeat_full = int(config.get("repeat_full", 8))

        # Output Dirs
        dirs = {
            "s1": project_dir / "1_preprocess",
            "s2": project_dir / "2_role",
            "s3": project_dir / "3_grid",
            "s4": project_dir / "4_model_gen",
            "s5": project_dir / "5_midi",
            "s6": project_dir / "6_editor",
            "s7": project_dir / "7_final",
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)

        # ---- Stage 1: Preprocess ----
        if from_stage <= 1:
            self._update_job_progress(project_name, "Running Stage 1: Preprocessing...")
            uploads_dir = state.get("uploads_dir")
            if not uploads_dir:
                # If run_pipeline wasn't called, uploads_dir might be missing.
                # Check default location
                default_upload = project_dir / "uploads"
                if default_upload.exists():
                    uploads_dir = str(default_upload)
                else:
                    raise ValueError("No uploads_dir in state. Please upload files first.")

            _run_step(self.project_root, self.pipeline_dir, "step1_run_preprocess.py", [
                "--input_dir", str(uploads_dir),
                "--out_dir", str(dirs["s1"]),
            ])
            latest_s1 = _get_latest_stage_dir(dirs["s1"], "stage1_")
            state = self.update_state(project_name, {"latest_s1_dir": str(latest_s1)})

        # ---- Stage 2: Role Assignment ----
        if from_stage <= 2:
            self._update_job_progress(project_name, "Running Stage 2: Role Assignment...")
            latest_s1 = state.get("latest_s1_dir")
            if not latest_s1:
                latest_s1 = str(_get_latest_stage_dir(dirs["s1"], "stage1_"))

            _run_step(self.project_root, self.pipeline_dir, "step2_run_role_assignment.py", [
                "--input_dir", str(latest_s1),
                "--out_dir", str(dirs["s2"]),
                "--limit", "0",
            ])
            pools_json = _get_latest_file(dirs["s2"], "role_pools_*.json")
            state = self.update_state(project_name, {"latest_pools_json": str(pools_json)})

        # ---- Stage 3: Grid & Skeleton ----
        if from_stage <= 3:
            self._update_job_progress(project_name, "Running Stage 3: Grid & Skeleton...")
            pools_json = state.get("latest_pools_json")
            if not pools_json:
                # Try finding it if state is missing
                pools_json = str(_get_latest_file(dirs["s2"], "role_pools_*.json"))

            _run_step(self.project_root, self.pipeline_dir, "step3_run_grid_and_skeleton.py", [
                "--out_dir", str(dirs["s3"]),
                "--bpm", str(bpm),
                "--style", style,
                "--seed", str(seed),
                "--pools_json", str(pools_json),
            ])
            grid_json = _get_latest_file(dirs["s3"], "grid_*.json")
            try:
                skeleton_json = _get_latest_file(dirs["s3"], "skeleton_*.json")
            except FileNotFoundError:
                skeleton_json = _get_latest_file(dirs["s3"], "event_grid_*.json")

            state = self.update_state(project_name, {
                "latest_grid_json": str(grid_json),
                "latest_skeleton_json": str(skeleton_json)
            })

        # ---- Stage 4: Transformer Gen ----
        if from_stage <= 4:
            self._update_job_progress(project_name, "Running Stage 4: AI Generation...")
            grid_json = state.get("latest_grid_json")
            skeleton_json = state.get("latest_skeleton_json")
            pools_json = state.get("latest_pools_json")
            # fallback reads
            if not grid_json:
                grid_json = str(_get_latest_file(dirs["s3"], "grid_*.json"))
            if not skeleton_json:
                try:
                    skeleton_json = str(_get_latest_file(dirs["s3"], "skeleton_*.json"))
                except FileNotFoundError:
                    skeleton_json = str(_get_latest_file(dirs["s3"], "event_grid_*.json"))
            if not pools_json:
                pools_json = str(_get_latest_file(dirs["s2"], "role_pools_*.json"))
            
            # Use 'latest_s1_dir' for sample root
            sample_root = state.get("latest_s1_dir")
            if not sample_root:
                # Fallback to finding it on disk
                sample_root = str(_get_latest_stage_dir(dirs["s1"], "stage1_"))

            try:
                _run_step(self.project_root, self.pipeline_dir, "step4_run_model_transformer.py", [
                    "--grid_json", str(grid_json),
                    "--skeleton_json", str(skeleton_json),
                    "--pools_json", str(pools_json),
                    "--out_dir", str(dirs["s4"]),
                    "--seed", str(seed),
                    "--sample_root", str(sample_root),
                ])
            except subprocess.CalledProcessError:
                # Retry with --events_json legacy arg if needed
                _run_step(self.project_root, self.pipeline_dir, "step4_run_model_transformer.py", [
                    "--grid_json", str(grid_json),
                    "--events_json", str(skeleton_json),
                    "--pools_json", str(pools_json),
                    "--out_dir", str(dirs["s4"]),
                    "--seed", str(seed),
                    "--sample_root", str(sample_root),
                ])
            
            notes_json = _get_latest_file(dirs["s4"], "event_grid_transformer_*.json")
            state = self.update_state(project_name, {"latest_transformer_json": str(notes_json)})

        # ---- Stage 5: Note & Layout ----
        if from_stage <= 5:
            self._update_job_progress(project_name, "Running Stage 5: Arrangement...")
            grid_json = state.get("latest_grid_json")
            notes_json = state.get("latest_transformer_json")
            pools_json = state.get("latest_pools_json")
            
            # fallbacks
            if not grid_json: grid_json = str(_get_latest_file(dirs["s3"], "grid_*.json"))
            if not notes_json: notes_json = str(_get_latest_file(dirs["s4"], "event_grid_transformer_*.json"))
            if not pools_json: pools_json = str(_get_latest_file(dirs["s2"], "role_pools_*.json"))
            
            # Use same seed for consistent results unless changed
            cmd5 = [
                "--grid_json", str(grid_json),
                "--notes_json", str(notes_json),
                "--pools_json", str(pools_json),
                "--out_dir", str(dirs["s5"]),
                "--seed", str(seed),
            ]
            if progressive:
                cmd5 += ["--progressive", "1", "--repeat_full", str(repeat_full)]

            _run_step(self.project_root, self.pipeline_dir, "step5_run_note_and_midi.py", cmd5)
            
            final_events = _get_latest_file(dirs["s5"], "event_grid_*.json")
            # If stage5 updated the grid (expansion), grab it
            try:
                new_grid = _get_latest_file(dirs["s5"], "grid_*.json")
                grid_json = str(new_grid)
            except FileNotFoundError:
                pass
            
            state = self.update_state(project_name, {
                "latest_event_grid_json": str(final_events),
                "latest_grid_json": str(grid_json) # Update grid if expanded
            })

        # ---- Stage 6: Editor ----
        if from_stage <= 6:
            self._update_job_progress(project_name, "Running Stage 6: Editor...")
            grid_json = state.get("latest_grid_json")
            event_grid = state.get("latest_event_grid_json")
            sample_root = state.get("latest_s1_dir")

            # Fallbacks
            if not grid_json: grid_json = str(_get_latest_file(dirs["s3"], "grid_*.json"))
            if not event_grid: event_grid = str(_get_latest_file(dirs["s5"], "event_grid_*.json"))
            if not sample_root: sample_root = str(_get_latest_stage_dir(dirs["s1"], "stage1_"))

            _run_step(self.project_root, self.pipeline_dir, "step6_run_editor.py", [
                "--grid_json", str(grid_json),
                "--event_grid", str(event_grid),
                "--out_dir", str(dirs["s6"]),
                "--seed", str(seed),
                "--sample_root", str(sample_root),
                "--render_preview", "1",
            ])
            editor_events = _get_latest_file(dirs["s6"], "event_grid_*.json")
            state = self.update_state(project_name, {"latest_editor_json": str(editor_events)})

        # ---- Stage 7: Render Final ----
        if from_stage <= 7:
            self._update_job_progress(project_name, "Running Stage 7: Rendering...")
            grid_json = state.get("latest_grid_json")
            editor_events = state.get("latest_editor_json")
            sample_root = state.get("latest_s1_dir")

            # Fallbacks
            if not grid_json: grid_json = str(_get_latest_file(dirs["s3"], "grid_*.json"))
            if not editor_events: editor_events = str(_get_latest_file(dirs["s6"], "event_grid_*.json"))
            if not sample_root: sample_root = str(_get_latest_stage_dir(dirs["s1"], "stage1_"))

            name = f"{project_name}_final"
            _run_step(self.project_root, self.pipeline_dir, "step7_run_render_final.py", [
                "--grid_json", str(grid_json),
                "--event_grid_json", str(editor_events),
                "--sample_root", str(sample_root),
                "--out_dir", str(dirs["s7"]),
                "--name", name,
            ])
            
            mp3_path = (dirs["s7"] / f"{name}.mp3").resolve()
            wav_path = (dirs["s7"] / f"{name}.wav").resolve()
            
            self.update_state(project_name, {
                "latest_mp3": str(mp3_path),
                "latest_wav": str(wav_path)
            })

        elapsed = time.time() - start_time
        latest_mp3 = state.get("latest_mp3", "")
        latest_wav = state.get("latest_wav", "")
        
        return {
            "project_name": project_name,
            "bpm": bpm,
            "seed": seed,
            "style": style,
            "output_root": str(project_dir),
            "mp3_path": latest_mp3,
            "wav_path": latest_wav,
            "elapsed_sec": elapsed
        }

    def get_latest_output(self, project_name: str) -> Dict:
        # Prefer state.json
        state = self.get_state(project_name)
        if state.get("latest_mp3") and Path(state["latest_mp3"]).exists():
             return {
                "project_name": project_name,
                "mp3_path": state["latest_mp3"],
                "wav_path": state.get("latest_wav", ""),
                "state": state
            }
            
        # Fallback to old glob method if state is missing
        project_name = project_name.strip()
        output_root = (self.outs_root / project_name).resolve()
        final_dir = output_root / "7_final"
        if not final_dir.exists():
            raise FileNotFoundError(f"final dir not found: {final_dir}")

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