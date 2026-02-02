import sys
from pathlib import Path

# Add project root to sys.path to allow importing stage modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app import create_app
from backend.config import Config

app = create_app(Config)

if __name__ == '__main__':
    print(f"Starting server on {Config.HOST}:{Config.PORT}...")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
