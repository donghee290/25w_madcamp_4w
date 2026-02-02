import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

class Config:
    BASE_DIR = Path(__file__).resolve().parent.parent
    PROJECT_ROOT = BASE_DIR

    # Stage Directories
    STAGE1_DIR = PROJECT_ROOT / "stage1_drumgenx"
    STAGE2_DIR = PROJECT_ROOT / "stage2_role_assignment"
    STAGE3_DIR = PROJECT_ROOT / "stage3_beat_grid"
    STAGE4_DIR = PROJECT_ROOT / "stage4_model_gen"

    # Upload & Output
    UPLOAD_FOLDER = BASE_DIR / "uploads"
    OUTPUT_FOLDER = BASE_DIR / "output"

    # Server Settings
    HOST = "0.0.0.0"
    PORT = 5000
    DEBUG = True

    # MongoDB
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB = os.getenv("MONGO_DB", "soundroutine")

    @staticmethod
    def init_app(app):
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.OUTPUT_FOLDER, exist_ok=True)
