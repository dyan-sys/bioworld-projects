#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/run-job.sh" pipeline-report \
  .claude/skills/check-recruit-status/workflows/check_recruit_status.py
