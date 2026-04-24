"""FastAPI entry point for the VPC-SC multi-agent on Cloud Run."""

import os

import uvicorn
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri=os.environ.get("SESSION_DB_URI", "sqlite+aiosqlite:///./sessions.db"),
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "http://localhost:8080,http://localhost:8000").split(","),
    web=os.environ.get("SERVE_WEB_UI", "true").lower() == "true",
)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
    )
