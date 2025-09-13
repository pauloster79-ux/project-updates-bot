import os, json, datetime
from flask import Flask, request, abort
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///data.db"), future=True)
slack_app = App(token=os.getenv("SLACK_BOT_TOKEN"), signing_secret=os.getenv("SLACK_SIGNING_SECRET"))
handler = SlackRequestHandler(slack_app)
app = Flask(__name__)

@slack_app.action("open_update_modal")
def open_modal(ack, body, client):
    ack()
    user_id = json.loads(body["actions"][0]["value"])["user_id"]
    today = datetime.date.today().isoformat()
    client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "submit_update",
            "private_metadata": json.dumps({"user_id": user_id}),
            "title": {"type": "plain_text", "text": "Project Update"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "blocks": [
                {"type": "input", "block_id": "p", "element": {"type": "plain_text_input", "action_id": "progress", "initial_value": "0"}, "label": {"type": "plain_text", "text": "Progress %"}},
                {"type": "input", "block_id": "s", "element": {"type": "plain_text_input", "multiline": True, "action_id": "summary"}, "label": {"type": "plain_text", "text": "What changed?"}},
                {"type": "input", "block_id": "b", "optional": True, "element": {"type": "plain_text_input", "multiline": True, "action_id": "blockers"}, "label": {"type": "plain_text", "text": "Blockers?"}},
                {"type": "input", "block_id": "e", "optional": True, "element": {"type": "plain_text_input", "action_id": "eta", "initial_value": today}, "label": {"type": "plain_text", "text": "ETA (YYYY-MM-DD)"}}
            ]
        }
    )

@slack_app.view("submit_update")
def save_update(ack, body, view):
    ack()
    meta = json.loads(view["private_metadata"])
    user_id = meta["user_id"]
    vals = view["state"]["values"]
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO updates (user_id, prompted_at, responded_at, progress_pct, summary, blockers, eta_date) VALUES (:uid, datetime('now'), datetime('now'), :progress, :summary, :blockers, :eta)"),
            {"uid": user_id, "progress": int(vals['p']['progress']['value']), "summary": vals['s']['summary']['value'], "blockers": vals['b']['blockers']['value'] if 'b' in vals else None, "eta": vals['e']['eta']['value']})

@app.post("/slack/events")
def slack_events(): return handler.handle(request)

@app.post("/slack/interactive")
def slack_interactive(): return handler.handle(request)

@app.get("/cron")
def cron():
    if request.args.get("secret") != os.getenv("CRON_SECRET"): abort(401)
    with engine.begin() as conn:
        users = conn.execute(text("SELECT id, slack_user_id, display_name FROM users WHERE is_active = 1 AND (next_due_at IS NULL OR next_due_at <= CURRENT_TIMESTAMP)")).mappings().all()
        count = 0
        for u in users:
            dm = slack_app.client.conversations_open(users=u["slack_user_id"])
            slack_app.client.chat_postMessage(channel=dm["channel"]["id"], text="Hi " + u["display_name"], blocks=[{
                "type": "section", "text": {"type": "mrkdwn", "text": "Hi *{}*, please provide a quick project update.".format(u["display_name"])}},
                {"type": "actions", "elements": [{
                    "type": "button", "text": {"type": "plain_text", "text": "Update"},
                    "value": json.dumps({"user_id": u["id"]}),
                    "action_id": "open_update_modal"
                }]
            }])
            conn.execute(text("INSERT INTO updates (user_id, prompted_at) VALUES (:uid, datetime('now'))"), {"uid": u["id"]})
            count += 1
    return {"prompted": count}

if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 8000)))
