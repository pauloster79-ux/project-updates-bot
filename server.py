# add/replace this whole route in server.py

@app.route("/slack/events", methods=["GET", "POST"])
def slack_events():
    # Slack sometimes probes with GET — keep it simple
    if request.method == "GET":
        return "ok", 200

    # Explicitly handle Slack's URL verification challenge
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    if data.get("type") == "url_verification" and "challenge" in data:
        # Return the raw challenge string as text/plain
        return data["challenge"], 200, {"Content-Type": "text/plain"}

    # For all normal events, pass to Bolt handler
    return handler.handle(request)
