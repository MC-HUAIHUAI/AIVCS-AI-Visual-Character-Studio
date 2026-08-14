"""PyInstaller entrypoint for the AIVCS backend (Phase 3-5C).

Runs the FastAPI app with uvicorn on 127.0.0.1:8321. No reload (release).
"""
import os
import sys

import uvicorn

# Make the repo root importable so `backend.app.main` resolves.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Import the app statically so PyInstaller bundles the whole backend package.
from backend.app.main import app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8321, reload=False, log_level="warning")
