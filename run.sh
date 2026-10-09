#!/usr/bin/env bash
# One-command local dev runner for AI-CRM: crm-service (:8001), ai-service (:8000),
# frontend (:3000). Ctrl+C stops everything. Logs go to ./logs/*.log.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

PIDS=()

cleanup() {
    echo
    echo "Stopping services..."
    for pid in "${PIDS[@]+"${PIDS[@]}"}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    # Each backend forks worker processes (uvicorn multiprocessing) that
    # aren't direct children of the PIDs above, so a plain kill leaves them
    # running and holding the ports. Sweep by port as a hard fallback.
    for port in 8003 8002 3001 8001 8000 3000; do
        local_pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
        if [ -n "$local_pids" ]; then
            echo "$local_pids" | xargs kill -9 2>/dev/null || true
        fi
    done
    echo "Stopped."
}
trap cleanup EXIT INT TERM

check_env() {
    local dir="$1"
    if [ ! -f "$dir/.env" ] && [ ! -f "$dir/.env.local" ]; then
        echo "Missing $dir/.env — copy $dir/.env.example first (see RUNNING.md)."
        exit 1
    fi
}

check_venv() {
    local dir="$1"
    if [ ! -x "$dir/venv/bin/python3" ]; then
        echo "Missing $dir/venv — run: cd $dir && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"
        exit 1
    fi
}

wait_healthy() {
    local name="$1" url="$2"
    for _ in $(seq 1 30); do
        if curl -s -o /dev/null -w '' "$url" 2>/dev/null; then
            echo "$name is up ($url)"
            return 0
        fi
        sleep 1
    done
    echo "$name did not become healthy at $url within 30s — check $LOG_DIR/${name}.log"
    return 1
}

check_env "$ROOT/crm-service"
check_env "$ROOT/ai-service"
check_env "$ROOT/frontend"
check_venv "$ROOT/crm-service"
check_venv "$ROOT/ai-service"

echo "Starting crm-service (:8003)..."
(cd "$ROOT/crm-service" && DEBUG=true ./venv/bin/python3 main.py) > "$LOG_DIR/crm-service.log" 2>&1 &
PIDS+=($!)

echo "Starting ai-service (:8002)..."
(cd "$ROOT/ai-service" && DEBUG=true ./venv/bin/python3 main.py) > "$LOG_DIR/ai-service.log" 2>&1 &
PIDS+=($!)

echo "Starting frontend (:3001)..."
(cd "$ROOT/frontend" && npm run dev -- -p 3001) > "$LOG_DIR/frontend.log" 2>&1 &
PIDS+=($!)

wait_healthy "crm-service" "http://localhost:8003/health"
wait_healthy "ai-service"  "http://localhost:8002/health"
wait_healthy "frontend"    "http://localhost:3001"

echo "Starting campaign-pacer (9:00 AM - 5:30 PM, 50/day limit)..."
(cd "$ROOT" && ./crm-service/venv/bin/python3 scripts/run_humanoid_campaign_pacer.py) > "$LOG_DIR/campaign-pacer.log" 2>&1 &
PIDS+=($!)

cat <<EOF

All services running:
  frontend        http://localhost:3001
  ai-service      http://localhost:8002
  crm-service     http://localhost:8003
  campaign-pacer  Active (9:00 AM - 5:30 PM, max 50/day)

Logs: $LOG_DIR/{crm-service,ai-service,frontend,campaign-pacer}.log
Press Ctrl+C to stop everything.
EOF

wait
