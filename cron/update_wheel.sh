#!/usr/bin/env bash
#
# update_wheel.sh — runs the v2 GenAI wheel update.
#
# Designed to be invoked from cron. Captures all output to a daily log file,
# and uses a lock file to prevent concurrent runs from overlapping if a
# previous run is still going.
#
# Example crontab entry — run every Monday at 06:00:
#   0 6 * * 1 /path/to/genai-wheel/cron/update_wheel.sh
#
# Make sure this script is executable: chmod +x cron/update_wheel.sh

set -euo pipefail

# Find the project root (parent of cron/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Where to write logs
LOG_DIR="$PROJECT_ROOT/cron/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).log"

# Prevent overlap with a previous run
LOCK_FILE="$PROJECT_ROOT/cron/.update.lock"
if [ -f "$LOCK_FILE" ]; then
    PID=$(cat "$LOCK_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "$(date -Iseconds) — another update is running (pid $PID); exiting" >> "$LOG_FILE"
        exit 0
    fi
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# Determine Python interpreter — prefer a venv if present
if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
    PY="$PROJECT_ROOT/.venv/bin/python"
else
    PY="$(command -v python3 || command -v python)"
fi

# Run the update
{
    echo "===================================================================="
    echo "Run start: $(date -Iseconds)"
    echo "Python:    $PY"
    echo "===================================================================="
    "$PY" main.py --quiet
    UPDATE_EXIT=$?
    if [ "$UPDATE_EXIT" -eq 0 ]; then
        # Refresh logos too (only really needed when new tools were added,
        # but cheap to run since cached logos won't re-download)
        "$PY" main.py --refresh-logos --quiet
    fi
    echo "Run end:   $(date -Iseconds)"
    echo ""
} >> "$LOG_FILE" 2>&1
