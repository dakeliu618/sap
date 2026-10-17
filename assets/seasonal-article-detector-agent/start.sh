#!/bin/sh
# start.sh — self-installing agent launcher for the Joule Studio sandbox.
# Run this instead of `python3 app/main.py` to ensure deps are always present.
set -e

AGENT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="/home/user/.venv/bin/python3"
UV="/usr/local/bin/uv"

# Check if key packages are installed; install if missing.
if ! "$VENV_PYTHON" -c "import uvicorn, a2a, langchain" 2>/dev/null; then
  echo "[start.sh] Installing dependencies..."
  "$UV" pip install --python "$VENV_PYTHON" \
    "uvicorn[standard]" "fastapi" "a2a-sdk[all]==0.3.22" \
    "langchain==1.3.10" "langchain-core==1.6.1" "langgraph==1.2.6" \
    "litellm" "langchain-litellm" "sap-cloud-sdk" \
    "httpx==0.28.1" "statsmodels==0.14.4" "numpy==2.2.6" \
    "python-dotenv" 2>&1
  echo "[start.sh] Dependencies installed."
else
  echo "[start.sh] Dependencies already present."
fi

# Start the agent on port 4004 with mock mode enabled.
cd "$AGENT_DIR"
exec "$VENV_PYTHON" app/main.py --port 4004 "$@"
