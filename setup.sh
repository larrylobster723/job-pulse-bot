#!/usr/bin/env bash
# TechPulse Jobs Bot — One-command setup
# Usage: bash setup.sh
#
# What this script does:
#   1. Checks all prerequisites (Python 3.11+, curl, git) — installs Python via Homebrew if missing
#   2. Creates a Python virtual environment
#   3. Installs all dependencies
#   4. Prompts you for your Discord bot token, guild ID, and channel ID
#   5. Creates your .env file automatically
#   6. Initialises the SQLite database
#   7. Verifies your bot token is valid before finishing

set -e

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Colour

ok()   { echo -e "  ${GREEN}✅ $1${NC}"; }
warn() { echo -e "  ${YELLOW}⚠️  $1${NC}"; }
err()  { echo -e "  ${RED}❌ $1${NC}"; }
info() { echo -e "  ${BLUE}ℹ️  $1${NC}"; }
step() { echo -e "\n${BOLD}▶ $1${NC}"; }

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   TechPulse Jobs Bot — Setup             ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "  This script will set up everything you need to run the bot."
echo "  It will ask you 3 questions — have your Discord values ready."
echo "  (See README.md → Step 1 if you haven't done the Discord setup yet)"
echo ""
read -r -p "  Press Enter to begin..."

# ── 1. Check OS ───────────────────────────────────────────────────────────────
step "Checking your system..."

OS="$(uname -s)"
case "$OS" in
  Darwin)  ok "macOS detected" ;;
  Linux)   ok "Linux detected" ;;
  *)
    err "Unsupported OS: $OS"
    echo "      This script supports macOS and Linux."
    echo "      On Windows: install WSL2 first, then re-run this script inside WSL."
    echo "      Guide: https://learn.microsoft.com/en-us/windows/wsl/install"
    exit 1
    ;;
esac

# ── 2. Check git ──────────────────────────────────────────────────────────────
step "Checking Git..."
if command -v git &>/dev/null; then
  ok "Git found: $(git --version)"
else
  err "Git is not installed."
  if [ "$OS" = "Darwin" ]; then
    echo ""
    echo "      To install Git on macOS, run:"
    echo "        xcode-select --install"
    echo "      A popup will appear — click Install and wait for it to finish."
    echo "      Then re-run this script."
  else
    echo "      To install Git on Linux, run:"
    echo "        sudo apt-get install git   (Ubuntu/Debian)"
    echo "        sudo yum install git       (CentOS/RHEL)"
    echo "      Then re-run this script."
  fi
  exit 1
fi

# ── 3. Check curl ─────────────────────────────────────────────────────────────
step "Checking curl..."
if command -v curl &>/dev/null; then
  ok "curl found"
else
  warn "curl not found — bot token verification will be skipped"
  SKIP_TOKEN_VERIFY=true
fi

# ── 4. Check Python 3.11+ ─────────────────────────────────────────────────────
step "Checking Python 3.11+..."

PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$cmd" &>/dev/null; then
    MAJOR=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo 0)
    MINOR=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 0)
    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 11 ]; then
      PYTHON="$cmd"
      ok "Python found: $("$cmd" --version)"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  err "Python 3.11 or higher is required but was not found."
  echo ""

  if [ "$OS" = "Darwin" ]; then
    echo "  How to install Python on macOS:"
    echo ""
    echo "  Option A — Homebrew (recommended):"
    echo "    1. Install Homebrew if you don't have it:"
    echo "         /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo "    2. Install Python:"
    echo "         brew install python@3.13"
    echo "    3. Re-run this script."
    echo ""
    echo "  Option B — Python.org installer:"
    echo "    1. Go to https://python.org/downloads"
    echo "    2. Click 'Download Python 3.13.x' (the big yellow button)"
    echo "    3. Open the downloaded .pkg file and follow the installer"
    echo "    4. Re-run this script."

    # Offer to install via Homebrew automatically
    echo ""
    if command -v brew &>/dev/null; then
      read -r -p "  Homebrew is already installed. Install Python 3.13 now? [y/N]: " INSTALL_PY
      if [[ "$INSTALL_PY" =~ ^[Yy]$ ]]; then
        echo "  Installing Python 3.13 via Homebrew..."
        brew install python@3.13
        PYTHON="$(brew --prefix)/bin/python3.13"
        ok "Python installed: $($PYTHON --version)"
      else
        echo "  Install Python manually then re-run this script."
        exit 1
      fi
    else
      exit 1
    fi
  else
    echo "  How to install Python on Linux:"
    echo ""
    echo "  Ubuntu / Debian:"
    echo "    sudo apt-get update && sudo apt-get install python3.11 python3.11-venv"
    echo ""
    echo "  CentOS / RHEL / Fedora:"
    echo "    sudo dnf install python3.11"
    echo ""
    echo "  After installing, re-run this script."
    exit 1
  fi
fi

# ── 5. Create virtual environment ─────────────────────────────────────────────
step "Setting up virtual environment..."

VENV_DIR=".venv"
if [ -d "$VENV_DIR" ]; then
  info ".venv already exists — skipping creation"
else
  "$PYTHON" -m venv "$VENV_DIR"
  ok "Virtual environment created in .venv/"
fi

PIP="$VENV_DIR/bin/pip"
PYTHON_VENV="$VENV_DIR/bin/python"

# ── 6. Install dependencies ───────────────────────────────────────────────────
step "Installing dependencies..."
echo "  This may take 30–60 seconds..."
"$PIP" install --upgrade pip -q
"$PIP" install -r requirements.txt -q
ok "All dependencies installed"

# ── 7. Create .env ────────────────────────────────────────────────────────────
step "Configuring your Discord credentials..."

if [ -f ".env" ]; then
  info ".env already exists — skipping"
  info "To reconfigure, delete .env and re-run this script"
