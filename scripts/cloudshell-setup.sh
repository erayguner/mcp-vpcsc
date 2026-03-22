#!/usr/bin/env bash
# VPC-SC MCP Server — Cloud Shell setup script
#
# Run this in Google Cloud Shell to set up the MCP server
# and connect it to Gemini CLI for interactive use.
#
# Usage:
#   git clone <your-repo> && cd vpcsc-mcp
#   bash scripts/cloudshell-setup.sh
#
# Prerequisites: Cloud Shell has gcloud, Python 3.10+, and npm pre-installed.

set -euo pipefail

echo "========================================"
echo "  VPC-SC MCP Server — Cloud Shell Setup"
echo "========================================"
echo ""

# ── Check prerequisites ──────────────────────────────────────────────────────
echo "[1/6] Checking prerequisites..."
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found"; exit 1; }
command -v gcloud >/dev/null 2>&1 || { echo "ERROR: gcloud not found"; exit 1; }
command -v pip3 >/dev/null 2>&1 || { echo "ERROR: pip3 not found"; exit 1; }

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  Python: $PYTHON_VERSION"
echo "  gcloud: $(gcloud version 2>/dev/null | head -1)"

PROJECT=$(gcloud config get-value project 2>/dev/null)
ACCOUNT=$(gcloud config get-value account 2>/dev/null)
echo "  Project: ${PROJECT:-NOT SET}"
echo "  Account: ${ACCOUNT:-NOT SET}"

if [ -z "$PROJECT" ]; then
    echo ""
    echo "ERROR: No GCP project set. Run:"
    echo "  gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

# ── Install the MCP server ───────────────────────────────────────────────────
echo ""
echo "[2/6] Installing VPC-SC MCP server..."
pip3 install --quiet -e ".[dev]"
echo "  Installed vpcsc-mcp"

# ── Verify MCP server works ──────────────────────────────────────────────────
echo ""
echo "[3/6] Verifying MCP server..."
TOOLS=$(python3 -c "
from vpcsc_mcp.server import mcp; import asyncio
async def c():
    t=await mcp.list_tools()
    print(len(t))
asyncio.run(c())
" 2>/dev/null)
echo "  MCP server: ${TOOLS} tools registered"

# ── Install Gemini CLI ───────────────────────────────────────────────────────
echo ""
echo "[4/6] Installing Gemini CLI..."
if ! command -v gemini >/dev/null 2>&1; then
    npm install -g @anthropic-ai/gemini-cli 2>/dev/null || npm install -g @google/gemini-cli 2>/dev/null || {
        echo "  Gemini CLI not available via npm. Using ADK instead."
        pip3 install --quiet "google-adk>=1.27.0" "python-dotenv>=1.0.0"
        echo "  Installed Google ADK"
    }
fi

# ── Configure MCP server for Gemini/ADK ──────────────────────────────────────
echo ""
echo "[5/6] Configuring MCP connection..."

# Create .env for ADK if needed
if [ ! -f examples/adk-agent/.env ]; then
    cat > examples/adk-agent/.env <<EOF
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=${PROJECT}
GOOGLE_CLOUD_LOCATION=europe-west2
VPCSC_MCP_MODE=local
EOF
    echo "  Created examples/adk-agent/.env (Vertex AI mode)"
fi

# Create Gemini CLI config if gemini is available
GEMINI_CONFIG_DIR="$HOME/.gemini"
if command -v gemini >/dev/null 2>&1; then
    mkdir -p "$GEMINI_CONFIG_DIR"
    cat > "$GEMINI_CONFIG_DIR/settings.json" <<EOF
{
  "mcpServers": {
    "vpcsc-mcp": {
      "command": "python3",
      "args": ["-m", "vpcsc_mcp.server"],
      "env": {
        "VPCSC_MCP_TRANSPORT": "stdio"
      }
    }
  }
}
EOF
    echo "  Created Gemini CLI MCP config at $GEMINI_CONFIG_DIR/settings.json"
fi

# ── Print usage instructions ─────────────────────────────────────────────────
echo ""
echo "[6/6] Setup complete!"
echo ""
echo "========================================"
echo "  HOW TO USE"
echo "========================================"
echo ""

if command -v gemini >/dev/null 2>&1; then
    echo "Option 1 — Gemini CLI (recommended):"
    echo "  gemini"
    echo "  > Run a diagnostic on my project"
    echo ""
fi

echo "Option 2 — ADK Web UI:"
echo "  cd examples/adk-agent"
echo "  adk web --port 8080"
echo "  # Then click 'Web Preview' in Cloud Shell toolbar"
echo ""
echo "Option 3 — ADK Terminal:"
echo "  cd examples/adk-agent"
echo "  adk run vpcsc_agent"
echo ""
echo "Option 4 — Programmatic:"
echo "  python3 examples/adk-agent/run_agent.py 'Run a diagnostic on my project'"
echo ""
echo "Option 5 — Direct MCP tools (no LLM):"
echo "  python3 scripts/run-diagnostic.py"
echo "  python3 scripts/run-diagnostic.py --org-policies"
echo "  python3 scripts/run-diagnostic.py --implementation-guide"
echo ""
echo "========================================"
