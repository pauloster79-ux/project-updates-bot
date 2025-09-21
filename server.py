import os
import json
from datetime import datetime, timedelta, date

from flask import Flask, request, jsonify, session, redirect, url_for, render_template
from functools import wraps
from sqlalchemy import create_engine, text
from slack_sdk import WebClient

# -----------------------------------------------------------------------------
# App & Config
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")
engine = create_engine(DATABASE_URL, future=True)

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
slack = WebClient(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# -----------------------------------------------------------------------------
# Bootstrap DB (idempotent)
# -----------------------------------------------------------------------------
def ensure_tables():
    with engine.begin() as conn:
        # users table
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
        # make slack_user_id unique (needed for upsert)
        if engine.url.get_backend_name().startswith("postgres"):
            conn.execute(text("""
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1
                      FROM pg_indexes
                     WHERE schemaname='public'
                       AND indexname='users_slack_user_id_uniq_idx'
                  ) THEN
                    CREATE UNIQUE INDEX users_slack_user_id_uniq_idx
                      ON users(slack_user_id);
                  END IF;
                END $$;
            """))

        # updates table (history of user replies)
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
        
        # Make prompted_at nullable if it's not already (for existing databases)
        if engine.url.get_backend_name().startswith("postgres"):
            try:
                conn.execute(text("ALTER TABLE updates ALTER COLUMN prompted_at DROP NOT NULL;"))
                app.logger.info("Successfully made prompted_at nullable")
            except Exception as e:
                app.logger.warning(f"Could not make prompted_at nullable: {e}")
        else:
            # For SQLite, the column is already nullable by default
            pass

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
    """Minimal 'chase now' DM."""
    if not slack:
        app.logger.warning("SLACK_BOT_TOKEN not set; cannot DM")
        return
    try:
        slack.chat_postMessage(
            channel=slack_user_id,
            text="👋 Quick project update, please!\n• Progress since last check-in\n• Any blockers\n• ETA/next steps"
        )
        app.logger.info(f"Sent chase DM to {slack_user_id}")
    except Exception as e:
        app.logger.exception(f"Failed to DM {slack_user_id}: {e}")

def find_or_create_user(slack_user_id: str) -> int | None:
    """Return users.id for a slack_user_id (create if missing)."""
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM users WHERE slack_user_id = :sid"),
            {"sid": slack_user_id}
        ).first()
        if row:
            return row[0]
        # create minimal record
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

# --- Slack Events endpoint (handles URL verification + DM messages) ---
@app.route("/slack/events", methods=["GET", "POST"])
def slack_events():
    # Slack sometimes probes with GET; answer 200
    if request.method == "GET":
        return jsonify({"ok": True})

    payload = request.get_json(silent=True) or {}
    app.logger.info(f"/slack/events payload: {payload}")

    # 1) URL verification challenge
    if payload.get("type") == "url_verification":
        return jsonify({"challenge": payload.get("challenge")})

    # 2) Only process event callbacks
    if payload.get("type") != "event_callback":
        return ("", 200)

    event = payload.get("event", {}) or {}
    etype = event.get("type")
    subtype = event.get("subtype")
    channel_type = event.get("channel_type")
    user_id = event.get("user")
    text_in = (event.get("text") or "").strip()
    ts = event.get("ts")

    # Ignore non-message events, bot/system messages, non-DMs, empties
    if etype != "message":
        app.logger.info(f"Ignoring non-message event: {etype}")
        return ("", 200)
    if subtype:
        app.logger.info(f"Ignoring message with subtype={subtype}")
        return ("", 200)
    if channel_type != "im":
        app.logger.info(f"Ignoring non-DM message channel_type={channel_type}")
        return ("", 200)
    if not user_id or not text_in:
        app.logger.info("Missing user or empty text; ignoring")
        return ("", 200)

    app.logger.info(f"DM from {user_id}: {text_in}")

    # Ensure user exists; write an updates row; (admin table shows last_summary via subquery)
    try:
        uid = find_or_create_user(user_id)
        if uid is None:
            app.logger.error(f"Could not resolve/create user for {user_id}")
            return ("", 200)
        with engine.begin() as conn:
            # Try the new format first, fall back to old format if needed
            try:
                conn.execute(text("""
                    INSERT INTO updates (user_id, prompted_at, responded_at, summary, raw_payload, raw_text, source)
                    VALUES (:uid, NOW(), NOW(), :summary, :payload, :raw_text, 'dm')
                """), {
                    "uid": uid,
                    "summary": text_in,
                    "payload": json.dumps(payload),
                    "raw_text": text_in
                })
            except Exception as e:
                # Fallback to old format if prompted_at column doesn't exist or has constraints
                app.logger.warning(f"New format failed, trying old format: {e}")
                conn.execute(text("""
                    INSERT INTO updates (user_id, responded_at, summary, raw_payload, raw_text, source)
                    VALUES (:uid, NOW(), :summary, :payload, :raw_text, 'dm')
                """), {
                    "uid": uid,
                    "summary": text_in,
                    "payload": json.dumps(payload),
                    "raw_text": text_in
                })
        app.logger.info(f"Saved update row for {user_id} (user_id={uid})")
    except Exception as e:
        app.logger.exception(f"DB insert failed for DM {user_id}: {e}")

    # Optional friendly ack in a thread
    if slack and ts:
        try:
            slack.chat_postMessage(
                channel=user_id,
                text="✅ Thanks — noted. I’ll include this in the roll‑up.",
                thread_ts=ts
            )
        except Exception as e:
            app.logger.warning(f"Ack DM failed for {user_id}: {e}")

    return ("", 200)

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
# Admin: Users pages
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
          ORDER BY 
            CASE WHEN responded_at IS NULL THEN 0 ELSE 1 END DESC,
            responded_at DESC, 
            id DESC
             LIMIT 1
          ) AS last_summary
        FROM users u
    """
    params = {}
    if q:
        if engine.url.get_backend_name().startswith("postgres"):
            sql += " WHERE u.slack_user_id ILIKE :q OR u.display_name ILIKE :q OR COALESCE(u.email,'') ILIKE :q"
        else:
            sql += " WHERE LOWER(u.slack_user_id) LIKE LOWER(:q) OR LOWER(u.display_name) LIKE LOWER(:q) OR LOWER(COALESCE(u.email,'')) LIKE LOWER(:q)"
        params["q"] = f"%{q}%"
    if engine.url.get_backend_name().startswith("postgres"):
        sql += " ORDER BY u.display_name NULLS LAST, u.slack_user_id"
    else:
        sql += " ORDER BY COALESCE(u.display_name, '') DESC, u.slack_user_id"

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
# Entrypoint (only for local dev; Render runs gunicorn via start command)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    ensure_tables()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
