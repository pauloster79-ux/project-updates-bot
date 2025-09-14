import os
import json
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template, redirect, url_for, session, flash
)
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from slack_bolt import App as SlackBoltApp
from slack_bolt.adapter.flask import SlackRequestHandler

# --- Boot & config ---
load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
CRON_SECRET = os.getenv("CRON_SECRET", "project-updates-secret")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")  # must be set in prod

# Flask must be defined before routes
app = Flask(__name__)
app.secret_key = SECRET_KEY

# DB
engine = create_engine(DATABASE_URL, future=True)

# Slack (Bolt) app + handler
bolt_app = SlackBoltApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
handler = SlackRequestHandler(bolt_app)

# ------------------ Helpers ------------------

def require_admin(f):
    @wraps(f)
    def _wrap(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return _wrap

def auth_ok(req) -> bool:
    auth = req.headers.get("Authorization", "")
    return auth == f"Bearer {CRON_SECRET}"

def now_utc():
    return datetime.utcnow()

# ------------------ Health ------------------

@app.get("/")
def health():
    return {"ok": True, "name": "Project Updates Bot", "status": "live"}, 200

# ------------------ Slack endpoints ------------------

@app.route("/slack/events", methods=["GET", "POST"])
def slack_events():
    if request.method == "GET":
        return "ok", 200
    data = request.get_json(silent=True) or {}
    if data.get("type") == "url_verification" and "challenge" in data:
        return data["challenge"], 200, {"Content-Type": "text/plain"}
    return handler.handle(request)

@app.route("/slack/interactive", methods=["POST"])
def slack_interactive():
    return handler.handle(request)

# ------------------ Bolt actions & views ------------------

@bolt_app.action("open_update_modal")
def open_update_modal(ack, body, client, logger):
    ack()
    try:
        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": "project_update_modal",
                "title": {"type": "plain_text", "text": "Project Update"},
                "submit": {"type": "plain_text", "text": "Submit"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "summary",
                        "element": {"type": "plain_text_input", "action_id": "val", "multiline": True},
                        "label": {"type": "plain_text", "text": "Summary"}
                    },
                    {
                        "type": "input",
                        "block_id": "progress",
                        "element": {"type": "plain_text_input", "action_id": "val"},
                        "label": {"type": "plain_text", "text": "Progress % (0–100)"}
                    },
                    {
                        "type": "input",
                        "block_id": "blockers",
                        "optional": True,
                        "element": {"type": "plain_text_input", "action_id": "val", "multiline": True},
                        "label": {"type": "plain_text", "text": "Blockers"}
                    },
                    {
                        "type": "input",
                        "block_id": "eta",
                        "optional": True,
                        "element": {"type": "plain_text_input", "action_id": "val"},
                        "label": {"type": "plain_text", "text": "ETA date (YYYY-MM-DD)"}
                    },
                    {
                        "type": "input",
                        "block_id": "rag",
                        "optional": True,
                        "element": {
                            "type": "static_select",
                            "action_id": "val",
                            "options": [
                                {"text": {"type": "plain_text", "text": "Green"}, "value": "G"},
                                {"text": {"type": "plain_text", "text": "Amber"}, "value": "A"},
                                {"text": {"type": "plain_text", "text": "Red"}, "value": "R"},
                            ],
                        },
                        "label": {"type": "plain_text", "text": "RAG"}
                    },
                ],
            },
        )
    except Exception as e:
        logger.exception(e)

