#!/usr/bin/env bash
# watcher.sh — Sovereign background activity daemon
# Watches your projects and apps while no session is open.
# Writes to SOVEREIGN_HOME/today/YYYY-MM-DD-activity.log
#
# Do not edit SOVEREIGN_HOME_PLACEHOLDER — the installer replaces it.
# To add projects, edit config/profile.json and restart.
#
# Start:   ./watcher-start.sh
# Stop:    ./watcher-stop.sh
# Harvest: python3 ../scripts/harvest.py
# Requires: brew install fswatch

# NOTE: no set -euo pipefail — daemon must not exit on non-zero returns

SOVEREIGN="SOVEREIGN_HOME_PLACEHOLDER"
HOME_DIR="$HOME"
PID_FILE="/tmp/sovereign-watcher.pid"

if [[ ! -d "$SOVEREIGN" ]]; then
  echo "Sovereign home not found: $SOVEREIGN" >&2
  exit 1
fi

echo $$ > "$PID_FILE"

TODAY=$(date +%Y-%m-%d)
LOG="$SOVEREIGN/today/${TODAY}-activity.log"
mkdir -p "$SOVEREIGN/today"
touch "$LOG"

log() {
  local level="$1"; shift
  local ts
  ts=$(date +"%H:%M:%S")
  echo "[$ts] [$level] $*" >> "$LOG"
}

# ── Read projects from profile.json ─────────────────────────────────────────
# Extract project ids and paths using Python (avoids jq dependency)
read_projects() {
  python3 - <<'PYEOF'
import json, pathlib, os
profile_path = pathlib.Path(os.environ["SOVEREIGN"]) / "config" / "profile.json"
try:
    profile = json.loads(profile_path.read_text())
    for p in profile["monitoring"]["projects"]:
        if p.get("enabled", True):
            path = p["path"].replace("~", os.environ["HOME"])
            print(f"{p['id']}|{path}")
except Exception as e:
    import sys
    print(f"ERROR: {e}", file=sys.stderr)
PYEOF
}

declare -a PROJ_IDS
declare -a PROJ_DIRS
while IFS='|' read -r pid pdir; do
  PROJ_IDS+=("$pid")
  PROJ_DIRS+=("$pdir")
done < <(SOVEREIGN="$SOVEREIGN" read_projects)

if [[ ${#PROJ_IDS[@]} -eq 0 ]]; then
  log "WARN" "No projects found in profile.json"
fi

log "START" "Watcher started (PID $$). Projects: ${PROJ_IDS[*]:-none}"

# ── Cleanup ───────────────────────────────────────────────────────────────────

cleanup() {
  log "STOP" "Watcher stopped (PID $$)."
  rm -f "$PID_FILE"
  [[ -n "${FSWATCH_PID:-}" ]] && kill "$FSWATCH_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ── App state ─────────────────────────────────────────────────────────────────

APP_WAS_SketchUp=false
APP_WAS_Code=false
APP_WAS_zoom=false
APP_WAS_Chrome=false

# ── File classifier ───────────────────────────────────────────────────────────

classify_change() {
  local project="$1"
  local path="$2"

  # Skip noise
  [[ "$path" =~ \.skb$|\.bak$|__pycache__|\.DS_Store|\.pyc$|toolbar_icons ]] && return

  local rel="$path"

  if   [[ "$path" =~ \.(rb|py|js|ts|tsx|jsx|go|rs|swift|sh)$ ]]; then
    log "CODE[$project]" "${path##*/}"
  elif [[ "$path" =~ \.(html|css|scss)$ ]]; then
    log "CODE[$project]" "Template: ${path##*/}"
  elif [[ "$path" =~ \.(skp|blend|fbx|obj)$ ]]; then
    log "MODEL[$project]" "${path##*/}"
  elif [[ "$path" =~ \.json$ ]]; then
    log "DATA[$project]" "${path##*/}"
  elif [[ "$path" =~ \.(md|txt|docx|pdf)$ ]]; then
    log "WRITE[$project]" "${path##*/}"
  fi
}

# ── File watcher ──────────────────────────────────────────────────────────────

if ! command -v fswatch &>/dev/null; then
  log "WARN" "fswatch not installed — run: brew install fswatch"
else
  WATCH_DIRS=()
  for i in "${!PROJ_IDS[@]}"; do
    dir="${PROJ_DIRS[$i]}"
    if [[ -d "$dir" ]]; then
      WATCH_DIRS+=("$dir")
    else
      log "WARN" "Directory not found: ${PROJ_IDS[$i]} → $dir"
    fi
  done

  if [[ ${#WATCH_DIRS[@]} -gt 0 ]]; then
    fswatch \
      --recursive \
      --event=Updated \
      --event=Created \
      --event=Removed \
      --latency=2.0 \
      "${WATCH_DIRS[@]}" \
    | while read -r changed_path; do
        # Match path to project
        best_project=""
        best_len=0
        for i in "${!PROJ_IDS[@]}"; do
          dir="${PROJ_DIRS[$i]}"
          if [[ "$changed_path" == "$dir"* ]] && [[ ${#dir} -gt $best_len ]]; then
            best_project="${PROJ_IDS[$i]}"
            best_len=${#dir}
          fi
        done
        [[ -n "$best_project" ]] && classify_change "$best_project" "$changed_path"
      done &
    FSWATCH_PID=$!
  fi
fi

# ── Main poll loop ────────────────────────────────────────────────────────────

while true; do
  if [[ ! -d "$SOVEREIGN" ]]; then
    log "STOP" "Sovereign home gone. Watcher exiting."
    exit 0
  fi

  # Midnight rollover
  NEW_TODAY=$(date +%Y-%m-%d)
  if [[ "$NEW_TODAY" != "$TODAY" ]]; then
    TODAY="$NEW_TODAY"
    LOG="$SOVEREIGN/today/${TODAY}-activity.log"
    touch "$LOG"
    log "START" "New day — log rolled over."
  fi

  # App polling
  for app in "SketchUp" "Code" "zoom.us" "Google Chrome"; do
    var="APP_WAS_${app//[. ]/_}"
    was=$(eval echo \$"$var" 2>/dev/null || echo false)
    if pgrep -x "$app" &>/dev/null; then
      if [[ "$was" == "false" ]]; then
        case "$app" in
          "SketchUp")      log "APP" "SketchUp opened" ;;
          "Code")          log "APP" "VS Code opened — coding session" ;;
          "zoom.us")       log "APP" "Zoom opened — meeting likely" ;;
          "Google Chrome") log "APP" "Chrome opened" ;;
        esac
        eval "$var=true"
      fi
    else
      if [[ "$was" == "true" ]]; then
        log "APP" "$app closed"
        eval "$var=false"
      fi
    fi
  done

  sleep 30
done
