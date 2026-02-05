# backend/app.py
from __future__ import annotations

import os
from pathlib import Path
from flask import Flask
from flask_cors import CORS

from services.job_manager import JobManager
from services.state_manager import StateManager
from services.pipeline_service import PipelineService
from services.audio_service import AudioService

from routes.health import health_bp
from routes.beats import beats_bp
from routes.legacy import legacy_bp


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": "*"}})

    # ---- Paths (Project Root)
    PROJECT_ROOT = Path(__file__).resolve().parents[1]  # .../soundroutine
    
    # Store config
    app.config["PROJECT_ROOT"] = PROJECT_ROOT
    DEFAULT_OUTS_DIR = PROJECT_ROOT / "outs"
    app.config["DEFAULT_OUTS_DIR"] = DEFAULT_OUTS_DIR
    
    # Also set UPLOAD_FOLDER for compatibility with existing services if needed
    app.config["UPLOAD_FOLDER"] = str(DEFAULT_OUTS_DIR / "uploads") # Or wherever default is

    # ---- Initialize Services
    # We attach them to 'app' instance so blueprints can access them via current_app
    app.job_manager = JobManager()
    app.state_manager = StateManager(outs_root=DEFAULT_OUTS_DIR)
    app.pipeline_service = PipelineService(
        project_root=PROJECT_ROOT, 
        state_manager=app.state_manager, 
        job_manager=app.job_manager
    )
    app.audio_service = AudioService(
        outs_root=DEFAULT_OUTS_DIR,
        state_manager=app.state_manager
    )

    # ---- Register Blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(beats_bp)
    app.register_blueprint(legacy_bp)

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app = create_app()
    app.run(host="0.0.0.0", port=port, debug=True)