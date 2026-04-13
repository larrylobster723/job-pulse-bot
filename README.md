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

Before running `make setup`, you need a Discord bot and a server for it to post into. This takes about 10 minutes. Follow each step exactly.

---

### 1a. Create a Discord server

1. Open the Discord app (or go to [discord.com](https://discord.com) in your browser and log in)
2. Look at the left sidebar — you'll see a column of circular server icons. Scroll to the bottom of that column and click the **+** button (it says "Add a Server" when you hover over it)
3. A popup appears. Click **"Create My Own"**
4. Click **"For me and my friends"**
5. Give it a name — e.g. `TechPulse Jobs` — then click **Create**
6. Your new server will appear in the left sidebar. You're now inside it.

**Create the jobs channel:**

7. On the left side of your server you'll see a **"Text Channels"** section with a `#general` channel already there
8. Click the **+** icon that appears when you hover next to "Text Channels"
9. Leave channel type as **"Text Channel"**
10. Name it `jobs` (Discord adds the `#` automatically)
11. Click **Create Channel**

---

### 1b. Create the bot

1. Open a new browser tab and go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Log in with your Discord account if prompted
3. Click the blue **"New Application"** button in the top right
4. In the popup, type the name `TechPulse Bot` and click **Create**
5. You're now on the application settings page. On the **left sidebar**, click **"Bot"**
6. You'll see a section called **"Token"**. Click **"Reset Token"** → click **"Yes, do it!"** to confirm
7. Your bot token appears — it looks like a long string of random characters. **Click "Copy" immediately** — you will not be able to see it again after you leave this page. Paste it somewhere safe (a notes app is fine for now).
8. Scroll down on the same page until you see **"Privileged Gateway Intents"**
9. Find **"Message Content Intent"** and click the toggle to turn it **ON** (it turns green)
10. Click **"Save Changes"** at the bottom of the page

---

### 1c. Invite the bot to your server

1. Still on the Developer Portal, look at the **left sidebar** and click **"OAuth2"**
2. Under OAuth2, click **"URL Generator"** (it appears as a sub-item under OAuth2)
3. You'll see a **"Scopes"** section with checkboxes. Check these two:
   - ✅ `bot`
   - ✅ `applications.commands`
4. A new section called **"Bot Permissions"** will appear below. Check these three:
   - ✅ `Send Messages`
   - ✅ `Embed Links`
   - ✅ `Read Message History`
5. Scroll to the very bottom of the page — you'll see a **"Generated URL"** box with a long link in it. Click **"Copy"**
6. Open a new browser tab, paste the URL into the address bar, and press Enter
7. A Discord authorisation page appears. Click the dropdown under **"Add to Server"** and select your `TechPulse Jobs` server
8. Click **"Continue"** → then **"Authorize"** → complete the CAPTCHA if one appears
9. You'll see a success message. Your bot is now in your server.

---

### 1d. Get your server and channel IDs

To copy IDs in Discord, you first need to enable **Developer Mode**:

1. Click the **gear icon ⚙️** in the bottom-left corner of Discord (next to your username) to open User Settings
2. In the left sidebar, scroll down and click **"Advanced"**
3. Find **"Developer Mode"** and toggle it **ON**
4. Close settings (press Escape or click the X)

**Get the Guild (Server) ID:**

5. Look at the left sidebar — find your `TechPulse Jobs` server icon
6. **Right-click** on the server icon
7. A menu appears at the bottom — click **"Copy Server ID"**
8. Paste it somewhere safe — this is your **Guild ID**

**Get the Channel ID:**

9. In your `TechPulse Jobs` server, look at the left sidebar for the `#jobs` channel you created
10. **Right-click** on `#jobs`
11. In the menu that appears, click **"Copy Channel ID"**
12. Paste it somewhere safe — this is your **Channel ID**

---

You now have three values ready:
- ✅ Bot Token
- ✅ Guild (Server) ID
- ✅ Channel ID

Proceed to Step 2 below.

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
