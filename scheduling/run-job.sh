#!/bin/bash
# Generic job wrapper for scheduled tasks.
# Usage: run-job.sh <job-id> <python-script>
#
# - Waits for network readiness
# - Runs the Python script, captures stdout+stderr to a log file
# - Writes a status JSON to local-data/service-status/

set -euo pipefail

JOB_ID="${1:?Usage: run-job.sh <job-id> <python-script>}"
SCRIPT="${2:?Usage: run-job.sh <job-id> <python-script>}"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="/opt/homebrew/bin/python3.11"
LOG_DIR="$PROJECT_ROOT/local-data/logs"
STATUS_DIR="$PROJECT_ROOT/local-data/service-status"

mkdir -p "$LOG_DIR" "$STATUS_DIR"

TIMESTAMP="$(date -u +%Y-%m-%d_%H%M_UTC)"
LOGFILE="$LOG_DIR/${JOB_ID}_${TIMESTAMP}.log"

cd "$PROJECT_ROOT" || exit 1

# Wait for network after wake-from-sleep (launchd may fire before DNS is ready)
MAX_WAIT=60
WAITED=0
while ! host api.notion.com >/dev/null 2>&1; do
  if [ "$WAITED" -ge "$MAX_WAIT" ]; then
    echo "ERROR: Network not available after ${MAX_WAIT}s, aborting." >> "$LOGFILE"
    # Write status JSON for network failure
    START_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    cat > "$STATUS_DIR/${JOB_ID}_${TIMESTAMP}.json" <<EOF
{
  "job_id": "$JOB_ID",
  "started_at": "$START_ISO",
  "finished_at": "$START_ISO",
  "duration_seconds": $WAITED,
  "exit_code": 1,
  "status": "network_unavailable",
  "log_file": "local-data/logs/${JOB_ID}_${TIMESTAMP}.log"
}
EOF
    exit 1
  fi
  sleep 5
  WAITED=$((WAITED + 5))
done

if [ "$WAITED" -gt 0 ]; then
  echo "Network ready after ${WAITED}s wait." >> "$LOGFILE"
fi

# Run the job and capture timing
START_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_EPOCH="$(date +%s)"

"$PYTHON" "$PROJECT_ROOT/$SCRIPT" >> "$LOGFILE" 2>&1
EXIT_CODE=$?

END_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
END_EPOCH="$(date +%s)"
DURATION=$((END_EPOCH - START_EPOCH))

if [ "$EXIT_CODE" -eq 0 ]; then
  STATUS="success"
else
  STATUS="failed"
fi

# Write status JSON
cat > "$STATUS_DIR/${JOB_ID}_${TIMESTAMP}.json" <<EOF
{
  "job_id": "$JOB_ID",
  "started_at": "$START_ISO",
  "finished_at": "$END_ISO",
  "duration_seconds": $DURATION,
  "exit_code": $EXIT_CODE,
  "status": "$STATUS",
  "log_file": "local-data/logs/${JOB_ID}_${TIMESTAMP}.log"
}
EOF
