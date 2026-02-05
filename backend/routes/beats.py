import os
import uuid
import json
from datetime import datetime
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file, current_app

beats_bp = Blueprint("beats", __name__)

# --- Helper accessors for services attached to app ---
def get_state_manager():
    return current_app.state_manager

def get_job_manager():
    return current_app.job_manager

def get_pipeline_service():
    return current_app.pipeline_service

def get_audio_service():
    return current_app.audio_service


@beats_bp.post("/api/beats")
def create_beat():
    """Creates a new beat (empty state)."""
    data = request.json or {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    beat_name = data.get("beat_name") or f"beat_{timestamp}"
    
    try:
        get_state_manager().update_state(beat_name, {"created_at": str(uuid.uuid1())})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
        
    return jsonify({"ok": True, "beat_name": beat_name})


@beats_bp.post("/api/beats/<beat_name>/upload")
def upload_files(beat_name: str):
    """Uploads files and updates state.json."""
    files = request.files.getlist("audio")
    if not files:
        return jsonify({"ok": False, "error": "No audio files"}), 400

    # Ensure upload directory exists
    # We need to know where OUTS directory is. 
    # StateManager knows via _get_project_dir, but it's internal.
    # We can reconstruct or expose it.
    # Expose get_project_dir or just assume standard path?
    # Better: let state manager handle path logic if possible, or use configured path.
    # StateManager has unique knowledge of project paths.
    # For now we use the one configured in app or state manager.
    
    # We'll use the one from config for consistency
    DEFAULT_OUTS_DIR = current_app.config["DEFAULT_OUTS_DIR"]
    upload_dir = DEFAULT_OUTS_DIR / beat_name / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        if not f.filename: continue
        suffix = Path(f.filename).suffix.lower()
        if suffix not in {".wav", ".mp3", ".m4a", ".webm"}:
            continue
        
        out_path = upload_dir / Path(f.filename).name
        f.save(out_path)
        saved.append(str(out_path))

    if not saved:
        return jsonify({"ok": False, "error": "No valid files saved"}), 400

    get_state_manager().update_state(beat_name, {"uploads_dir": str(upload_dir)})
    return jsonify({"ok": True, "count": len(saved)})


@beats_bp.delete("/api/beats/<beat_name>/files/<filename>")
def delete_file(beat_name: str, filename: str):
    DEFAULT_OUTS_DIR = current_app.config["DEFAULT_OUTS_DIR"]
    upload_dir = DEFAULT_OUTS_DIR / beat_name / "uploads"
    file_path = upload_dir / filename
    
    if file_path.exists() and file_path.is_file():
        try:
            file_path.unlink()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    else:
        return jsonify({"ok": False, "error": "File not found"}), 404


@beats_bp.post("/api/beats/<beat_name>/generate/initial")
def generate_initial(beat_name: str):
    """Runs the full pipeline (1-6) as a job. Stage 7 is on-demand."""
    data = request.json or {}
    config = {
        "bpm": float(data.get("bpm", 120.0)),
        "seed": int(data.get("seed", 42)),
        "style": str(data.get("style", "rock")),
        "progressive": bool(data.get("progressive", True)),
        "repeat_full": int(data.get("repeat_full", 2)),
        "beat_title": str(data.get("beat_title", "")),
    }
    
    get_state_manager().update_state(beat_name, {"config": config})
    
    pipeline = get_pipeline_service()
    job_id = get_job_manager().start_job(
        pipeline.run_from_stage,
        project_name=beat_name,
        from_stage=1,
        to_stage=6, # Stop at editor, wait for explicit export
        config_overrides=config
    )
    return jsonify({"ok": True, "job_id": job_id})


@beats_bp.get("/api/beats/<beat_name>/state")
def get_beat_state(beat_name: str):
    state = get_state_manager().get_state(beat_name)
    
    # Inject Grid Content
    grid_path = state.get("latest_grid_json")
    if grid_path and os.path.exists(grid_path):
        try:
            with open(grid_path, "r") as f:
                state["grid_content"] = json.load(f)
            
            # Use audio service logic or duplicate logic here?
            # Logic for event transformation is complex view-logic. Keep here for now.
            event_path = state.get("latest_event_grid_json") or state.get("latest_editor_json")
            if event_path and os.path.exists(event_path):
                 with open(event_path, "r") as f:
                    events_data = json.load(f)
                    raw_events = events_data if isinstance(events_data, list) else events_data.get("events", [])
                    
                    steps_per_bar = state["grid_content"].get("steps_per_bar", 16)
                    # Fix keys
                    if "bars" not in state["grid_content"] and "num_bars" in state["grid_content"]:
                        state["grid_content"]["bars"] = state["grid_content"]["num_bars"]
                    if "stepsPerBar" not in state["grid_content"]:
                        state["grid_content"]["stepsPerBar"] = steps_per_bar

                    transformed_events = []
                    for e in raw_events:
                        abs_step = (e["bar"] * steps_per_bar + e["step"]) if "bar" in e else e["step"]
                        vel = e.get("vel", e.get("velocity", 0.8))
                        final_vel = int(vel * 127) if isinstance(vel, float) and vel <= 1.0 else int(vel)
                        
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
                raw_pools = json.load(f)
                transformed_pools = {}
                for k, v in raw_pools.items():
                    if k.endswith("_POOL"):
                        role_name = k.replace("_POOL", "")
                        if isinstance(v, list):
                            transformed_pools[role_name] = [item.get("sample_id") for item in v if isinstance(item, dict)]
                
                state["pools_content"] = transformed_pools
        except Exception as e:
            print(f"Error reading pools: {e}")

    return jsonify({"ok": True, "state": state})


@beats_bp.patch("/api/beats/<beat_name>/config")
def update_config(beat_name: str):
    data = request.json or {}
    state = get_state_manager().get_state(beat_name)
    current_config = state.get("config", {})
    current_config.update(data)
    
    get_state_manager().update_state(beat_name, {"config": current_config})
    return jsonify({"ok": True, "config": current_config})


@beats_bp.post("/api/beats/<beat_name>/regenerate")
def regenerate(beat_name: str):
    data = request.json or {}
    from_stage = int(data.get("from_stage", 1))
    overrides = data.get("params", {}) 

    pipeline = get_pipeline_service()
    job_id = get_job_manager().start_job(
        pipeline.run_from_stage,
        project_name=beat_name,
        from_stage=from_stage,
        to_stage=6, # Also stop at 6 for regenerate by default? Or full? 
        # Usually regenerate implies you want to see/hear changes. 
        # Since 6 provides preview, 6 is enough.
        config_overrides=overrides
    )
    return jsonify({"ok": True, "job_id": job_id})


@beats_bp.get("/api/jobs/<job_id>")
def get_job_status(job_id: str):
    job = get_job_manager().get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job not found"}), 404
    return jsonify({"ok": True, "job": job})


@beats_bp.get("/api/beats/<beat_name>/latest")
def latest(beat_name: str):
    try:
        result = get_audio_service().get_latest_output(beat_name)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    return jsonify({"ok": True, "result": result})


@beats_bp.get("/api/beats/<beat_name>/download")
def download(beat_name: str):
    kind = (request.args.get("kind") or "mp3").lower().strip()
    if kind not in {"mp3", "wav", "flac", "ogg", "m4a"}:
        return jsonify({"ok": False, "error": "Supported formats: mp3, wav, flac, ogg, m4a"}), 400

    file_path = None
    try:
        # First try finding existing
        file_path = get_audio_service().convert_output(beat_name, kind)
    except FileNotFoundError:
        # Not found, try generating on demand
        try:
            print(f"[download] triggering on-demand export for {kind}...")
            file_path = get_pipeline_service().run_export(beat_name, kind)
        except Exception as e:
             return jsonify({"ok": False, "error": f"Export generation failed: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 404

    if not file_path or not file_path.exists():
         return jsonify({"ok": False, "error": "File not found after export"}), 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=file_path.name,
        mimetype=f"audio/{kind}" if kind != "m4a" else "audio/mp4",
    )


@beats_bp.get("/api/beats/<beat_name>/samples/<filename>")
def get_sample(beat_name: str, filename: str):
    if ".." in filename or filename.startswith("/"):
         return jsonify({"ok": False, "error": "Invalid filename"}), 400
         
    try:
        target_path = get_audio_service().get_sample_path(beat_name, filename)
        return send_file(target_path, max_age=0)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 404
