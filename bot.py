import logging
from flask import Flask, request

# ضبط مستوى تسجيل الرسائل (اللوج)
logging.basicConfig(level=logging.INFO)

# إنشاء تطبيق Flask
app = Flask(__name__)

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    logging.info("Request on /webhook with method %s", request.method)
    # هنا يمكن لاحقًا إضافة منطق البوت أو التعامل مع JSON الوارد من تيليجرام
    return "OK from /webhook"

# ملاحظة هامة:
# لا نستدعي app.run(...) في بيئة Vercel serverless.
# Vercel سيقوم تلقائيًا بتحويل 'app' إلى سيرفر WSGI/ASGI.

# لا يوجد if __name__ == "__main__": لأننا لا نشغل محليًا.
