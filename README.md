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

## Local setup

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd job-pulse-bot

# 2. Install dependencies and initialise the database
make setup

# 3. Copy the example env file and fill in your values
cp .env.example .env
# Edit .env — at minimum set DISCORD_BOT_TOKEN, DISCORD_GUILD_ID,
# and DISCORD_JOBS_CHANNEL_ID

# 4. Start the bot
make run
```

## Running tests

```bash
make test
# or
pytest tests/ -v
```

## Railway deployment

1. Create a new Railway project and link this repo.
2. Add all variables from `.env.example` in the Railway environment variables panel.
3. Railway auto-detects `railway.toml` — the bot starts with `python -m src.bot.main`.

## Slash commands

| Command | Description |
|---------|-------------|
| `/pulse today` | Top 10 jobs scored in the last 24 hours |
| `/pulse search <keyword>` | Search jobs by title, company, or tag |
| `/pipeline status` | Pipeline stats, last run info, and bot uptime |

## Adding a new source

1. Create `src/sources/mysource.py` — subclass `JobSource`, implement `source_name` and `fetch()`.
2. Register it in `src/agents/recon.py`: add `"mysource": MySource` to `SOURCE_REGISTRY`.
3. Add `"mysource"` to `ENABLED_SOURCES` in your `.env`.

## Environment variables reference

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_BOT_TOKEN` | *required* | Discord bot token |
| `DISCORD_GUILD_ID` | *required* | Guild ID for guild-scoped slash commands |
| `DISCORD_JOBS_CHANNEL_ID` | *required* | Channel to post jobs into |
| `DB_PATH` | `jobs.db` | SQLite database file path |
| `POLL_INTERVAL_SECONDS` | `3600` | Seconds between pipeline runs |
| `DEDUP_THRESHOLD` | `85` | Fuzzy match score to treat a job as duplicate |
| `PULSE_POST_THRESHOLD` | `60` | Minimum PULSE score to post a job |
| `PULSE_HOT_THRESHOLD` | `80` | Score above which a job is marked 🔥 HOT |
| `SALARY_MARKET_MEDIAN_USD` | `80000` | Market median used in salary scoring |
| `ENABLED_SOURCES` | `remoteok,arbeitnow` | Comma-separated list of active sources |
| `LOG_LEVEL` | `INFO` | Python logging level |
