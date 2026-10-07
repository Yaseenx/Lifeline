#!/usr/bin/env bash
# LifeLine — single start command.
# Launches the BACKEND (FastAPI + the 10 Hz engine, broadcast, and route loops —
# all inside ONE uvicorn process) and the VEHICLE DASHBOARD (Vite), then waits.
# No runner.py. No --reload (so no extra watcher/child process is forked).
# Press Ctrl+C once to stop both.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER="$ROOT/server"
DASH="$ROOT/ambulance-unit/dashboard"
UVICORN="$SERVER/.venv/bin/uvicorn"

pids=()
cleanup() {
  trap - INT TERM EXIT
  echo
  echo "[lifeline] stopping…"
  for pid in "${pids[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

if [ ! -x "$UVICORN" ]; then
  echo "[lifeline] uvicorn not found in the server venv:"
  echo "           $UVICORN"
  echo "           create it once with:"
  echo "           cd \"$SERVER\" && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

echo "[lifeline] backend  → http://localhost:4000/   (ops map)"
echo "                      http://localhost:4000/console   (call-taker)"
echo "                      http://localhost:4000/hospital  (hospital dashboard)"
( cd "$SERVER" && exec "$UVICORN" app:app --port 4000 ) &
pids+=($!)

echo "[lifeline] dashboard → Vite dev server (watch below for its URL, usually http://localhost:5173)"
( cd "$DASH" && exec npm run dev ) &
pids+=($!)

echo "[lifeline] agent     → ambulance-unit/agent/main.py"
AGENT_PYTHON="$ROOT/ambulance-unit/.venv/bin/python"
if [ ! -x "$AGENT_PYTHON" ]; then
  AGENT_PYTHON="python3"
fi
( cd "$ROOT/ambulance-unit/agent" && exec "$AGENT_PYTHON" main.py ) &
pids+=($!)

echo "[lifeline] all running in one command. No runner.py, no --reload. Ctrl+C to stop all."
wait
