import os
import json
from datetime import datetime, timedelta, date

from flask import Flask, request, jsonify, session, redirect, url_for, render_template
from functools import wraps

from sqlalchemy import create_engine, text
from slack_sdk import WebClient

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")
engine = create_engine(DATABASE_URL, future=True)

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
slack = WebClient(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# -----------------------------------------------------------------------------
# DB bootstrap
# -----------------------------------------------------------------------------
def ensure_tables():
    with engine.begin() as conn:
        # users
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id              SERIAL PRIMARY KEY,
            slack_user_id   TEXT NOT NULL,
            display_name    TEXT NOT NULL,
            email           TEXT,
            timezone        TEXT DEFAULT 'Europe/London',
            cadence_days    INTEGER DEFAULT 7,
            preferred_hour  INTEGER,
            preferred_dow   INTEGER,
            last_prompt_at  TIMESTAMP,
            next_due_at     TIMESTAMP,
            is_active       BOOLEAN DEFAULT TRUE,
            project         TEXT,
            escalate_to     TEXT
        );
        """))
        if engine.url.get_backend_name().startswith("postgres"):
            # add columns if missing (no-ops if exist)
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'Europe/London';"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS cadence_days INTEGER DEFAULT 7;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_hour INTEGER;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_dow INTEGER;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_prompt_at TIMESTAMP;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS next_due_at TIMESTAMP;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS project TEXT;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS escalate_to TEXT;"))
            # make slack_user_id unique so upserts work
            conn.execute(text("""
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes
                     WHERE schemaname='public' AND indexname='users_slack_user_id_uniq_idx'
                  ) THEN
                    CREATE UNIQUE INDEX users_slack_user_id_uniq_idx ON users(slack_user_id);
                  END IF;
                END $$;
            """))
        # updates
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS updates (
            id             SERIAL PRIMARY KEY,
            user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            prompted_at    TIMESTAMP,
            responded_at   TIMESTAMP,
            progress_pct   INTEGER,
            summary        TEXT,
            blockers       TEXT,
            eta_date       DATE,
            rag            TEXT,
            raw_payload    JSON,
            raw_text       TEXT,
            source         TEXT
        );
        """))

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def admin_required(f):
    @wraps(f)
    def _wrap(*args, **kwargs):
        if not session.get("admin_ok"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return _wrap

def send_prompt_to_user(slack_user_id: str):
    if not slack:
        return
    try:
        slack.chat_postMessage(
            channel=slack_user_id,
            text="👋 Quick project update, please!\n• Progress since last check-in\n• Any blockers\n• ETA/next steps"
        )
    except Exception:
        pass

def find_or_create_user_from_slack(slack_user_id: str) -> int | None:
    """Ensure the user exists in DB; return user_id."""
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM users WHERE slack_user_id = :sid"),
            {"sid": slack_user_id}
        ).first()
        if row:
            return row[0]
        # fallback: create with minimal details
        conn.execute(text("""
            INSERT INTO users (slack_user_id, display_name)
            VALUES (:sid, :name)
            ON CONFLICT (slack_user_id) DO NOTHING
        """), {"sid": slack_user_id, "name": slack_user_id})
        row2 = conn.execute(
            text("SELECT id FROM users WHERE slack_user_id = :sid"),
            {"sid": slack_user_id}
        ).first()
        return row2[0] if row2 else None

# -----------------------------------------------------------------------------
# Public routes
# -----------------------------------------------------------------------------
@app.get("/")
def index():
    return jsonify({"name": "Project Updates Bot", "ok": True, "status": "live"})

