#!/bin/bash
# Wrapper script for daily pipeline report via launchd.
# Sets up environment and logs output.

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/local-data/logs"
PYTHON="/opt/homebrew/bin/python3.11"
SCRIPT="$PROJECT_ROOT/.claude/skills/check-recruit-status/workflows/check_recruit_status.py"

mkdir -p "$LOG_DIR"

TIMESTAMP="$(date -u +%Y-%m-%d_%H%M_UTC)"

cd "$PROJECT_ROOT" || exit 1

"$PYTHON" "$SCRIPT" >> "$LOG_DIR/pipeline-report_${TIMESTAMP}.log" 2>&1
