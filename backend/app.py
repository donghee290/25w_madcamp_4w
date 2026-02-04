# backend/app.py
from __future__ import annotations

import os
import uuid
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

from model_loader import SoundRoutineModel


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": "*"}})

    # ---- Paths (Project Root)
    PROJECT_ROOT = Path(__file__).resolve().parents[1]  # .../soundroutine
    DEFAULT_OUTS_DIR = PROJECT_ROOT / "outs"

    # ---- Singleton model/pipeline runner
    # FIX: Pass project_root
    app.model = SoundRoutineModel(project_root=PROJECT_ROOT)  # type: ignore[attr-defined]

    @app.get("/api/health")
    def health():
        """
        Server status check.
        Can be used to verify if Model logic is attached.
        """
        model_connected = hasattr(app, "model") and app.model is not None
        return jsonify({
            "ok": True, 
            "model_connected": model_connected
        })

    # ===============================================================
    # NEW API ENDPOINTS (Project-based & Step-by-step)
    # ===============================================================

    @app.post("/api/projects")
    def create_project():
        """Creates a new project (empty state)."""
        data = request.json or {}
        # Use timestamp for easy identification during testing
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = data.get("project_name") or f"project_{timestamp}"
        
        # Init state
        try:
            app.model.update_state(project_name, {"created_at": str(uuid.uuid1())}) # type: ignore
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
            
        return jsonify({"ok": True, "project_name": project_name})

    @app.post("/api/projects/<project_name>/upload")
    def upload_files(project_name: str):
        """Uploads files and updates state.json."""
        files = request.files.getlist("audio")
        if not files:
            return jsonify({"ok": False, "error": "No audio files"}), 400

        upload_dir = DEFAULT_OUTS_DIR / project_name / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        saved = []
        for f in files:
            if not f.filename: continue
            suffix = Path(f.filename).suffix.lower()
            if suffix not in {".wav", ".mp3", ".flac", ".ogg", ".m4a"}:
                continue
            
            out_path = upload_dir / Path(f.filename).name
            f.save(out_path)
            saved.append(str(out_path))

        if not saved:
            return jsonify({"ok": False, "error": "No valid files saved"}), 400

        # Update state with uploads_dir
        app.model.update_state(project_name, {"uploads_dir": str(upload_dir)}) # type: ignore
        return jsonify({"ok": True, "count": len(saved)})

    @app.post("/api/projects/<project_name>/generate/initial")
    def generate_initial(project_name: str):
        """Runs the full pipeline (1-7) as a job."""
        data = request.json or {}
        # Allows optional config overrides
        config = {
            "bpm": float(data.get("bpm", 120.0)),
            "seed": int(data.get("seed", 42)),
            "style": str(data.get("style", "rock")),
            "progressive": bool(data.get("progressive", True)),
            "repeat_full": int(data.get("repeat_full", 8)),
        }
        
        # Save config first
        app.model.update_state(project_name, {"config": config}) # type: ignore
        
        # Start job (runs full pipeline from stage 1)
        job_id = app.model.start_job( # type: ignore
            app.model.run_from_stage, # type: ignore
            project_name=project_name,
            from_stage=1,
            config_overrides=config
        )
        return jsonify({"ok": True, "job_id": job_id})

    @app.get("/api/projects/<project_name>/state")
    def get_project_state(project_name: str):
        """Returns the current state.json content, plus active grid/pool data."""
        state = app.model.get_state(project_name) # type: ignore
        
        # Inject Grid Content if path exists
        grid_path = state.get("latest_grid_json")
        if grid_path and os.path.exists(grid_path):
            try:
                with open(grid_path, "r") as f:
                    state["grid_content"] = json.load(f)
                
                # FIX: Also load event_grid if available and merge into grid_content
                # The frontend expects 'events' inside grid object.
                event_path = state.get("latest_event_grid_json") or state.get("latest_editor_json")
                if event_path and os.path.exists(event_path):
                     with open(event_path, "r") as f:
                        events_data = json.load(f)
                        raw_events = []
                        if isinstance(events_data, list):
                            raw_events = events_data
                        elif isinstance(events_data, dict) and "events" in events_data:
                            raw_events = events_data["events"]
                        
                        # --- FIX: Transform events for Frontend (BeatCanvas) ---
                        # Frontend expects: { step: absolute, velocity: 0-127, role: ... }
                        # Backend typically has: { bar: 0, step: 0-15, vel: 0.0-1.0 }
                        steps_per_bar = state["grid_content"].get("steps_per_bar", 16)
                        
                        # Fix: Ensure frontend keys exist
                        if "bars" not in state["grid_content"] and "num_bars" in state["grid_content"]:
                            state["grid_content"]["bars"] = state["grid_content"]["num_bars"]
                        if "stepsPerBar" not in state["grid_content"]:
                            state["grid_content"]["stepsPerBar"] = steps_per_bar

                        transformed_events = []
                        for e in raw_events:
                            # 1. Calc absolute step
                            # If 'bar' is present, use it. If not, assume 'step' is already absolute?
                            # Usually backend 'event_grid' has bar/step.
                            if "bar" in e:
                                abs_step = e["bar"] * steps_per_bar + e["step"]
                            else:
                                abs_step = e["step"]

                            # 2. Velocity scaling
                            # Backend 'vel' is 0.0-1.0 usually
                            vel = e.get("vel", e.get("velocity", 0.8))
                            if isinstance(vel, float) and vel <= 1.0:
                                final_vel = int(vel * 127)
                            else:
                                final_vel = int(vel)
                            
                            # 3. Construct new event
                            new_e = {
                                "step": abs_step,
                                "role": e["role"],
                                "velocity": final_vel,
                                "duration": e.get("dur_steps", e.get("duration", 1)),
                                "sampleId": e.get("sample_id"),
                                "offset": e.get("micro_offset_ms", 0)
                            }
                            transformed_events.append(new_e)

                        state["grid_content"]["events"] = transformed_events
                            
            except Exception as e:
                print(f"Error reading grid: {e}")

        # Inject Pools Content
        pools_path = state.get("latest_pools_json")
        if pools_path and os.path.exists(pools_path):
            try:
                with open(pools_path, "r") as f:
                    state["pools_content"] = json.load(f)
            except Exception as e:
                print(f"Error reading pools: {e}")

        return jsonify({"ok": True, "state": state})

    @app.patch("/api/projects/<project_name>/config")
    def update_config(project_name: str):
        """Updates configuration in state.json."""
        data = request.json or {}
        # We assume data contains keys like bpm, style, etc.
        # Check current state first
        state = app.model.get_state(project_name) # type: ignore
        current_config = state.get("config", {})
        current_config.update(data)
        
        app.model.update_state(project_name, {"config": current_config}) # type: ignore
        return jsonify({"ok": True, "config": current_config})

    @app.post("/api/projects/<project_name>/regenerate")
    def regenerate(project_name: str):
        """
        Partial re-execution loop.
        body: { "from_stage": 3, "overrides": {...} }
        """
        data = request.json or {}
        from_stage = int(data.get("from_stage", 1))
        overrides = data.get("params", {}) # param overrides

        # Start job
        job_id = app.model.start_job( # type: ignore
            app.model.run_from_stage, # type: ignore
            project_name=project_name,
            from_stage=from_stage,
            config_overrides=overrides
        )
        return jsonify({"ok": True, "job_id": job_id})

    @app.get("/api/jobs/<job_id>")
    def get_job_status(job_id: str):
        job = app.model.get_job(job_id) # type: ignore
        if not job:
            return jsonify({"ok": False, "error": "Job not found"}), 404
        return jsonify({"ok": True, "job": job})

    # ===============================================================
    # LEGACY / COMPATIBILITY (Wraps new logic)
    # ===============================================================

    @app.post("/api/generate")
    def generate_legacy():
        """
        Legacy ALL-IN-ONE generate.
        Blocks until finished (SYNCHRONOUS for backward compat).
        """
        # ---- params
        project_name = (request.form.get("project_name") or "project_001").strip()
        bpm = float(request.form.get("bpm") or 120.0)
        seed = int(request.form.get("seed") or 42)
        style = (request.form.get("style") or "rock").strip()

        # ---- files
        files = request.files.getlist("audio")
        if not files:
            return jsonify({"ok": False, "error": "No audio files. Use form-data key: audio"}), 400

        # ---- write input_dir
        input_dir = DEFAULT_OUTS_DIR / project_name / "uploads"
        input_dir.mkdir(parents=True, exist_ok=True)

        saved = []
        for f in files:
            if not f.filename: continue
            suffix = Path(f.filename).suffix.lower()
            if suffix not in {".wav", ".mp3", ".flac", ".ogg", ".m4a"}:
                return jsonify({"ok": False, "error": f"Unsupported extension: {suffix}"}), 400
            
            out_path = input_dir / Path(f.filename).name
            f.save(out_path)
            saved.append(str(out_path))

        if not saved:
            return jsonify({"ok": False, "error": "No valid files saved."}), 400

        # ---- run pipeline (Blocking)
        try:
            # We call run_pipeline which is now a wrapper around run_from_stage(1)
            # This calls run_from_stage SYNCHRONOUSLY inside model_loader if we use the old RunPipeline method?
            # actually app.model.run_pipeline in my new code calls run_from_stage directly 
            # and returns the dict result. It does NOT spawn a thread.
            
            result = app.model.run_pipeline( # type: ignore
                input_dir=input_dir,
                project_name=project_name,
                bpm=bpm,
                seed=seed,
                style=style,
            )
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

        return jsonify({"ok": True, "result": result})

    @app.get("/api/projects/<project_name>/latest")
    def latest(project_name: str):
        try:
            result = app.model.get_latest_output(project_name)  # type: ignore[attr-defined]
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 404
        return jsonify({"ok": True, "result": result})

    @app.get("/api/projects/<project_name>/download")
    def download(project_name: str):
        kind = (request.args.get("kind") or "mp3").lower().strip()
        # Allow common audio formats
        if kind not in {"mp3", "wav", "flac", "ogg", "m4a"}:
            return jsonify({"ok": False, "error": "Supported formats: mp3, wav, flac, ogg, m4a"}), 400

        try:
            # On-demand conversion
            file_path = app.model.convert_output(project_name, kind) # type: ignore
            print(f"[DEBUG] Serving {file_path} for {project_name} ({kind})")
        except Exception as e:
            print(f"[DEBUG] Download error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 404

        return send_file(
            file_path,
            as_attachment=True,
            download_name=file_path.name,
            mimetype=f"audio/{kind}" if kind != "m4a" else "audio/mp4",
        )

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app = create_app()
    app.run(host="0.0.0.0", port=port, debug=True)