@bolt_app.view("project_update_modal")
def handle_modal_submission(ack, body, client, logger):
    ack()
    try:
        user_id = body.get("user", {}).get("id")
        state = body.get("view", {}).get("state", {}).get("values", {})

        def read(block_id):
            blk = state.get(block_id, {})
            for _, action in blk.items():
                if isinstance(action, dict):
                    return action.get("value") or action.get("selected_option", {}).get("value")
            return None

        summary = read("summary") or ""
        progress = read("progress")
        blockers = read("blockers") or ""
        eta = read("eta") or None
        rag = read("rag") or None

        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT id FROM users WHERE slack_user_id=:sid"),
                {"sid": user_id},
            ).one_or_none()

            if row is None:
                info = client.users_info(user=user_id)
                display_name = (
                    info.get("user", {})
                    .get("profile", {})
                    .get("display_name")
                    or info.get("user", {}).get("real_name")
                    or user_id
                )
                conn.execute(
                    text("INSERT INTO users (slack_user_id, display_name, timezone, is_active) "
                         "VALUES (:sid, :dn, 'Europe/London', TRUE)"),
                    {"sid": user_id, "dn": display_name},
                )
                row = conn.execute(
                    text("SELECT id FROM users WHERE slack_user_id=:sid"),
                    {"sid": user_id},
                ).one()

            user_pk = row[0]
            pct = int(progress) if (isinstance(progress, str) and progress.isdigit()) else None

            conn.execute(
                text("""
                    INSERT INTO updates
                      (user_id, prompted_at, responded_at, progress_pct, summary, blockers, eta_date, rag, raw_text, source)
                    VALUES
                      (:uid, NOW(), NOW(), :pct, :summary, :blockers, :eta, :rag, :raw, 'slack_dm')
                """),
                {"uid": user_pk, "pct": pct, "summary": summary, "blockers": blockers,
                 "eta": eta, "rag": rag, "raw": json.dumps(state)},
            )

        client.chat_postMessage(channel=user_id, text="✅ Thanks — your update has been recorded.")
    except Exception as e:
        logger.exception(e)

# ------------------ Admin API (cron-compatible) ------------------

@app.post("/admin/users")
def add_user_api():
    # Unchanged API for scripted adds; portal uses HTML forms below.
    if not auth_ok(request):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    data = request.get_json(force=True)
    slack_user_id = data["slack_user_id"]
    display_name = data.get("display_name", slack_user_id)
    email = data.get("email")
    timezone = data.get("timezone", "Europe/London")
    cadence_days = int(data.get("cadence_days", 7))

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO users (slack_user_id, display_name, email, timezone, cadence_days, is_active)
                VALUES (:sid, :name, :email, :tz, :cad, TRUE)
                ON CONFLICT (slack_user_id) DO UPDATE
                SET display_name=EXCLUDED.display_name,
                    email=EXCLUDED.email,
                    timezone=EXCLUDED.timezone,
                    cadence_days=EXCLUDED.cadence_days,
                    is_active=TRUE
            """),
            {"sid": slack_user_id, "name": display_name, "email": email, "tz": timezone, "cad": cadence_days},
        )
    return jsonify({"ok": True})

@app.get("/cron")
def cron():
    if request.args.get("secret") != CRON_SECRET:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    prompted = 0
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT id, slack_user_id, COALESCE(cadence_days, 7)
                FROM users
                WHERE is_active=TRUE
                AND (next_due_at IS NULL OR next_due_at <= NOW())
            """)
        ).all()

        for uid, slack_uid, cadence in rows:
            try:
                bolt_app.client.chat_postMessage(
                    channel=slack_uid,
                    text="⏱️ Quick project update, please.",
                    blocks=[
                        {"type": "section", "text": {"type": "mrkdwn", "text": "*Time for your project update*"}},
                        {"type": "actions", "elements": [
                            {"type": "button", "text": {"type": "plain_text", "text": "Update"}, "action_id": "open_update_modal"}
                        ]},
                    ],
                )
                prompted += 1
                conn.execute(
                    text("UPDATE users SET last_prompt_at=NOW(), next_due_at = NOW() + (:d || ' days')::interval WHERE id=:id"),
                    {"id": uid, "d": cadence},
                )
            except Exception:
                pass
    return jsonify({"ok": True, "prompted": prompted, "at": now_utc().isoformat()})

# ------------------ Admin Web UI ------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pw = request.form.get("password", "")
        if ADMIN_PASSWORD and pw == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Signed in.", "success")
            return redirect(request.args.get("next") or url_for("admin_users"))
        flash("Wrong password.", "error")
    return render_template("admin_login.html")

@app.get("/admin/logout")
def admin_logout():
    session.clear()
    flash("Signed out.", "success")
    return redirect(url_for("admin_login"))

@app.get("/admin")
@require_admin
def admin_root():
    return redirect(url_for("admin_users"))

