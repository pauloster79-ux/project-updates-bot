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
    if subtype or event.get("bot_id") or event.get("user") == "USLACKBOT":
        app.logger.info(f"Ignoring bot/system message subtype={subtype}, bot_id={event.get('bot_id')}")
        return ("", 200)
    if channel_type != "im":
        app.logger.info(f"Ignoring non-DM message channel_type={channel_type}")
        return ("", 200)
    if not user_id or not text_in:
        app.logger.info("Missing user or empty text; ignoring")
        return ("", 200)
    
    # Check for retry headers to avoid reprocessing
    if request.headers.get("X-Slack-Retry-Num"):
        app.logger.info("Ignoring retry request")
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
# Project Hub Slack UI
# -----------------------------------------------------------------------------
@app.route("/slack/project-hub", methods=["POST"])
def slack_project_hub():
    """Handle project hub interactions"""
    payload = request.get_json(silent=True) or {}
    app.logger.info(f"/slack/project-hub payload: {payload}")
    
    # Handle different action types
    action_type = payload.get("type")
    
    if action_type == "block_actions":
        # Handle button clicks and interactions
        actions = payload.get("actions", [])
        user_id = payload.get("user", {}).get("id")
        
        for action in actions:
            action_id = action.get("action_id", "")
            value = action.get("value", "")
            
            # Handle project navigation
            if action_id.startswith("nav_open_"):
                project_id = value
                response = build_project_hub_view(user_id, project_id, "summary")
                return jsonify(response)
            
            # Handle tab switching
            elif action_id.startswith("tab_"):
                tab = value
                # Get current state from private_metadata
                view = payload.get("view", {})
                private_metadata = view.get("private_metadata", "{}")
                try:
                    state = json.loads(private_metadata)
                    project_id = state.get("selectedProjectId", "p1")
                except:
                    project_id = "p1"
                
                response = build_project_hub_view(user_id, project_id, tab)
                return jsonify(response)
    
    return jsonify({"ok": True})

