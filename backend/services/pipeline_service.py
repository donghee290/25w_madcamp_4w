import sys
import subprocess
import time
import logging
import os
from pathlib import Path
from typing import Optional, Dict

from .state_manager import StateManager
from .job_manager import JobManager

logger = logging.getLogger(__name__)

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

class PipelineService:
    def __init__(self, project_root: Path, state_manager: StateManager, job_manager: JobManager):
        self.project_root = project_root
        self.state_manager = state_manager
        self.job_manager = job_manager
        
        self.model_dir = (self.project_root / "model").resolve()
        self.pipeline_dir = (self.model_dir / "pipeline").resolve()
        self.outs_root = (self.project_root / "outs").resolve()

    def _get_project_dir(self, beat_name: str) -> Path:
        return self.outs_root / beat_name

    def run_from_stage(
        self,
        project_name: str,
        from_stage: int,
        to_stage: int = 7,  # Added to_stage control
        config_overrides: Optional[Dict] = None
    ) -> Dict:
        """
        Executes pipeline starting from `from_stage` up to `to_stage`.
        Reads inputs from `state.json` and updates it after each step.
        """
        beat_name = project_name
        start_time = time.time()
        project_dir = self._get_project_dir(beat_name)
        project_dir.mkdir(parents=True, exist_ok=True)

        # Merge config
        state = self.state_manager.get_state(beat_name)
        config = state.get("config", {})
        if config_overrides:
            config.update(config_overrides)
            self.state_manager.update_state(beat_name, {"config": config})

        # Parameters
        bpm = float(config.get("bpm", 120.0))
        seed = int(config.get("seed", 42))
        style = str(config.get("style", "rock"))
        progressive = bool(config.get("progressive", True))
        repeat_full = int(config.get("repeat_full", 2))
        
        if progressive and repeat_full > 2:
             repeat_full = 2

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
        if from_stage <= 1 and to_stage >= 1:
            self.job_manager.update_job_progress(beat_name, "Running Stage 1: Preprocessing...")
            uploads_dir = state.get("uploads_dir")
            if not uploads_dir:
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
            state = self.state_manager.update_state(beat_name, {"latest_s1_dir": str(latest_s1)})

        # ---- Stage 2: Role Assignment ----
        if from_stage <= 2 and to_stage >= 2:
            self.job_manager.update_job_progress(beat_name, "Running Stage 2: Role Assignment...")
            latest_s1 = state.get("latest_s1_dir")
            if not latest_s1:
                latest_s1 = str(_get_latest_stage_dir(dirs["s1"], "stage1_"))

            _run_step(self.project_root, self.pipeline_dir, "step2_run_role_assignment.py", [
                "--input_dir", str(latest_s1),
                "--out_dir", str(dirs["s2"]),
                "--limit", "0",
            ])
            pools_json = _get_latest_file(dirs["s2"], "role_pools_*.json")
            state = self.state_manager.update_state(beat_name, {"latest_pools_json": str(pools_json)})

        # ---- Stage 3: Grid & Skeleton ----
        if from_stage <= 3 and to_stage >= 3:
            self.job_manager.update_job_progress(beat_name, "Running Stage 3: Grid & Skeleton...")
            pools_json = state.get("latest_pools_json")
            if not pools_json:
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

            state = self.state_manager.update_state(beat_name, {
                "latest_grid_json": str(grid_json),
                "latest_skeleton_json": str(skeleton_json)
            })

        # ---- Stage 4: Transformer Gen ----
        if from_stage <= 4 and to_stage >= 4:
            self.job_manager.update_job_progress(beat_name, "Running Stage 4: AI Generation...")
            grid_json = state.get("latest_grid_json")
            skeleton_json = state.get("latest_skeleton_json")
            pools_json = state.get("latest_pools_json")
            
            if not grid_json: grid_json = str(_get_latest_file(dirs["s3"], "grid_*.json"))
            if not skeleton_json:
                try:
                    skeleton_json = str(_get_latest_file(dirs["s3"], "skeleton_*.json"))
                except FileNotFoundError:
                    skeleton_json = str(_get_latest_file(dirs["s3"], "event_grid_*.json"))
            if not pools_json: pools_json = str(_get_latest_file(dirs["s2"], "role_pools_*.json"))
            
            sample_root = state.get("latest_s1_dir")
            if not sample_root:
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
                # Retry with legacy args
                _run_step(self.project_root, self.pipeline_dir, "step4_run_model_transformer.py", [
                    "--grid_json", str(grid_json),
                    "--events_json", str(skeleton_json),
                    "--pools_json", str(pools_json),
                    "--out_dir", str(dirs["s4"]),
                    "--seed", str(seed),
                    "--sample_root", str(sample_root),
                ])
            
            notes_json = _get_latest_file(dirs["s4"], "event_grid_transformer_*.json")
            state = self.state_manager.update_state(beat_name, {"latest_transformer_json": str(notes_json)})

        # ---- Stage 5: Note & Layout ----
        if from_stage <= 5 and to_stage >= 5:
            self.job_manager.update_job_progress(beat_name, "Running Stage 5: Arrangement...")
            grid_json = state.get("latest_grid_json")
            notes_json = state.get("latest_transformer_json")
            pools_json = state.get("latest_pools_json")
            
            if not grid_json: grid_json = str(_get_latest_file(dirs["s3"], "grid_*.json"))
            if not notes_json: notes_json = str(_get_latest_file(dirs["s4"], "event_grid_transformer_*.json"))
            if not pools_json: pools_json = str(_get_latest_file(dirs["s2"], "role_pools_*.json"))
            
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
            try:
                new_grid = _get_latest_file(dirs["s5"], "grid_*.json")
                grid_json = str(new_grid)
            except FileNotFoundError:
                pass
            
            state = self.state_manager.update_state(beat_name, {
                "latest_event_grid_json": str(final_events),
                "latest_grid_json": str(grid_json)
            })

        # ---- Stage 6: Editor ----
        if from_stage <= 6 and to_stage >= 6:
            self.job_manager.update_job_progress(beat_name, "Running Stage 6: Editor...")
            grid_json = state.get("latest_grid_json")
            event_grid = state.get("latest_event_grid_json")
            sample_root = state.get("latest_s1_dir")

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
            state = self.state_manager.update_state(beat_name, {"latest_editor_json": str(editor_events)})

        # ---- Stage 7: Render Final ----
        if from_stage <= 7 and to_stage >= 7:
            self.job_manager.update_job_progress(beat_name, "Running Stage 7: Rendering...")
            grid_json = state.get("latest_grid_json")
            editor_events = state.get("latest_editor_json")
            sample_root = state.get("latest_s1_dir")

            if not grid_json: grid_json = str(_get_latest_file(dirs["s3"], "grid_*.json"))
            if not editor_events: editor_events = str(_get_latest_file(dirs["s6"], "event_grid_*.json"))
            if not sample_root: sample_root = str(_get_latest_stage_dir(dirs["s1"], "stage1_"))

            custom_title = config.get("beat_title")
            if custom_title:
                safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in custom_title)
                name = f"{safe_title}_final"
            else:
                name = f"{beat_name}_final"
            
            # Default render is usually wav/mp3 fallback? 
            # We'll just run default which produces wav
            _run_step(self.project_root, self.pipeline_dir, "step7_run_render_final.py", [
                "--grid_json", str(grid_json),
                "--event_grid_json", str(editor_events),
                "--sample_root", str(sample_root),
                "--out_dir", str(dirs["s7"]),
                "--name", name,
                "--format", "wav" # Default
            ])
            
            wav_path = (dirs["s7"] / f"{name}.wav").resolve()
            
            self.state_manager.update_state(beat_name, {
                "latest_wav": str(wav_path)
            })

        elapsed = time.time() - start_time
        state_final = self.state_manager.get_state(beat_name)
        
        return {
            "beat_name": beat_name,
            "bpm": bpm,
            "seed": seed,
            "style": style,
            "output_root": str(project_dir),
            "mp3_path": state_final.get("latest_mp3", ""),
            "wav_path": state_final.get("latest_wav", ""),
            "elapsed_sec": elapsed
        }

    def run_export(self, beat_name: str, fmt: str) -> Path:
        """
        Runs ONLY Stage 7 for a specific format on demand.
        Returns the absolute path to the generated file.
        """
        state = self.state_manager.get_state(beat_name)
        project_dir = self._get_project_dir(beat_name)
        
        # Resolve inputs using latest state
        grid_json = state.get("latest_grid_json")
        editor_events = state.get("latest_editor_json")
        sample_root = state.get("latest_s1_dir")
        config = state.get("config", {})

        dirs = {
            "s3": project_dir / "3_grid",
            "s6": project_dir / "6_editor",
            "s1": project_dir / "1_preprocess",
            "s7": project_dir / "7_final",
        }
        dirs["s7"].mkdir(parents=True, exist_ok=True)

        # Fallbacks if state path is missing (try to guess latest in dir)
        if not grid_json: grid_json = str(_get_latest_file(dirs["s3"], "grid_*.json"))
        if not editor_events: editor_events = str(_get_latest_file(dirs["s6"], "event_grid_*.json"))
        if not sample_root: sample_root = str(_get_latest_stage_dir(dirs["s1"], "stage1_"))

        custom_title = config.get("beat_title")
        if custom_title:
            # Use exact title if provided, no suffix
            safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in custom_title)
            name = safe_title
        else:
            name = f"{beat_name}_final"

        logger.info(f"Running on-demand export for {beat_name} -> {fmt}")
        _run_step(self.project_root, self.pipeline_dir, "step7_run_render_final.py", [
            "--grid_json", str(grid_json),
            "--event_grid_json", str(editor_events),
            "--sample_root", str(sample_root),
            "--out_dir", str(dirs["s7"]),
            "--name", name,
            "--format", fmt
        ])

        # Resolve output path
        # step7 produces: {name}.{fmt} OR {name}_{ver}.{fmt}
        # Use glob that matches both cases
        output_files = sorted(
            list(dirs["s7"].glob(f"{name}.{fmt}")) + list(dirs["s7"].glob(f"{name}_[0-9]*.{fmt}")),
            key=lambda p: p.stat().st_mtime
        )
        if not output_files:
            raise FileNotFoundError(f"Export failed: Output file for {fmt} not found in {dirs['s7']}")
        
        final_path = output_files[-1]
        
        # Update state
        self.state_manager.update_state(beat_name, {
            f"latest_{fmt}": str(final_path)
        })
        
        return final_path

    def run_pipeline(
        self,
        input_dir: Path,
        project_name: str = "beat_001", 
        bpm: float = 120.0,
        seed: int = 42,
        style: str = "rock",
        progressive: bool = True,
        repeat_full: int = 8,
    ) -> Dict:
        """
        Legacy ALL-IN-ONE generate.
        """
        beat_name = project_name
        self.state_manager.update_state(beat_name, {
            "uploads_dir": str(input_dir),
            "config": {
                "bpm": bpm,
                "seed": seed,
                "style": style,
                "progressive": progressive,
                "repeat_full": repeat_full
            }
        })
        return self.run_from_stage(beat_name, from_stage=1)
