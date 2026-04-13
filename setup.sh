#!/usr/bin/env bash
# TechPulse Jobs Bot — One-command setup
# Usage: bash setup.sh
set -e

PYTHON=""
VENV_DIR=".venv"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   TechPulse Jobs Bot — Setup         ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Find Python 3.11+ ─────────────────────────────────────────────────────
echo "▶ Checking Python version..."
for cmd in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$cmd" &>/dev/null; then
    VERSION=$("$cmd" -c "import sys; print(sys.version_info[:2])")
    MAJOR=$("$cmd" -c "import sys; print(sys.version_info.major)")
    MINOR=$("$cmd" -c "import sys; print(sys.version_info.minor)")
    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 11 ]; then
      PYTHON="$cmd"
      echo "  ✅ Found: $cmd ($("$cmd" --version))"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "  ❌ Python 3.11+ not found."
  echo "     Install from https://python.org or via Homebrew: brew install python@3.13"
  exit 1
fi

# ── 2. Create virtual environment ────────────────────────────────────────────
echo ""
echo "▶ Creating virtual environment..."
if [ -d "$VENV_DIR" ]; then
  echo "  ℹ️  .venv already exists — skipping"
else
  "$PYTHON" -m venv "$VENV_DIR"
  echo "  ✅ Created .venv"
fi

PIP="$VENV_DIR/bin/pip"
PYTHON_VENV="$VENV_DIR/bin/python"

# ── 3. Install dependencies ──────────────────────────────────────────────────
echo ""
echo "▶ Installing dependencies..."
"$PIP" install --upgrade pip -q
"$PIP" install -r requirements.txt -q
echo "  ✅ Dependencies installed"

# ── 4. Create .env ───────────────────────────────────────────────────────────
echo ""
echo "▶ Configuring environment..."

if [ -f ".env" ]; then
  echo "  ℹ️  .env already exists — skipping (delete it to reconfigure)"
else
  echo ""
  echo "  You'll need 3 values from your Discord setup:"
  echo "  (See README.md → Discord Setup section if you haven't done this yet)"
  echo ""

  read -r -p "  Bot Token (from discord.com/developers): " BOT_TOKEN
  if [ -z "$BOT_TOKEN" ]; then
    echo "  ❌ Bot token is required."
    exit 1
  fi

  read -r -p "  Guild (Server) ID: " GUILD_ID
  if [ -z "$GUILD_ID" ]; then
    echo "  ❌ Guild ID is required."
    exit 1
  fi

  read -r -p "  Jobs Channel ID: " CHANNEL_ID
  if [ -z "$CHANNEL_ID" ]; then
    echo "  ❌ Channel ID is required."
    exit 1
  fi

  cat > .env << EOF
# ── Required ────────────────────────────────────────────────────────────────
DISCORD_BOT_TOKEN=${BOT_TOKEN}
DISCORD_GUILD_ID=${GUILD_ID}
DISCORD_JOBS_CHANNEL_ID=${CHANNEL_ID}

# ── Optional (defaults shown) ────────────────────────────────────────────────
DB_PATH=jobs.db
POLL_INTERVAL_SECONDS=3600
DEDUP_THRESHOLD=85
PULSE_POST_THRESHOLD=60
PULSE_HOT_THRESHOLD=80
SALARY_MARKET_MEDIAN_USD=80000
ENABLED_SOURCES=remoteok,arbeitnow
LOG_LEVEL=INFO
EOF
  echo "  ✅ .env created"
fi

# ── 5. Initialise database ───────────────────────────────────────────────────
echo ""
echo "▶ Initialising database..."
"$PYTHON_VENV" -m src.db.init
echo "  ✅ Database ready"

# ── 6. Verify bot token ──────────────────────────────────────────────────────
echo ""
echo "▶ Verifying Discord bot token..."
TOKEN=$(grep DISCORD_BOT_TOKEN .env | cut -d= -f2)
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bot ${TOKEN}" \
  https://discord.com/api/v10/users/@me)

if [ "$HTTP_STATUS" = "200" ]; then
  BOT_NAME=$(curl -s \
    -H "Authorization: Bot ${TOKEN}" \
    https://discord.com/api/v10/users/@me | "$PYTHON_VENV" -c "import sys,json; d=json.load(sys.stdin); print(d.get('username','unknown'))")
  echo "  ✅ Token valid — bot username: ${BOT_NAME}"
else
  echo "  ⚠️  Token check returned HTTP ${HTTP_STATUS} — double-check your DISCORD_BOT_TOKEN in .env"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════╗"
echo "║   Setup complete! Start with:        ║"
echo "║                                      ║"
echo "║   .venv/bin/python -m src.bot.main   ║"
echo "║   (or: make run)                     ║"
echo "╚══════════════════════════════════════╝"
echo ""
