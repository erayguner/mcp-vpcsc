"""FastAPI entry point for deploying the VPC-SC ADK agent to Cloud Run.

This wraps the ADK agent in a FastAPI server with:
  - Session persistence via SQLite (survives container restarts with a volume)
  - Web UI for interactive testing (optional, set SERVE_WEB_UI=false to disable)
  - REST API for programmatic access

Deploy:
  adk deploy cloud_run --project=$PROJECT --region=$REGION --with_ui ./vpcsc_agent
  # OR manually:
  gcloud run deploy vpcsc-adk-agent --source . --region=europe-west2 --no-allow-unauthenticated
"""

import os

import uvicorn
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri=os.environ.get(
        "SESSION_DB_URI", "sqlite+aiosqlite:///./sessions.db"
    ),
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "http://localhost:8080,http://localhost:8000").split(","),
    web=os.environ.get("SERVE_WEB_UI", "true").lower() == "true",
)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
    )
