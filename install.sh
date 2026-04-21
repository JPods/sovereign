#!/usr/bin/env bash
# Sovereign — one-command installer
# curl -fsSL https://raw.githubusercontent.com/JPods/sovereign/main/install.sh | bash
#
# What this does:
#   1. Check/install prerequisites
#   2. Ask install location
#   3. Copy Sovereign files
#   4. Run profile wizard
#   5. Register Athena LLMs with Ollama
#   6. Start watcher
#   7. Open audit console

set -euo pipefail

REPO="https://raw.githubusercontent.com/JPods/sovereign/main"
DEFAULT_HOME="$HOME/sovereign"

red()    { echo -e "\033[0;31m$*\033[0m"; }
green()  { echo -e "\033[0;32m$*\033[0m"; }
yellow() { echo -e "\033[0;33m$*\033[0m"; }
bold()   { echo -e "\033[1m$*\033[0m"; }

bold "\n═══════════════════════════════════════"
bold "  Sovereign — User-Sovereignty AI"
bold "═══════════════════════════════════════\n"

# ── Prereq checks ─────────────────────────────────────────────────────────────

check_prereq() {
  local name="$1" cmd="$2" install_hint="$3"
  if command -v "$cmd" &>/dev/null; then
    green "  ✓ $name"
  else
    yellow "  ✗ $name not found."
    echo "    Install: $install_hint"
    read -r -p "    Install now? [y/N] " yn
    if [[ "$yn" =~ ^[Yy]$ ]]; then
      eval "$install_hint"
    else
      red "    $name is required. Aborting."
      exit 1
    fi
  fi
}

echo "Checking prerequisites..."
check_prereq "Homebrew"  "brew"    '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
check_prereq "Ollama"    "ollama"  'brew install ollama'
check_prereq "Python 3"  "python3" 'brew install python3'
check_prereq "fswatch"   "fswatch" 'brew install fswatch'

# ── Install location ──────────────────────────────────────────────────────────

echo ""
bold "Where should Sovereign live?"
echo "  This folder holds your config, logs, agent files, and harvest summaries."
echo "  An external drive works well (survives reinstalls)."
echo "  Default: $DEFAULT_HOME"
echo ""
read -r -p "Install path [press Enter for default]: " SOVEREIGN_HOME
SOVEREIGN_HOME="${SOVEREIGN_HOME:-$DEFAULT_HOME}"
SOVEREIGN_HOME="${SOVEREIGN_HOME/#\~/$HOME}"  # expand tilde

mkdir -p "$SOVEREIGN_HOME"/{scripts,config,athena,today,readmes,knowledge}
green "  ✓ Created $SOVEREIGN_HOME"

# ── Download files ────────────────────────────────────────────────────────────

echo ""
echo "Downloading Sovereign files..."

download() {
  local src="$1" dest="$2"
  mkdir -p "$(dirname "$dest")"
  curl -fsSL "$REPO/$src" -o "$dest"
}

download scripts/watcher.sh       "$SOVEREIGN_HOME/scripts/watcher.sh"
download scripts/watcher-start.sh "$SOVEREIGN_HOME/scripts/watcher-start.sh"
download scripts/watcher-stop.sh  "$SOVEREIGN_HOME/scripts/watcher-stop.sh"
download scripts/harvest.py       "$SOVEREIGN_HOME/scripts/harvest.py"
download scripts/athena_review.py "$SOVEREIGN_HOME/scripts/athena_review.py"
download scripts/audit.py         "$SOVEREIGN_HOME/scripts/audit.py"
download athena/athena.modelfile       "$SOVEREIGN_HOME/athena/athena.modelfile"
download athena/athena-triage.modelfile "$SOVEREIGN_HOME/athena/athena-triage.modelfile"
download athena/athena-reason.modelfile "$SOVEREIGN_HOME/athena/athena-reason.modelfile"
download setup/profile_wizard.py  "$SOVEREIGN_HOME/setup/profile_wizard.py"

