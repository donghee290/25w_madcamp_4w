# backend/app.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

from backend.model_loader import SoundRoutineModel


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": "*"}})

    # ---- Paths (프로젝트 루트 기준)
    PROJECT_ROOT = Path(__file__).resolve().parents[1]  # .../soundroutine
    DEFAULT_OUTS_DIR = PROJECT_ROOT / "outs"

    # ---- Singleton model/pipeline runner
    app.model = SoundRoutineModel(project_root=PROJECT_ROOT)  # type: ignore[attr-defined]

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    @app.post("/api/generate")
    def generate():
        """
        multipart/form-data
        - files: audio (여러 개 가능)
        - project_name: str (optional)
        - bpm: float (optional)
        - seed: int (optional)
        - style: str (optional)  # rock/house/hiphop 등 (현재 pipeline에서 지원하는 값)
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
            if not f.filename:
                continue
            # 간단한 확장자 체크(선택)
            suffix = Path(f.filename).suffix.lower()
            if suffix not in {".wav", ".mp3", ".flac", ".ogg", ".m4a"}:
                return jsonify({"ok": False, "error": f"Unsupported extension: {suffix}"}), 400

            out_path = input_dir / Path(f.filename).name
            f.save(out_path)
            saved.append(str(out_path))

        if not saved:
            return jsonify({"ok": False, "error": "No valid files saved."}), 400

        # ---- run pipeline
        try:
            result = app.model.run_pipeline(  # type: ignore[attr-defined]
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
        """
        가장 최근 생성된 최종 mp3 경로와 메타를 반환
        """
        try:
            result = app.model.get_latest_output(project_name)  # type: ignore[attr-defined]
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 404
        return jsonify({"ok": True, "result": result})

    @app.get("/api/projects/<project_name>/download")
    def download(project_name: str):
        """
        query:
        - kind=mp3|wav (default mp3)
        """
        kind = (request.args.get("kind") or "mp3").lower().strip()
        if kind not in {"mp3", "wav"}:
            return jsonify({"ok": False, "error": "kind must be mp3 or wav"}), 400

        try:
            info = app.model.get_latest_output(project_name)  # type: ignore[attr-defined]
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 404

        file_path = Path(info["mp3_path"] if kind == "mp3" else info["wav_path"])
        if not file_path.exists():
            return jsonify({"ok": False, "error": f"File not found: {file_path}"}), 404

        return send_file(
            file_path,
            as_attachment=True,
            download_name=file_path.name,
            mimetype="audio/mpeg" if kind == "mp3" else "audio/wav",
        )

    return app


if __name__ == "__main__":
    # 기본: FLASK_RUN_PORT 없으면 5000
    port = int(os.environ.get("PORT", "5000"))
    app = create_app()
    app.run(host="0.0.0.0", port=port, debug=True)