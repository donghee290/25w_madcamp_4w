from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class AppConfig:
    repo_root: Path
    data_root: Path
    role_config_path: Path
    prompts_path: Path
    default_limit: int
    log_level: str
    db_backend: str
    mongo_uri: str
    mongo_db: str
    mongo_collection: str


def load_config() -> AppConfig:
    repo_root = Path(__file__).resolve().parents[1]

    data_root = Path(os.getenv("SOUNDROUTINE_DATA_ROOT", str(repo_root / "data")))
    role_config_path = Path(
        os.getenv(
            "SOUNDROUTINE_ROLE_CONFIG",
            str(repo_root / "stage2_role_assignment" / "configs" / "role_assignment.yaml"),
        )
    )
    prompts_path = Path(
        os.getenv(
            "SOUNDROUTINE_PROMPTS",
            str(repo_root / "stage2_role_assignment" / "prompts" / "prompts.yaml"),
        )
    )

    default_limit = int(os.getenv("SOUNDROUTINE_DEFAULT_LIMIT", "0"))
    log_level = os.getenv("SOUNDROUTINE_LOG_LEVEL", "INFO")
    db_backend = os.getenv("SOUNDROUTINE_DB_BACKEND", "memory")
    mongo_uri = os.getenv("SOUNDROUTINE_MONGO_URI", "mongodb://localhost:27017")
    mongo_db = os.getenv("SOUNDROUTINE_MONGO_DB", "soundroutine")
    mongo_collection = os.getenv("SOUNDROUTINE_MONGO_COLLECTION", "jobs")

    return AppConfig(
        repo_root=repo_root,
        data_root=data_root,
        role_config_path=role_config_path,
        prompts_path=prompts_path,
        default_limit=default_limit,
        log_level=log_level,
        db_backend=db_backend,
        mongo_uri=mongo_uri,
        mongo_db=mongo_db,
        mongo_collection=mongo_collection,
    )
