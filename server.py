import os
import json
from datetime import datetime, timedelta

from flask import Flask, request, jsonify
from dotenv import load_dotenv

from sqlalchemy import create_engine, text

from slack_bolt import App as SlackBoltApp
from slack_bolt.adapter.flask import SlackRequestHandler

# --- Boot ---
load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
CRON_SECRET = os.getenv("CRON_SECRET", "project-updates-secret")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")

# Flask app (must be defined before @app.route usage)
app = Flask(__name__)

# DB
engine = create_engine(DATABASE_URL, future=True)

# Slack (Bolt) app
bolt_app = SlackBoltApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
handler = SlackRequestHandler(bolt_app)


# ---------- Health ----------
@app.get("/")
def health():
    return {"ok": True, "name": "Project Updates Bot", "status": "live"}, 200


# ---------- Slack endpoints ----------
@app.route("/slack/events", methods=["GET", "POST"])
def slack_events():
    # Slack sometimes probes with GET
    if request.method == "GET":
        return "ok", 200

    # URL verification challenge
    data = request.get_json(silent=True) or {}
    if data.get("type") == "url_verification" and "challenge" in data:
        return data["challenge"], 200, {"Content-Type": "text/plain"}

    # Normal events → hand to Bolt
    return handler.handle(request)


@app.route("/slack/interactive", methods=["POST"])
def slack_interactive():
    return handler.handle(request)


# ---------- Bolt actions & views ----------
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
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "val",
                            "multiline": True,
                            "placeholder": {"type": "plain_text", "text": "What happened since last time?"}
                        },
                        "label": {"type": "plain_text", "text": "Summary"}
                    },
                    {
                        "type": "input",
                        "block_id": "progress",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "val",
                            "placeholder": {"type": "plain_text", "text": "0-100"}
                        },
                        "label": {"type": "plain_text", "text": "Progress %"}
                    },
                    {
                        "type": "input",
                        "block_id": "blockers",
                        "optional": True,
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "val",
                            "multiline": True,
                            "placeholder": {"type": "plain_text", "text": "Any blockers?"}
                        },
                        "label": {"type": "plain_text", "text": "Blockers"}
                    },
                    {
                        "type": "input",
                        "block_id": "eta",
                        "optional": True,
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "val",
                            "placeholder": {"type": "plain_text", "text": "YYYY-MM-DD"}
                        },
                        "label": {"type": "plain_text", "text": "ETA date"}
                    },
                    {
                        "type": "input",
                        "block_id": "rag",
                        "optional": True,
                        "element": {
                            "type": "static_select",
                            "action_id": "val",
                            "placeholder": {"type": "plain_text", "text": "Choose"},
                            "options": [
                                {"text": {"type": "plain_text", "text": "Green"}, "value": "G"},
                                {"text": {"type": "plain_text", "text": "Amber"}, "value": "A"},
                                {"text": {"type": "plain_text", "text": "Red"}, "value": "R"},
                            ],
                        },
                        "label": {"type": "plain_text", "text": "RAG"}
                    },
                ]
            }
        )
    except Exception as e:
        logger.exception(e)


@bolt_app.view("project_update_modal")
def handle_modal_submission(ack, body, client, logger):
    ack()
    try:
        user_id = body.get("user", {}).get("id")
        state = body.get("view", {}).get("state", {}).get("values", {})

        def v(block_id):
            block = state.get(block_id, {})
            # pull action value regardless of input type
            if "val" in block:
                action = block["val"]
                if isinstance(action, dict):
                    return action.get("value") or action.get("selected_option", {}).get("value")
            for key, action in block.items():
                if isinstance(action, dict):
                    return action.get("value") or action.get("selected_option", {}).get("value")
            return None

        summary = v("summary") or ""
        progress = v("progress") or None
        blockers = v("blockers") or ""
        eta = v("eta") or None
        rag = v("rag") or None

        with engine.begin() as conn:
            # ensure user exists
            row = conn.execute(
                text("SELECT id FROM users WHERE slack_user_id=:sid"),
                {"sid": user_id}
            ).one_or_none()
            if row is None:
                # best-effort display name
                profile = client.users_info(user=user_id)
                display_name = (
                    profile.get("user", {})
                    .get("profile", {})
                    .get("display_name") or profile.get("user", {}).get("real_name") or user_id
                )
                conn.execute(
                    text(
                        "INSERT INTO users (slack_user_id, display_name, email, timezone) "
                        "VALUES (:sid, :dn, NULL, 'Europe/London')"
                    ),
                    {"sid": user_id, "dn": display_name},
                )
                row = conn.execute(
                    text("SELECT id FROM users WHERE slack_user_id=:sid"),
                    {"sid": user_id},
                ).one()
            user_pk = row[0]

            conn.execute(
                text(
                    """
                    INSERT INTO updates
                      (user_id, prompted_at, responded_at, progress_pct, summary, blockers, eta_date, rag, raw_text, source)
                    VALUES
                      (:uid, NOW(), NOW(), :pct, :summary, :blockers, :eta, :rag, :raw, 'slack_dm')
                    """
                ),
                {
                    "uid": user_pk,
                    "pct": int(progress) if (isinstance(progress, str) and progress.isdigit()) else None,
                    "summary": summary,
                    "blockers": blockers,
                    "eta": eta,
                    "rag": rag,
                    "raw": json.dumps(state),
                },
            )

        client.chat_postMessage(channel=user_id, text="✅ Thanks — your update has been recorded.")
    except Exception as e:
        logger.exception(e)


# ---------- Admin & Cron ----------
def auth_ok(request) -> bool:
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {CRON_SECRET}"


@app.post("/admin/users")
def add_user():
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
            text(
                """
                INSERT INTO users (slack_user_id, display_name, email, timezone, cadence_days, is_active)
                VALUES (:sid, :name, :email, :tz, :cad, TRUE)
                ON CONFLICT (slack_user_id) DO UPDATE
                  SET display_name = EXCLUDED.display_name,
                      email = EXCLUDED.email,
                      timezone = EXCLUDED.timezone,
                      cadence_days = EXCLUDED.cadence_days,
                      is_active = TRUE
                """
            ),
            {"sid": slack_user_id, "name": display_name, "email": email, "tz": timezone, "cad": cadence_days},
        )

    return jsonify({"ok": True})


@app.get("/cron")
def cron():
    # ?secret=...
    if request.args.get("secret") != CRON_SECRET:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    now = datetime.utcnow()
    prompted = 0

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, slack_user_id, cadence_days
                FROM users
                WHERE is_active = TRUE
                  AND (next_due_at IS NULL OR next_due_at <= NOW())
                """
            )
        ).all()

        for uid, slack_uid, cadence in rows:
            try:
                bolt_app.client.chat_postMessage(
                    channel=slack_uid,
                    text="⏱️ Quick project update, please.",
                    blocks=[
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": "*Time for your project update*"},
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "Update"},
                                    "action_id": "open_update_modal",
                                }
                            ],
                        },
                    ],
                )
                prompted += 1
                conn.execute(
                    text(
                        "UPDATE users SET last_prompt_at = NOW(), next_due_at = NOW() + (:d || ' days')::interval WHERE id=:id"
                    ),
                    {"id": uid, "d": cadence or 7},
                )
            except Exception:
                # don't crash cron if a DM fails
                pass

    return jsonify({"ok": True, "prompted": prompted, "at": now.isoformat()})