# Slack Events: verify & handle DMs (message.im)
@app.route("/slack/events", methods=["GET", "POST"])
def slack_events():
    if request.method == "GET":
        return jsonify({"ok": True})

    body = request.get_json(silent=True) or {}
    # URL verification handshake
    if body.get("type") == "url_verification":
        return jsonify({"challenge": body.get("challenge")})

    # Events API payload
    if body.get("type") == "event_callback":
        event = body.get("event", {})
        # Ignore bot messages & edits
        if event.get("subtype") in {"bot_message", "message_changed", "message_deleted"}:
            return jsonify({"ok": True})

        # Direct message to the bot
        if event.get("type") == "message" and event.get("channel_type") == "im":
            user_id = event.get("user")
            text_in = (event.get("text") or "").strip()
            ts = event.get("ts")
            if user_id and text_in:
                # ensure user exists
                uid = find_or_create_user_from_slack(user_id)
                # store update
                with engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO updates (user_id, responded_at, summary, raw_text, source)
                        VALUES (:uid, NOW(), :summary, :raw, 'dm')
                    """), {"uid": uid, "summary": text_in, "raw": json.dumps(event)})
                # friendly ack (in same DM)
                if slack:
                    try:
                        slack.chat_postMessage(
                            channel=user_id,
                            text="✅ Thanks — noted. I’ll include this in the roll‑up.",
                            thread_ts=ts  # keep tidy in a thread
                        )
                    except Exception:
                        pass
            return jsonify({"ok": True})

        # Optional: channel mentions
        if event.get("type") == "app_mention":
            if slack:
                try:
                    slack.chat_postMessage(
                        channel=event.get("channel"),
                        text="👋 DM me directly for updates, or ask an admin to schedule a chase."
                    )
                except Exception:
                    pass
            return jsonify({"ok": True})

    return jsonify({"ok": True})

# -----------------------------------------------------------------------------
# Admin auth
# -----------------------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if ADMIN_PASSWORD and request.form.get("password") == ADMIN_PASSWORD:
            session["admin_ok"] = True
            return redirect(url_for("admin_users"))
    return render_template("admin_login.html")

@app.get("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

# -----------------------------------------------------------------------------
# Admin: Users
# -----------------------------------------------------------------------------
@app.get("/admin/users")
@admin_required
def admin_users():
    q = (request.args.get("q") or "").strip()
    sql = """
        SELECT
          u.id, u.slack_user_id, u.display_name, u.email, u.timezone,
          u.cadence_days, u.last_prompt_at, u.next_due_at, u.is_active,
          (
            SELECT summary FROM updates
             WHERE user_id = u.id
          ORDER BY responded_at DESC NULLS LAST, id DESC
             LIMIT 1
          ) AS last_summary
        FROM users u
    """
    params = {}
    if q:
        sql += " WHERE u.slack_user_id ILIKE :q OR u.display_name ILIKE :q OR COALESCE(u.email,'') ILIKE :q"
        params["q"] = f"%{q}%"
    sql += " ORDER BY u.display_name NULLS LAST, u.slack_user_id"

    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    return render_template("admin_users.html", rows=rows, q=q)

@app.post("/admin/users/new")
@admin_required
def admin_users_new():
    f = request.form
    slack_user_id = (f.get("slack_user_id") or "").strip()
    if not slack_user_id:
        return redirect(url_for("admin_users"))

    display_name = (f.get("display_name") or "").strip() or slack_user_id
    email        = (f.get("email") or "").strip() or None
    timezone     = (f.get("timezone") or "").strip() or "Europe/London"
    try:
        cadence_days = int(f.get("cadence_days") or 7)
    except ValueError:
        cadence_days = 7

    vals = dict(
        slack_user_id=slack_user_id,
        display_name=display_name,
        email=email,
        timezone=timezone,
        cadence_days=cadence_days,
    )

    with engine.begin() as conn:
        if engine.url.get_backend_name().startswith("postgres"):
            conn.execute(text("""
                INSERT INTO users (slack_user_id, display_name, email, timezone, cadence_days)
                VALUES (:slack_user_id, :display_name, :email, :timezone, :cadence_days)
                ON CONFLICT (slack_user_id) DO UPDATE SET
                  display_name = EXCLUDED.display_name,
                  email        = EXCLUDED.email,
                  timezone     = EXCLUDED.timezone,
                  cadence_days = EXCLUDED.cadence_days;
            """), vals)
        else:
            existing = conn.execute(
                text("SELECT id FROM users WHERE slack_user_id = :sid"),
                {"sid": slack_user_id}
            ).first()
            if existing:
                conn.execute(text("""
                    UPDATE users
                       SET display_name=:display_name,
                           email=:email,
                           timezone=:timezone,
                           cadence_days=:cadence_days
                     WHERE slack_user_id=:slack_user_id
                """), vals)
            else:
                conn.execute(text("""
                    INSERT INTO users (slack_user_id, display_name, email, timezone, cadence_days)
                    VALUES (:slack_user_id, :display_name, :email, :timezone, :cadence_days)
                """), vals)

    return redirect(url_for("admin_users"))

@app.post("/admin/users/<int:user_id>/toggle")
@admin_required
def admin_users_toggle(user_id: int):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE users
               SET is_active = NOT COALESCE(is_active, TRUE)
             WHERE id = :id
        """), {"id": user_id})
    return redirect(url_for("admin_users"))

@app.post("/admin/users/<int:user_id>/chase")
@admin_required
def admin_users_chase(user_id: int):
    with engine.begin() as conn:
        user = conn.execute(
            text("SELECT slack_user_id FROM users WHERE id = :id"),
            {"id": user_id}
        ).mappings().first()
    if user and user.get("slack_user_id"):
        send_prompt_to_user(user["slack_user_id"])
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE users
                   SET last_prompt_at = NOW(),
                       next_due_at    = NOW() + (COALESCE(cadence_days,7) || ' days')::interval
                 WHERE id = :id
            """), {"id": user_id})
    return redirect(url_for("admin_users"))

@app.get("/admin/users/<int:user_id>")
@admin_required
def admin_user_detail(user_id: int):
    with engine.begin() as conn:
        user = conn.execute(
            text("""SELECT id, slack_user_id, display_name, email, timezone,
                           cadence_days, last_prompt_at, next_due_at, is_active
                      FROM users WHERE id = :id"""),
            {"id": user_id}
        ).mappings().first()

        updates = conn.execute(
            text("""SELECT id, prompted_at, responded_at, progress_pct, rag,
                           summary, blockers, eta_date
                      FROM updates
                     WHERE user_id = :id
                  ORDER BY responded_at DESC NULLS LAST, id DESC
                 LIMIT 50"""),
            {"id": user_id}
        ).mappings().all()

    try:
        return render_template("admin_user_detail.html", user=user, updates=updates)
    except Exception:
        return jsonify({"user": dict(user) if user else None, "updates": [dict(u) for u in updates]})

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    ensure_tables()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