@app.get("/admin/users")
@require_admin
def admin_users():
    q = request.args.get("q", "").strip()
    sql = """
        SELECT u.id, u.display_name, u.slack_user_id, u.email, u.timezone,
               COALESCE(u.cadence_days, 7) AS cadence_days,
               u.last_prompt_at, u.next_due_at, u.is_active,
               (SELECT rag FROM updates WHERE user_id=u.id ORDER BY responded_at DESC NULLS LAST LIMIT 1) AS last_rag,
               (SELECT summary FROM updates WHERE user_id=u.id ORDER BY responded_at DESC NULLS LAST LIMIT 1) AS last_summary,
               (SELECT responded_at FROM updates WHERE user_id=u.id ORDER BY responded_at DESC NULLS LAST LIMIT 1) AS last_responded_at
        FROM users u
        {where}
        ORDER BY COALESCE(u.next_due_at, NOW() - interval '999 days') ASC, u.display_name ASC
    """
    where = ""
    params = {}
    if q:
        where = "WHERE (LOWER(u.display_name) LIKE :q OR LOWER(u.email) LIKE :q OR u.slack_user_id LIKE :q)"
        params["q"] = f"%{q.lower()}%"
    with engine.begin() as conn:
        rows = conn.execute(text(sql.format(where=where)), params).mappings().all()
    return render_template("admin_users.html", rows=rows, q=q)

@app.post("/admin/users/new")
@require_admin
def admin_users_new():
    form = request.form
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO users (slack_user_id, display_name, email, timezone, cadence_days, is_active)
                    VALUES (:sid, :name, :email, :tz, :cad, TRUE)
                    ON CONFLICT (slack_user_id) DO UPDATE
                      SET display_name=EXCLUDED.display_name,
                          email=EXCLUDED.email,
                          timezone=EXCLUDED.timezone,
                          cadence_days=EXCLUDED.cadence_days,
                          is_active=TRUE
                """),
                {
                    "sid": form["slack_user_id"].strip(),
                    "name": form.get("display_name", "").strip() or form["slack_user_id"].strip(),
                    "email": form.get("email") or None,
                    "tz": form.get("timezone", "Europe/London") or "Europe/London",
                    "cad": int(form.get("cadence_days") or 7),
                },
            )
        flash("User saved.", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("admin_users"))

@app.post("/admin/users/<int:user_id>/toggle")
@require_admin
def admin_users_toggle(user_id: int):
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET is_active = NOT is_active WHERE id=:id"), {"id": user_id})
    flash("Toggled active.", "success")
    return redirect(url_for("admin_users"))

@app.post("/admin/users/<int:user_id>/chase")
@require_admin
def admin_users_chase(user_id: int):
    # Send a DM now and push next_due_at forward by cadence
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT slack_user_id, COALESCE(cadence_days, 7) AS cad FROM users WHERE id=:id"),
            {"id": user_id},
        ).one_or_none()
        if not row:
            flash("User not found.", "error")
            return redirect(url_for("admin_users"))
        slack_uid, cadence = row
        try:
            bolt_app.client.chat_postMessage(
                channel=slack_uid,
                text="⏱️ Quick project update, please.",
                blocks=[
                    {"type": "section", "text": {"type": "mrkdwn", "text": "*Time for your project update*"}},
                    {"type": "actions", "elements": [
                        {"type": "button", "text": {"type": "plain_text", "text": "Update"}, "action_id": "open_update_modal"}
                    ]},
                ],
            )
            conn.execute(
                text("UPDATE users SET last_prompt_at=NOW(), next_due_at = NOW() + (:d || ' days')::interval WHERE id=:id"),
                {"id": user_id, "d": cadence},
            )
            flash("Chase sent.", "success")
        except Exception as e:
            flash(f"Slack error: {e}", "error")
    return redirect(url_for("admin_users"))

@app.get("/admin/users/<int:user_id>")
@require_admin
def admin_user_detail(user_id: int):
    with engine.begin() as conn:
        user = conn.execute(text("SELECT * FROM users WHERE id=:id"), {"id": user_id}).mappings().one()
        updates = conn.execute(
            text("SELECT * FROM updates WHERE user_id=:id ORDER BY responded_at DESC NULLS LAST, prompted_at DESC"),
            {"id": user_id},
        ).mappings().all()
    return render_template("admin_user_detail.html", user=user, updates=updates)

# ------------------ Run (local) ------------------
if __name__ == "__main__":
    # Local dev server; Render uses gunicorn
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=True)
