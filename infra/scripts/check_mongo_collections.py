#!/usr/bin/env python3
import os
from pathlib import Path
from typing import Dict, Optional


def load_env(env_path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def getenv(key: str, fallback: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> Optional[str]:
    if key in os.environ:
        return os.environ[key]
    if env and key in env:
        return env[key]
    return fallback


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    env_values = load_env(repo_root / ".env")

    mongo_uri = getenv("SOUNDROUTINE_MONGO_URI", getenv("MONGO_URI", None, env_values), env_values)
    mongo_db = getenv("SOUNDROUTINE_MONGO_DB", getenv("MONGO_DB", "soundroutine", env_values), env_values)

    if not mongo_uri:
        print("Missing MongoDB URI. Set SOUNDROUTINE_MONGO_URI or MONGO_URI.")
        return 1

    try:
        import certifi  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        certifi = None  # type: ignore

    try:
        from pymongo import MongoClient  # type: ignore
    except Exception as exc:
        print(f"pymongo import failed: {exc}")
        return 1

    client_kwargs = {"serverSelectionTimeoutMS": 5000}
    if certifi is not None:
        client_kwargs["tlsCAFile"] = certifi.where()

    client = MongoClient(mongo_uri, **client_kwargs)

    try:
        client.admin.command("ping")
    except Exception as exc:
        print(f"MongoDB connection failed: {exc}")
        return 1

    db = client[mongo_db]
    collections = sorted(db.list_collection_names())

    print(f"DB: {mongo_db}")
    print(f"Collections: {', '.join(collections) if collections else '(none)'}")

    def print_count(name: str) -> None:
        if name not in collections:
            print(f"- {name}: (missing)")
            return
        count = db[name].count_documents({})
        print(f"- {name}: {count}")

    print_count("users")
    print_count("refresh_tokens")
    print_count("active_sessions")
    print_count("tokens")

    def preview_users() -> None:
        if "users" not in collections:
            return
        print("\nUsers (latest 3):")
        cursor = (
            db["users"]
            .find({}, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "created_at": 1, "last_login": 1})
            .sort("created_at", -1)
            .limit(3)
        )
        for doc in cursor:
            print(f"- {doc}")

    def preview_refresh_tokens() -> None:
        if "refresh_tokens" not in collections:
            return
        print("\nRefresh tokens (latest 3):")
        cursor = (
            db["refresh_tokens"]
            .find(
                {},
                {
                    "_id": 0,
                    "token_id": 1,
                    "user_id": 1,
                    "is_revoked": 1,
                    "expires_at": 1,
                    "created_at": 1,
                    "last_used_at": 1,
                    "ip_address": 1,
                    "device_info": 1,
                },
            )
            .sort("created_at", -1)
            .limit(3)
        )
        for doc in cursor:
            print(f"- {doc}")

    def preview_sessions() -> None:
        if "active_sessions" not in collections:
            return
        print("\nActive sessions (latest 3):")
        cursor = (
            db["active_sessions"]
            .find(
                {},
                {
                    "_id": 0,
                    "session_id": 1,
                    "user_id": 1,
                    "is_active": 1,
                    "created_at": 1,
                    "last_activity": 1,
                    "ip_address": 1,
                    "device_info": 1,
                },
            )
            .sort("created_at", -1)
            .limit(3)
        )
        for doc in cursor:
            print(f"- {doc}")

    preview_users()
    preview_refresh_tokens()
    preview_sessions()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