else
  echo ""
  echo "  You need 3 values from your Discord setup."
  echo "  Haven't done that yet? See README.md → Step 1 for a full guide."
  echo ""
  echo "  ┌─────────────────────────────────────────────────────────┐"
  echo "  │  Where to find each value:                              │"
  echo "  │                                                         │"
  echo "  │  Bot Token    → discord.com/developers/applications     │"
  echo "  │                 → Your app → Bot → Reset Token          │"
  echo "  │                                                         │"
  echo "  │  Guild ID     → Right-click your server name            │"
  echo "  │                 → Copy Server ID                        │"
  echo "  │                 (requires Developer Mode — see README)  │"
  echo "  │                                                         │"
  echo "  │  Channel ID   → Right-click your #jobs channel          │"
  echo "  │                 → Copy Channel ID                       │"
  echo "  └─────────────────────────────────────────────────────────┘"
  echo ""

  # Bot Token
  while true; do
    read -r -p "  Paste your Bot Token: " BOT_TOKEN
    BOT_TOKEN="$(echo "$BOT_TOKEN" | tr -d '[:space:]')"
    if [ -z "$BOT_TOKEN" ]; then
      err "Bot token cannot be empty. Try again."
    elif [ ${#BOT_TOKEN} -lt 50 ]; then
      err "That doesn't look like a valid token (too short). Check you copied the full token."
    else
      ok "Bot token received"
      break
    fi
  done

  echo ""

  # Guild ID
  while true; do
    read -r -p "  Paste your Guild (Server) ID: " GUILD_ID
    GUILD_ID="$(echo "$GUILD_ID" | tr -d '[:space:]')"
    if [ -z "$GUILD_ID" ]; then
      err "Guild ID cannot be empty. Try again."
    elif ! [[ "$GUILD_ID" =~ ^[0-9]+$ ]]; then
      err "Guild ID should be a number (e.g. 1234567890123456789). Check you right-clicked the server name, not a channel."
    else
      ok "Guild ID received"
      break
    fi
  done

  echo ""

  # Channel ID
  while true; do
    read -r -p "  Paste your Channel ID (for #jobs): " CHANNEL_ID
    CHANNEL_ID="$(echo "$CHANNEL_ID" | tr -d '[:space:]')"
    if [ -z "$CHANNEL_ID" ]; then
      err "Channel ID cannot be empty. Try again."
    elif ! [[ "$CHANNEL_ID" =~ ^[0-9]+$ ]]; then
      err "Channel ID should be a number. Check you right-clicked the #jobs channel."
    else
      ok "Channel ID received"
      break
    fi
  done

  # Write .env
  cat > .env << EOF
# ── Required ─────────────────────────────────────────────────────────────────
DISCORD_BOT_TOKEN=${BOT_TOKEN}
DISCORD_GUILD_ID=${GUILD_ID}
DISCORD_JOBS_CHANNEL_ID=${CHANNEL_ID}

# ── Optional (defaults shown) ─────────────────────────────────────────────────
DB_PATH=jobs.db
POLL_INTERVAL_SECONDS=3600
DEDUP_THRESHOLD=85
PULSE_POST_THRESHOLD=60
PULSE_HOT_THRESHOLD=80
SALARY_MARKET_MEDIAN_USD=80000
ENABLED_SOURCES=remoteok,arbeitnow
LOG_LEVEL=INFO
EOF
  ok ".env file created"
fi

# ── 8. Initialise database ────────────────────────────────────────────────────
step "Initialising database..."
"$PYTHON_VENV" -m src.db.init
ok "Database ready (jobs.db)"

# ── 9. Verify bot token ───────────────────────────────────────────────────────
step "Verifying bot token..."

if [ "${SKIP_TOKEN_VERIFY}" = "true" ]; then
  warn "Skipped (curl not available)"
else
  TOKEN=$(grep "^DISCORD_BOT_TOKEN=" .env | cut -d= -f2 | tr -d '[:space:]')
  HTTP_STATUS=$(curl -s -o /tmp/discord_verify.json -w "%{http_code}" \
    -H "Authorization: Bot ${TOKEN}" \
    https://discord.com/api/v10/users/@me 2>/dev/null || echo "000")

  if [ "$HTTP_STATUS" = "200" ]; then
    BOT_NAME=$("$PYTHON_VENV" -c "import json; d=json.load(open('/tmp/discord_verify.json')); print(d.get('username','unknown'))" 2>/dev/null || echo "unknown")
    ok "Token valid — bot username: ${BOT_NAME}"
  elif [ "$HTTP_STATUS" = "401" ]; then
    err "Token is invalid (HTTP 401 — Unauthorized)"
    echo ""
    echo "      Your DISCORD_BOT_TOKEN in .env is not valid."
    echo "      To fix:"
    echo "        1. Go to discord.com/developers/applications"
    echo "        2. Select your app → Bot → Reset Token → copy the new token"
    echo "        3. Open .env in a text editor and replace the DISCORD_BOT_TOKEN value"
    echo "        4. Re-run: bash setup.sh"
    exit 1
  else
    warn "Could not verify token (HTTP ${HTTP_STATUS}) — check your internet connection"
    warn "The bot may still work — try running it with: make run"
  fi
  rm -f /tmp/discord_verify.json
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║   ✅ Setup complete!                     ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "  To start the bot, run:"
echo ""
echo -e "    ${BOLD}make run${NC}"
echo ""
echo "  The bot will:"
echo "    • Connect to your Discord server"
echo "    • Register the /pulse and /pipeline slash commands"
echo "    • Immediately fetch and score jobs from RemoteOK and Arbeitnow"
echo "    • Post qualifying jobs to your #jobs channel"
echo "    • Continue running on a 1-hour schedule"
echo ""
echo "  To run tests:"
echo -e "    ${BOLD}make test${NC}"
echo ""
