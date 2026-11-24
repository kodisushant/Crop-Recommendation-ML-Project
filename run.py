"""Crop Advisor - Top-level FastAPI application entrypoint."""
import os
import uvicorn
from src.crop_advisor.main import app

if __name__ == "__main__":
    uvicorn.run("src.crop_advisor.main:app", host="127.0.0.1", port=int(os.getenv("PORT", 8000)))
