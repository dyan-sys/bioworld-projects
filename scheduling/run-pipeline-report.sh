#!/bin/bash
# Wrapper script for daily pipeline report via launchd.
# Sets up environment and logs output.

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/local-data/logs"
PYTHON="/opt/homebrew/bin/python3.11"
SCRIPT="$PROJECT_ROOT/.claude/skills/check-recruit-status/workflows/check_recruit_status.py"

mkdir -p "$LOG_DIR"

TIMESTAMP="$(date -u +%Y-%m-%d_%H%M_UTC)"
LOGFILE="$LOG_DIR/pipeline-report_${TIMESTAMP}.log"

cd "$PROJECT_ROOT" || exit 1

# Wait for network after wake-from-sleep (launchd may fire before DNS is ready)
MAX_WAIT=60
WAITED=0
while ! host api.notion.com >/dev/null 2>&1; do
  if [ "$WAITED" -ge "$MAX_WAIT" ]; then
    echo "ERROR: Network not available after ${MAX_WAIT}s, aborting." >> "$LOGFILE"
    exit 1
  fi
  sleep 5
  WAITED=$((WAITED + 5))
done

if [ "$WAITED" -gt 0 ]; then
  echo "Network ready after ${WAITED}s wait." >> "$LOGFILE"
fi

"$PYTHON" "$SCRIPT" >> "$LOGFILE" 2>&1
