from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request
from werkzeug.utils import secure_filename

from .config import AppConfig, load_config
from .db.models import JobRecord
from .db.repository import build_repository
from .services.beat_gen import generate_basic_beat


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parse_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _parse_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def create_app(config: Optional[AppConfig] = None) -> Flask:
    cfg = config or load_config()
    repo = build_repository(
        cfg.db_backend,
        mongo_uri=cfg.mongo_uri,
        mongo_db=cfg.mongo_db,
        mongo_collection=cfg.mongo_collection,
    )

    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health() -> Any:
        return jsonify({"status": "ok"})

    @app.route("/v1/beat", methods=["POST"])
    def create_beat() -> Any:
        job_id = uuid.uuid4().hex
        job_dir = _ensure_dir(cfg.data_root / "jobs" / job_id)
        uploads_dir = _ensure_dir(job_dir / "uploads")
        outputs_dir = _ensure_dir(job_dir / "outputs")

        content_type = request.content_type or ""
        payload: Dict[str, Any] = {}
        uploaded_files: List[Path] = []

        if content_type.startswith("multipart/form-data"):
            payload.update(request.form.to_dict())
            for f in request.files.getlist("files"):
                if not f:
                    continue
                filename = secure_filename(f.filename or f"upload_{uuid.uuid4().hex}.wav")
                save_path = uploads_dir / filename
                f.save(str(save_path))
                uploaded_files.append(save_path)
        else:
            payload = request.get_json(silent=True)
            if payload is None:
                try:
                    payload = json.loads(request.data.decode("utf-8"))
                except Exception:
                    payload = {}

        bpm = _parse_float(payload.get("bpm"), 120.0)
        bars = _parse_int(payload.get("bars"), 4)
        seed = _parse_int(payload.get("seed"), 42)
        motion_mode = str(payload.get("motion_mode", "B"))
        motion_keep = _parse_int(payload.get("motion_keep"), 6)
        fill_prob = _parse_float(payload.get("fill_prob"), 0.25)
        texture_enabled = _parse_bool(payload.get("texture", True), True)

        limit = _parse_int(payload.get("limit"), cfg.default_limit)

        pools_json_input = payload.get("pools_json")
        input_dir = payload.get("input_dir")

        record = JobRecord(
            job_id=job_id,
            status="running",
            created_at=_utc_now(),
            input_meta={
                "bpm": bpm,
                "bars": bars,
                "seed": seed,
                "motion_mode": motion_mode,
                "motion_keep": motion_keep,
                "fill_prob": fill_prob,
                "texture_enabled": texture_enabled,
                "limit": limit,
                "input_dir": input_dir,
                "uploads": [str(p) for p in uploaded_files],
            },
        )
        repo.save(record)

        try:
            if pools_json_input:
                if isinstance(pools_json_input, dict):
                    pools_json = pools_json_input
                else:
                    pools_path = Path(str(pools_json_input))
                    pools_json = json.loads(pools_path.read_text(encoding="utf-8"))
                debug_list: List[Dict[str, Any]] = []
            else:
                # Ensure HF cache directories are writable (avoid invalid default paths)
                _ensure_dir(cfg.data_root)
                default_hf_home = cfg.data_root / "hf"
                default_tf_cache = default_hf_home / "transformers"
                hf_home_env = os.getenv("HF_HOME")
                tf_cache_env = os.getenv("TRANSFORMERS_CACHE")
                if not hf_home_env or not Path(hf_home_env).exists():
                    os.environ["HF_HOME"] = str(default_hf_home)
                if not tf_cache_env or not Path(tf_cache_env).exists():
                    os.environ["TRANSFORMERS_CACHE"] = str(default_tf_cache)
                _ensure_dir(Path(os.environ["HF_HOME"]))
                _ensure_dir(Path(os.environ["TRANSFORMERS_CACHE"]))

                if input_dir:
                    src_dir = Path(str(input_dir))
                else:
                    src_dir = uploads_dir
                from .services.role_assign import assign_roles
                pools_json, debug_list = assign_roles(
                    input_dir=src_dir,
                    config_path=cfg.role_config_path,
                    prompts_path=cfg.prompts_path,
                    limit=limit,
                    seed=seed,
                )

            grid_json, events_json, chosen = generate_basic_beat(
                pools_json=pools_json,
                bpm=bpm,
                bars=bars,
                seed=seed,
                motion_mode=motion_mode,
                motion_keep=motion_keep,
                fill_prob=fill_prob,
                texture_enabled=texture_enabled,
            )

            (outputs_dir / "grid.json").write_text(
                json.dumps(grid_json, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (outputs_dir / "events.json").write_text(
                json.dumps(events_json, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (outputs_dir / "pools.json").write_text(
                json.dumps(pools_json, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if debug_list:
                (outputs_dir / "debug.json").write_text(
                    json.dumps(debug_list, ensure_ascii=False, indent=2), encoding="utf-8"
                )

            record.status = "done"
            record.output_meta = {
                "grid_json": grid_json,
                "events_json": events_json,
                "chosen_samples": chosen,
                "paths": {
                    "grid": str(outputs_dir / "grid.json"),
                    "events": str(outputs_dir / "events.json"),
                    "pools": str(outputs_dir / "pools.json"),
                },
            }
            repo.save(record)

            return jsonify(
                {
                    "job_id": job_id,
                    "grid_json": grid_json,
                    "events_json": events_json,
                    "chosen_samples": chosen,
                }
            )
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
            repo.save(record)
            return jsonify({"error": str(exc), "job_id": job_id}), 400

    @app.route("/v1/beat/<job_id>", methods=["GET"])
    def get_beat(job_id: str) -> Any:
        record = repo.get(job_id)
        if not record:
            return jsonify({"error": "job not found"}), 404
        return jsonify(
            {
                "job_id": record.job_id,
                "status": record.status,
                "created_at": record.created_at,
                "input": record.input_meta,
                "output": record.output_meta,
                "error": record.error,
            }
        )

    return app