def build_project_hub_view(user_id, project_id="p1", active_tab="summary"):
    """Build the project hub home view"""
    # Sample data (in a real app, this would come from your database)
    projects = [
        {"id": "p1", "name": "AI Project Hub", "description": "Slack-native PM hub with Notion-like UI."},
        {"id": "p2", "name": "Website Refresh", "description": "New marketing site & docs."}
    ]
    
    tasks = [
        {
            "id": "t1", "projectId": "p1", "title": "Home view scaffold",
            "status": "In Progress", "priority": "High", "owner": user_id,
            "description": "Build header, nav, tabs, and summary.",
            "dueDate": "2025-10-15", "lastUpdated": "2025-10-10"
        },
        {
            "id": "t2", "projectId": "p1", "title": "Task card component",
            "status": "To Do", "priority": "Medium", "owner": user_id,
            "description": "Reusable builder for task rows/cards.",
            "lastUpdated": "2025-10-10"
        }
    ]
    
    risks = [
        {
            "id": "r1", "projectId": "p1", "title": "Slack rate limits",
            "description": "Rapid view updates might hit rate limits.",
            "likelihood": "Medium", "impact": "High", "owner": user_id,
            "mitigationPlan": "Batch updates; debounce actions.",
            "status": "Open", "lastUpdated": "2025-10-10"
        }
    ]
    
    # Find selected project
    selected_project = next((p for p in projects if p["id"] == project_id), projects[0])
    project_tasks = [t for t in tasks if t["projectId"] == project_id]
    project_risks = [r for r in risks if r["projectId"] == project_id]
    
    # Build the view
    blocks = []
    
    # Project navigation
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "*Projects*"}]
    })
    
    for project in projects:
        blocks.append({
            "type": "section",
            "block_id": f"nav_{project['id']}",
            "text": {
                "type": "mrkdwn",
                "text": f"{'•' if project['id'] == project_id else '◦'} *{project['name']}*"
            },
            "accessory": {
                "type": "button",
                "action_id": f"nav_open_{project['id']}",
                "text": {"type": "plain_text", "text": "Open" if project['id'] == project_id else "View"},
                "value": project['id']
            }
        })
    
    blocks.append({"type": "divider"})
    
    # Header
    blocks.append({
        "type": "section",
        "block_id": "hdr",
        "text": {
            "type": "mrkdwn",
            "text": f"*📘 {selected_project['name']}*\n_Your calm command center_"
        }
    })
    
    blocks.append({"type": "divider"})
    
    # Tabs
    tabs = [
        {"text": "Summary", "value": "summary"},
        {"text": "Tasks", "value": "tasks"},
        {"text": "Risks", "value": "risks"}
    ]
    
    blocks.append({
        "type": "actions",
        "block_id": "tabs",
        "elements": [
            {
                "type": "button",
                "action_id": f"tab_{tab['value']}",
                "text": {"type": "plain_text", "text": tab["text"]},
                "style": "primary" if active_tab == tab["value"] else None,
                "value": tab["value"]
            } for tab in tabs
        ]
    })
    
    blocks.append({"type": "divider"})
    
    # Content based on active tab
    if active_tab == "summary":
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Project Summary*\n{selected_project.get('description', '_No description_')}"
            }
        })
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"*Tasks:* {len(project_tasks)}  •  *Risks:* {len(project_risks)}"}]
        })
    
    elif active_tab == "tasks":
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Tasks*"},
            "accessory": {
                "type": "button",
                "action_id": "task_new",
                "text": {"type": "plain_text", "text": "New Task"}
            }
        })
        blocks.append({"type": "divider"})
        
        if project_tasks:
            for task in project_tasks:
                blocks.append({
                    "type": "section",
                    "block_id": f"task_{task['id']}",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*🗂️ {task['title']}*  _({task['status']} • {task['priority']})_\n{task.get('description', '')}"
                    },
                    "accessory": {
                        "type": "overflow",
                        "action_id": f"task_menu_{task['id']}",
                        "options": [
                            {"text": {"type": "plain_text", "text": "Open"}, "value": f"open_{task['id']}"},
                            {"text": {"type": "plain_text", "text": "Edit"}, "value": f"edit_{task['id']}"},
                            {"text": {"type": "plain_text", "text": "Change status"}, "value": f"status_{task['id']}"},
                            {"text": {"type": "plain_text", "text": "Archive"}, "value": f"archive_{task['id']}"}
                        ]
                    }
                })
                blocks.append({
                    "type": "context",
                    "elements": [{
                        "type": "mrkdwn",
                        "text": f"*Owner:* <@{task['owner']}>  •  *Due:* {task.get('dueDate', '—')}  •  *Updated:* {task['lastUpdated']}"
                    }]
                })
                blocks.append({"type": "divider"})
        else:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*No tasks yet*\n_Add your first task to get rolling._"},
                "accessory": {
                    "type": "button",
                    "action_id": "task_new",
                    "text": {"type": "plain_text", "text": "Add Task"}
                }
            })
    
    elif active_tab == "risks":
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Risks*"},
            "accessory": {
                "type": "button",
                "action_id": "risk_new",
                "text": {"type": "plain_text", "text": "New Risk"}
            }
        })
        blocks.append({"type": "divider"})
        
        if project_risks:
            for risk in project_risks:
                blocks.append({
                    "type": "section",
                    "block_id": f"risk_{risk['id']}",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*⚠️ {risk['title']}*  _({risk['likelihood']} × {risk['impact']})_\n{risk['description']}"
                    },
                    "accessory": {
                        "type": "overflow",
                        "action_id": f"risk_menu_{risk['id']}",
                        "options": [
                            {"text": {"type": "plain_text", "text": "Open"}, "value": f"open_{risk['id']}"},
                            {"text": {"type": "plain_text", "text": "Edit"}, "value": f"edit_{risk['id']}"},
                            {"text": {"type": "plain_text", "text": "Update status"}, "value": f"status_{risk['id']}"},
                            {"text": {"type": "plain_text", "text": "Close risk"}, "value": f"close_{risk['id']}"}
                        ]
                    }
                })
                blocks.append({
                    "type": "context",
                    "elements": [{
                        "type": "mrkdwn",
                        "text": f"*Owner:* <@{risk['owner']}>  •  *Status:* {risk['status']}  •  *Updated:* {risk['lastUpdated']}"
                    }]
                })
                blocks.append({"type": "divider"})
        else:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*No risks captured*\n_Add the first risk to start mitigation planning._"},
                "accessory": {
                    "type": "button",
                    "action_id": "risk_new",
                    "text": {"type": "plain_text", "text": "Add Risk"}
                }
            })
    
    # Build the view response
    state = {
        "selectedProjectId": project_id,
        "activeTab": active_tab
    }
    
    return {
        "type": "home",
        "private_metadata": json.dumps(state),
        "blocks": blocks
    }

