"""Entry point for running the slot service: uv run uvicorn service.main:app --port 8000"""

import os

from dotenv import load_dotenv

from service.app import create_app

load_dotenv()

app = create_app(os.getenv("BANK_DB_PATH", "data/bank.db"))
