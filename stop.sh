#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/data/pids.txt"

if [ -f "$PID_FILE" ]; then
    for PID in $(cat "$PID_FILE"); do
        kill "$PID" 2>/dev/null && echo "Stopped PID $PID"
    done
    rm -f "$PID_FILE"
    echo "JARVIS stopped."
else
    echo "No PID file found. JARVIS may not be running."
fi
