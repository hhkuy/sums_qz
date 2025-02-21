import logging
from flask import Flask, request

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    logging.info("Request on /webhook with method %s", request.method)
    return "OK from /webhook"

@app.route("/")
def index():
    return "I'm alive!"

# لا نستدعي app.run() في Vercel، فهي تعمل بأسلوب Serverless.
# إذا أردت منطق بوت تيليجرام أو غيره، أضفه هنا لاحقًا.
