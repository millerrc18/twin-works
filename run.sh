#!/usr/bin/env bash
# Start TwinWorks (bash / Git-Bash on Windows).
#   ./run.sh              -> live IFS data (falls back to snapshot until you Connect IFS)
#   ./run.sh snapshot     -> offline snapshot data only
#   PORT=8001 ./run.sh    -> override the app port (default 8000)
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-live}"          # live | snapshot
PORT="${PORT:-8000}"
PY=".venv/Scripts/python.exe"
[ -x "$PY" ] || PY=".venv/bin/python"   # non-Windows venv layout

echo "[run] applying DB migrations (idempotent)..."
"$PY" -m alembic upgrade head >/dev/null 2>&1 || echo "[run] alembic skipped (create_all will cover it)"

echo "[run] starting app  mode=$MODE  port=$PORT  (OAuth callback -> http://localhost:$PORT/callback)"
RTG_DATA_SOURCE="$MODE" RTG_APP_PORT="$PORT" "$PY" -m uvicorn app.main:app --reload --port "$PORT"
