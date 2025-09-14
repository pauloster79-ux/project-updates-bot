import os
import json
from datetime import datetime, timedelta, date

from flask import (
    Flask, request, jsonify, session, redirect, url_for, render_template
)
from functools import wraps

from sqlalchemy import create_engine, text
from slack_sdk import WebClient


# -----------------------------------------------------------------------------
# App & config
# -----------------------------------------------------------------------------
app = Flask(__name__)

# Required env vars you should have set in Render:
#   SLACK_BOT_TOKEN        -> xoxb-...
#   SECRET_KEY             -> any long random string (for Flask sessions)
#   ADMIN_PASSWORD         -> the password you use at /admin/login
#   DATABASE_URL           -> Render Postgres URL (or we'll fall back to SQLite)
app.secret_key = os.getenv("SECRET_KEY", "change-me")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")
engine = create_engine(DATABASE_URL, future=True)

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")  # optional for "Chase now"
slack = WebClient(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None


# -----------------------------------------------------------------------------
# Small helpers
# -----------------------------------------------------------------------------
def admin_required(f):
    @wraps(f)
    def _wrap(*args, **kwargs):
        if not session.get("admin_ok"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return _wrap


def ensure_tables():
    """
    Safe to run repeatedly. For Postgres we also add columns that might be
    missing if you created tables earlier.
    """
    with engine.begin() as conn:
        # USERS
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id              SERIAL PRIMARY KEY,
            slack_user_id   TEXT UNIQUE NOT NULL,
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

        # Add missing columns if needed (Postgres)
        if engine.url.get_backend_name().startswith("postgres"):
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'Europe/London';"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS cadence_days INTEGER DEFAULT 7;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_hour INTEGER;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_dow INTEGER;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_prompt_at TIMESTAMP;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS next_due_at TIMESTAMP;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS project TEXT;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS escalate_to TEXT;"))

        # UPDATES (optional history)
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


def send_prompt_to_user(slack_user_id: str):
    """
    Minimal 'chase now' DM. Requires SLACK_BOT_TOKEN.
    You can replace this with your modal logic later.
    """
    if not slack:
        return

    try:
        slack.chat_postMessage(
            channel=slack_user_id,
            text="👋 Quick project update, please!\n• Progress since last check-in\n• Any blockers\n• ETA/next steps"
        )
    except Exception:
        # Ignore errors to avoid breaking admin UI
        pass


# -----------------------------------------------------------------------------
# Public routes
# -----------------------------------------------------------------------------
@app.get("/")
def index():
    return jsonify({"name": "Project Updates Bot", "ok": True, "status": "live"})


@app.route("/slack/events", methods=["GET", "POST"])
def slack_events():
    """
    Keeps Slack Event Subscriptions happy.
    - GET → simple OK
    - POST:
        * url_verification → echo challenge
        * everything else → 200 (no-op for now)
    """
    if request.method == "GET":
        return jsonify({"ok": True})

    body = request.get_json(silent=True) or {}
    if body.get("type") == "url_verification":
        return jsonify({"challenge": body.get("challenge")})
    # TODO: handle app_mention / message events if you want
    return jsonify({"ok": True})


# -----------------------------------------------------------------------------
# Admin auth
# -----------------------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    admin_pw = os.getenv("ADMIN_PASSWORD", "")
    if request.method == "POST":
        if admin_pw and request.form.get("password") == admin_pw:
            session["admin_ok"] = True
            return redirect(url_for("admin_users"))
    return render_template("admin_login.html")


@app.get("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# -----------------------------------------------------------------------------
# Admin: Users (list, create/update, toggle, chase, detail)
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
            # SQLite fallback
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
        # update last_prompt_at / next_due_at
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

    # Fallback page if you haven’t created admin_user_detail.html yet
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
