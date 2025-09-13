# Slack Project Updates Bot

This bot:
- Sends DMs to users asking for project updates
- Collects structured data (progress, blockers, ETA)
- Stores updates in a database (SQLite/Postgres)
- You can trigger prompts manually or via scheduler

---

## 🔧 Setup Instructions

### 1. Slack App Setup

1. Go to https://api.slack.com/apps → **Create New App**
2. Add these **Bot Token Scopes**:
   - `chat:write`
   - `im:write`
   - `users:read`
   - `commands`
3. Enable **Interactivity**:
   - Request URL: `https://YOUR_DOMAIN/slack/interactive`
4. Enable **Event Subscriptions**:
   - Request URL: `https://YOUR_DOMAIN/slack/events`
   - Bot Events: `app_mention`
5. Install the app to your workspace
6. Copy the **Bot Token** and **Signing Secret**

---

### 2. Local Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # then fill it in with your Slack secrets
python -m app.db_init
python -m app.server
```

Then use **ngrok** to expose:
```bash
ngrok http 8000
```

Update Slack with your public ngrok URL + `/slack/events` and `/slack/interactive`

---

### 3. Triggering the bot

To manually trigger DMs to users:
```bash
curl "http://localhost:8000/cron?secret=YOUR_CRON_SECRET"
```

---

### 4. Deployment (Render)

- Upload code to GitHub
- Create **Web Service** on render.com
  - Build: `pip install -r requirements.txt`
  - Start: `gunicorn app.server:app --bind 0.0.0.0:$PORT --workers 2`
- Add environment variables from `.env`
