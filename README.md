# TechPulse Jobs Bot

A Discord bot that polls public job APIs, scores listings with the **PULSE algorithm**, and posts ranked results to a Discord channel automatically.

## What it does

| Stage | Agent | Description |
|-------|-------|-------------|
| 1 | **RECON** | Fetches raw jobs from RemoteOK and Arbeitnow APIs |
| 2 | **DEDUP** | Fuzzy-deduplicates listings; parses salary & location |
| 3 | **PULSE** | Scores each job 0–100 (salary + remote + freshness) |
| 4 | **HERALD** | Posts top-scoring jobs to your Discord channel as rich embeds |

The pipeline runs on a configurable interval (default: every hour). Slash commands let users query jobs on demand.

---

## Step 1 — Discord setup (one-time, manual)

Before running `make setup`, you need a Discord bot and server. This takes about 10 minutes.

### 1a. Create a Discord server
1. Open Discord → click **+** in the left sidebar → **Create My Own** → **For me and my friends**
2. Name it anything (e.g. `TechPulse Jobs`)
3. Create a text channel called `#jobs`

### 1b. Create the bot
1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** → name it `TechPulse Bot` → Create
3. Left sidebar → **Bot**
4. Click **Reset Token** → copy it (you only see it once — save it)
5. Under **Privileged Gateway Intents**, enable **Message Content Intent** ✅

### 1c. Invite the bot to your server
1. Left sidebar → **OAuth2** → **URL Generator**
2. Scopes: check `bot` and `applications.commands`
3. Bot Permissions: check `Send Messages`, `Embed Links`, `Read Message History`
4. Copy the generated URL → open in browser → select your server → Authorize

### 1d. Get your IDs
Enable Developer Mode first: Discord Settings → Advanced → Developer Mode ✅

- **Guild (Server) ID** — right-click your server name → Copy Server ID
- **Channel ID** — right-click `#jobs` → Copy Channel ID

---

## Step 2 — Run setup

```bash
git clone https://github.com/larrylobster723/job-pulse-bot.git
cd job-pulse-bot
make setup
```

`make setup` will:
- Check for Python 3.11+
- Create a virtual environment
- Install all dependencies
- Prompt you for your bot token, guild ID, and channel ID
- Create `.env` automatically
- Initialise the SQLite database
- Verify your bot token is valid

---

## Step 3 — Start the bot

```bash
make run
```

The bot will:
1. Connect to Discord
2. Register slash commands in your server (instant — guild-scoped)
3. Run the full pipeline immediately (RECON → DEDUP → PULSE → HERALD)
4. Continue running on a 1-hour schedule

---

## Running tests

```bash
make test
```

---

## Slash commands

| Command | Description |
|---------|-------------|
| `/pulse today` | Top 10 jobs scored in the last 24 hours |
| `/pulse search <keyword>` | Search jobs by title, company, or tag |
| `/pipeline status` | Pipeline stats, last run info, and bot uptime |

---

## Railway deployment

1. Create a new Railway project and link this repo
2. Add these environment variables in Railway's Variables panel (same values as your `.env`):
   - `DISCORD_BOT_TOKEN`
   - `DISCORD_GUILD_ID`
   - `DISCORD_JOBS_CHANNEL_ID`
   - Any optional variables you want to override (see table below)
3. Railway auto-detects `railway.toml` — the bot starts automatically

> ⚠️ Railway's free tier sleeps after inactivity. Use the **Hobby plan (~$5/month)** or [Render](https://render.com) free tier for 24/7 uptime.

---

## Adding a new job source

1. Create `src/sources/mysource.py` — subclass `JobSource`, implement `source_name` and `fetch()`
2. Register it in `src/agents/recon.py`: add `"mysource": MySource` to `SOURCE_REGISTRY`
3. Add `"mysource"` to `ENABLED_SOURCES` in your `.env`

That's it — RECON picks it up automatically on next run.

---

## Extending PULSE scoring

Edit `src/agents/pulse.py` → `compute_pulse_score()`. The function is pure (no DB calls) and fully tested. Each factor is clearly separated — add, remove, or reweight as needed. Run `make test` after changes.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_BOT_TOKEN` | *required* | Discord bot token |
| `DISCORD_GUILD_ID` | *required* | Guild ID for slash command registration |
| `DISCORD_JOBS_CHANNEL_ID` | *required* | Channel to post jobs into |
| `DB_PATH` | `jobs.db` | SQLite database file path |
| `POLL_INTERVAL_SECONDS` | `3600` | Seconds between pipeline runs |
| `DEDUP_THRESHOLD` | `85` | Fuzzy match score to treat a job as duplicate (0–100) |
| `PULSE_POST_THRESHOLD` | `60` | Minimum PULSE score to post a job |
| `PULSE_HOT_THRESHOLD` | `80` | Score above which a job is marked 🔥 HOT |
| `SALARY_MARKET_MEDIAN_USD` | `80000` | Market median used in salary scoring |
| `ENABLED_SOURCES` | `remoteok,arbeitnow` | Comma-separated list of active sources |
| `LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
