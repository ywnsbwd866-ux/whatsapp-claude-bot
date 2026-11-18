"""
WhatsApp AI bot using Twilio + Anthropic Claude.

Render settings:
  Build command: pip install -r requirements.txt
  Start command: gunicorn whatsapp_bot:app

Required environment variable:
  ANTHROPIC_API_KEY

After deployment, set the Twilio WhatsApp incoming-message webhook to:
  https://YOUR-RENDER-SERVICE.onrender.com/whatsapp
Use HTTP POST.
"""

import os
import logging

from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    raise RuntimeError(
        "Missing ANTHROPIC_API_KEY. Add it in Render > Environment."
    )

client = anthropic.Anthropic(api_key=api_key)

# Current Claude API model ID (can be changed if needed).
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")

SYSTEM_PROMPT = (
    "You are a helpful WhatsApp assistant replying on behalf of the account owner. "
    "Reply in the same language as the sender. Keep replies concise, friendly, "
    "and clear. Do not claim to be the account owner. If you do not know an answer, "
    "say that the account owner can follow up."
)

# Temporary in-memory conversation history; it resets when the server restarts.
conversations = {}
MAX_MESSAGES = 20


@app.route("/", methods=["GET"])
def health():
    return "WhatsApp bot is running.", 200


@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    sender = request.form.get("From", "").strip()
    incoming_text = request.form.get("Body", "").strip()

    twiml = MessagingResponse()

    if not incoming_text:
        twiml.message("ما وصلتني رسالة نصية. أرسل رسالتك مرة ثانية.")
        return Response(str(twiml), mimetype="application/xml")

    history = conversations.setdefault(sender or "unknown", [])
    history.append({"role": "user", "content": incoming_text})

    # Keep only the latest messages and ensure the first one is a user message.
    if len(history) > MAX_MESSAGES:
        del history[:-MAX_MESSAGES]
    while history and history[0]["role"] != "user":
        history.pop(0)

    try:
        result = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=history,
        )
        answer = "".join(
            block.text for block in result.content
            if getattr(block, "type", None) == "text"
        ).strip()

        if not answer:
            answer = "ما كدرت أجهز جواب هسه، حاول بعد شوي."

        history.append({"role": "assistant", "content": answer})

        # Keep history bounded after adding Claude's reply too.
        if len(history) > MAX_MESSAGES:
            del history[:-MAX_MESSAGES]

    except Exception:
        logger.exception("Claude API request failed")
        if history and history[-1]["role"] == "user":
            history.pop()
        answer = "صار عندي خلل مؤقت، حاول بعد شوي."

    twiml.message(answer)
    return Response(str(twiml), mimetype="application/xml")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
