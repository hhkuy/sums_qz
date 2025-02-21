import logging
from flask import Flask, request, Response

# ضبط مستوى اللوج
logging.basicConfig(level=logging.INFO)

# إنشاء تطبيق Flask
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    logging.info("Received a POST request on /webhook.")
    # يمكن لاحقًا إضافة منطق البوت أو التعامل مع JSON
    return Response("OK", status=200)

@app.route("/")
def index():
    return "I'm alive!"

if __name__ == "__main__":
    # تشغيل الخادم محليًا أو على Vercel مع المنفذ 8000
    app.run(host="0.0.0.0", port=8000)
