#!/usr/bin/env bash
# watcher-stop.sh — stop the Sovereign activity watcher

PID_FILE="/tmp/sovereign-watcher.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "Watcher is not running."
  exit 0
fi

PID=$(cat "$PID_FILE")
if kill "$PID" 2>/dev/null; then
  echo "Watcher stopped (PID $PID)."
else
  echo "Watcher process not found — clearing PID file."
  rm -f "$PID_FILE"
fi