chmod +x "$SOVEREIGN_HOME/scripts/watcher.sh"
chmod +x "$SOVEREIGN_HOME/scripts/watcher-start.sh"
chmod +x "$SOVEREIGN_HOME/scripts/watcher-stop.sh"

# Write SOVEREIGN_HOME into each script
sed -i '' "s|SOVEREIGN_HOME_PLACEHOLDER|$SOVEREIGN_HOME|g" \
  "$SOVEREIGN_HOME/scripts/watcher.sh" \
  "$SOVEREIGN_HOME/scripts/watcher-start.sh" \
  "$SOVEREIGN_HOME/scripts/watcher-stop.sh" 2>/dev/null || \
sed -i "s|SOVEREIGN_HOME_PLACEHOLDER|$SOVEREIGN_HOME|g" \
  "$SOVEREIGN_HOME/scripts/watcher.sh" \
  "$SOVEREIGN_HOME/scripts/watcher-start.sh" \
  "$SOVEREIGN_HOME/scripts/watcher-stop.sh"

green "  ✓ Scripts downloaded"

# ── Profile wizard ────────────────────────────────────────────────────────────

if [[ -f "$SOVEREIGN_HOME/config/profile.json" ]]; then
  yellow "  Profile already exists at $SOVEREIGN_HOME/config/profile.json — skipping wizard."
else
  echo ""
  bold "Running profile wizard..."
  python3 "$SOVEREIGN_HOME/setup/profile_wizard.py" --home "$SOVEREIGN_HOME"
fi

# ── Register Athena LLMs ──────────────────────────────────────────────────────

echo ""
bold "Checking Ollama models for Athena..."

register_model() {
  local name="$1" modelfile="$2"
  if ollama list 2>/dev/null | grep -q "^$name"; then
    green "  ✓ $name already registered"
  else
    echo "  Registering $name..."
    cp "$modelfile" "/tmp/${name}.modelfile"
    if ollama create "$name" -f "/tmp/${name}.modelfile" &>/dev/null; then
      green "  ✓ $name registered"
    else
      yellow "  ✗ Failed to register $name. Check Ollama is running: ollama serve"
    fi
  fi
}

register_model "athena-triage" "$SOVEREIGN_HOME/athena/athena-triage.modelfile"
register_model "athena"        "$SOVEREIGN_HOME/athena/athena.modelfile"
register_model "athena-reason" "$SOVEREIGN_HOME/athena/athena-reason.modelfile"

# ── Start watcher ─────────────────────────────────────────────────────────────

echo ""
bold "Starting watcher..."
bash "$SOVEREIGN_HOME/scripts/watcher-start.sh"

# ── Install LaunchAgent (optional) ───────────────────────────────────────────

echo ""
read -r -p "Install LaunchAgent so watcher starts at login? [y/N] " yn
if [[ "$yn" =~ ^[Yy]$ ]]; then
  PLIST="$HOME/Library/LaunchAgents/com.sovereign.watcher.plist"
  cat > "$PLIST" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.sovereign.watcher</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$SOVEREIGN_HOME/scripts/watcher-start.sh</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>StandardErrorPath</key><string>/tmp/sovereign-watcher-stderr.log</string>
</dict>
</plist>
PLIST_EOF
  launchctl load "$PLIST" 2>/dev/null || true
  green "  ✓ LaunchAgent installed"
fi

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
bold "═══════════════════════════════════════"
bold "  Sovereign installed."
bold "═══════════════════════════════════════"
echo ""
echo "  Home:      $SOVEREIGN_HOME"
echo "  Profile:   $SOVEREIGN_HOME/config/profile.json"
echo "  Audit UI:  python3 $SOVEREIGN_HOME/scripts/audit.py"
echo "  Harvest:   python3 $SOVEREIGN_HOME/scripts/harvest.py"
echo "  Stop:      $SOVEREIGN_HOME/scripts/watcher-stop.sh"
echo ""
green "  Audit console opening at http://localhost:7373 ..."
python3 "$SOVEREIGN_HOME/scripts/audit.py" &
