"""Run from repository root: uvicorn backend.app.server:app --port 8000."""
from pathlib import Path
from dotenv import load_dotenv
from .main import create_app

load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
app = create_app()
