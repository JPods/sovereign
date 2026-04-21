#!/usr/bin/env bash
# watcher-start.sh — start the Sovereign activity watcher

SOVEREIGN="SOVEREIGN_HOME_PLACEHOLDER"
PID_FILE="/tmp/sovereign-watcher.pid"

if [[ ! -d "$SOVEREIGN" ]]; then
  echo "ERROR: Sovereign home not found: $SOVEREIGN"
  exit 1
fi

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Watcher already running (PID $(cat "$PID_FILE"))."
  exit 0
fi

nohup bash "$SOVEREIGN/scripts/watcher.sh" >> "/tmp/sovereign-watcher-stderr.log" 2>&1 &
sleep 2
if [[ -f "$PID_FILE" ]]; then
  echo "Watcher started (PID $(cat "$PID_FILE"))."
  echo "Log: $SOVEREIGN/today/$(date +%Y-%m-%d)-activity.log"
else
  echo "ERROR: Watcher failed to start. Check /tmp/sovereign-watcher-stderr.log"
fi
