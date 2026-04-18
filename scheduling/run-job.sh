#!/bin/bash
# Generic job wrapper for scheduled tasks.
# Usage: run-job.sh <job-id> <python-script>
#
# - Waits for network readiness
# - Runs the Python script, captures stdout+stderr to a log file
# - Writes a status JSON to local-data/service-status/

set -euo pipefail

JOB_ID="${1:?Usage: run-job.sh <job-id> <python-script> [script-args...]}"
SCRIPT="${2:?Usage: run-job.sh <job-id> <python-script> [script-args...]}"
shift 2
SCRIPT_ARGS=("$@")

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Pick the first Python that exists. Prefers project venv → Homebrew 3.11 → system python3.
# This lets the wrapper work across teammates' Macs without hardcoding a single path.
for candidate in \
  "$PROJECT_ROOT/.venv/bin/python3" \
  "/opt/homebrew/bin/python3.11" \
  "/usr/local/bin/python3.11" \
  "/usr/local/bin/python3" \
  "/opt/homebrew/bin/python3" \
  "/usr/bin/python3"; do
  if [ -x "$candidate" ]; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "${PYTHON:-}" ]; then
  echo "[ERROR] No usable python interpreter found"
  exit 1
fi
LOG_DIR="$PROJECT_ROOT/local-data/logs"
STATUS_DIR="$PROJECT_ROOT/local-data/service-status"

# Load .env for Slack webhook
if [ -f "$PROJECT_ROOT/.env" ]; then
  SLACK_WEBHOOK_URL_JARVIS="$(grep '^SLACK_WEBHOOK_URL_JARVIS=' "$PROJECT_ROOT/.env" | cut -d= -f2-)"
fi

mkdir -p "$LOG_DIR" "$STATUS_DIR"

# ── Slack notification helper ──────────────────────────────
notify_slack() {
  local status="$1"
  local duration="$2"
  local exit_code="${3:-0}"

  [ -z "${SLACK_WEBHOOK_URL_JARVIS:-}" ] && return 0

  # Format duration as Xm Ys
  local mins=$((duration / 60))
  local secs=$((duration % 60))
  local dur_str=""
  if [ "$mins" -gt 0 ]; then
    dur_str="${mins}m ${secs}s"
  else
    dur_str="${secs}s"
  fi

  # Pick emoji
  local emoji
  case "$status" in
    success)            emoji="white_check_mark" ;;
    failed)             emoji="x" ;;
    network_unavailable) emoji="warning" ;;
    *)                  emoji="grey_question" ;;
  esac

  # Extract SUMMARY block from log (everything after the SUMMARY divider)
  local summary=""
  if [ -f "$LOGFILE" ]; then
    summary="$(sed -n '/^SUMMARY$/,$ p' "$LOGFILE" | tail -n +3 | head -20)"
  fi

  # Build message text
  local text=":${emoji}: *${JOB_ID}* — ${status} (${dur_str})"
  if [ "$status" = "failed" ]; then
    text="${text} | exit ${exit_code}"
  fi
  if [ -n "$summary" ]; then
    text="${text}\n\`\`\`${summary}\`\`\`"
  fi

  # Post (fire-and-forget, don't fail the wrapper)
  curl -s -X POST -H 'Content-type: application/json' \
    --data "{\"text\": \"${text}\"}" \
    "$SLACK_WEBHOOK_URL_JARVIS" >/dev/null 2>&1 || true
}

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
    notify_slack "network_unavailable" "$WAITED" 1
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

EXIT_CODE=0
"$PYTHON" "$PROJECT_ROOT/$SCRIPT" ${SCRIPT_ARGS[@]+"${SCRIPT_ARGS[@]}"} >> "$LOGFILE" 2>&1 || EXIT_CODE=$?

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

# Notify Slack
notify_slack "$STATUS" "$DURATION" "$EXIT_CODE"