@app.route("/slack/project-hub-view")
def project_hub_view():
    """Serve the project hub view for testing"""
    user_id = request.args.get("user_id", "U12345")
    project_id = request.args.get("project_id", "p1")
    active_tab = request.args.get("tab", "summary")
    
    view = build_project_hub_view(user_id, project_id, active_tab)
    return jsonify(view)

@app.route("/slack/project-hub-preview")
def project_hub_preview():
    """Preview the project hub as HTML"""
    user_id = request.args.get("user_id", "U12345")
    project_id = request.args.get("project_id", "p1")
    active_tab = request.args.get("tab", "summary")
    
    view = build_project_hub_view(user_id, project_id, active_tab)
    
    # Convert Block Kit to HTML for preview
    html_blocks = []
    for block in view["blocks"]:
        if block["type"] == "context":
            text = block["elements"][0]["text"]
            html_blocks.append(f'<div class="context">{text}</div>')
        elif block["type"] == "section":
            text = block["text"]["text"]
            html_blocks.append(f'<div class="section">{text}</div>')
        elif block["type"] == "divider":
            html_blocks.append('<div class="divider"></div>')
        elif block["type"] == "actions":
            buttons = []
            for element in block["elements"]:
                style = "primary" if element.get("style") == "primary" else "secondary"
                buttons.append(f'<button class="btn {style}">{element["text"]["text"]}</button>')
            html_blocks.append(f'<div class="actions">{"" .join(buttons)}</div>')
    
    html_content = "\n".join(html_blocks)
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Project Hub Preview</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background: #f8f9fa;
            }}
            .context {{
                color: #666;
                font-size: 14px;
                margin: 10px 0;
                font-weight: 500;
            }}
            .section {{
                background: white;
                padding: 16px;
                margin: 8px 0;
                border-radius: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                line-height: 1.5;
            }}
            .divider {{
                height: 1px;
                background: #e1e5e9;
                margin: 16px 0;
            }}
            .actions {{
                display: flex;
                gap: 8px;
                margin: 16px 0;
            }}
            .btn {{
                padding: 8px 16px;
                border: 1px solid #ddd;
                border-radius: 6px;
                background: white;
                cursor: pointer;
                font-size: 14px;
            }}
            .btn.primary {{
                background: #007bff;
                color: white;
                border-color: #007bff;
            }}
            .btn:hover {{
                background: #f8f9fa;
            }}
            .btn.primary:hover {{
                background: #0056b3;
            }}
            .preview-header {{
                background: white;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }}
            .preview-header h1 {{
                margin: 0 0 10px 0;
                color: #333;
            }}
            .preview-header p {{
                margin: 0;
                color: #666;
            }}
        </style>
    </head>
    <body>
        <div class="preview-header">
            <h1>📘 Project Hub Preview</h1>
            <p>This is how your Slack Block Kit UI will look. The actual UI will be rendered inside Slack.</p>
            <p><strong>Current State:</strong> Project: {project_id}, Tab: {active_tab}</p>
        </div>
        {html_content}
        
        <div class="preview-header" style="margin-top: 40px;">
            <h2>🔗 Test Different Views</h2>
            <p>
                <a href="?project_id=p1&tab=summary">Summary Tab</a> | 
                <a href="?project_id=p1&tab=tasks">Tasks Tab</a> | 
                <a href="?project_id=p1&tab=risks">Risks Tab</a> | 
                <a href="?project_id=p2&tab=summary">Website Refresh Project</a>
            </p>
        </div>
    </body>
    </html>
    """

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
