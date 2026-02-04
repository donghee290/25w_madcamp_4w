from pathlib import Path
from flask import Blueprint, jsonify, request, current_app

legacy_bp = Blueprint("legacy", __name__)

def get_pipeline_service():
    return current_app.pipeline_service

@legacy_bp.post("/api/generate")
def generate_legacy():
    """
    Legacy ALL-IN-ONE generate.
    Blocks until finished (SYNCHRONOUS for backward compat).
    """
    beat_name = (request.form.get("beat_name") or request.form.get("project_name") or "beat_001").strip()
    bpm = float(request.form.get("bpm") or 120.0)
    seed = int(request.form.get("seed") or 42)
    style = (request.form.get("style") or "rock").strip()

    files = request.files.getlist("audio")
    if not files:
        return jsonify({"ok": False, "error": "No audio files. Use form-data key: audio"}), 400

    DEFAULT_OUTS_DIR = current_app.config["DEFAULT_OUTS_DIR"]
    input_dir = DEFAULT_OUTS_DIR / beat_name / "uploads"
    input_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        if not f.filename: continue
        suffix = Path(f.filename).suffix.lower()
        if suffix not in {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".webm"}:
            return jsonify({"ok": False, "error": f"Unsupported extension: {suffix}"}), 400
        
        out_path = input_dir / Path(f.filename).name
        f.save(out_path)
        saved.append(str(out_path))

    if not saved:
        return jsonify({"ok": False, "error": "No valid files saved."}), 400

    try:
        result = get_pipeline_service().run_pipeline(
            input_dir=input_dir,
            project_name=beat_name,
            bpm=bpm,
            seed=seed,
            style=style,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True, "result": result})
