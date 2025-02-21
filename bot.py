import logging
import requests
import json
import random
import re
import os
import threading

from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Poll
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PollAnswerHandler,
    filters
)

# ---------------------------------------------------------------------
# 1) ضبط نظام اللوج
# ---------------------------------------------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# 2) توكن البوت
# ---------------------------------------------------------------------
# يُفضَّل وضع التوكن في متغير بيئة على Vercel
BOT_TOKEN = "7633072361:AAHnzREYTKKRFiTiq7HDZBalnwnmgivY8_I"

# ---------------------------------------------------------------------
# 3) إعدادات مستودع GitHub لجلب البيانات
# ---------------------------------------------------------------------
BASE_RAW_URL = "https://raw.githubusercontent.com/hhkuy/Sums_Q/main"
TOPICS_JSON_URL = f"{BASE_RAW_URL}/data/topics.json"

# ---------------------------------------------------------------------
# 4) دوال لجلب البيانات من GitHub
# ---------------------------------------------------------------------
def fetch_topics():
    """جلب ملف topics.json من GitHub على شكل list[dict]."""
    try:
        resp = requests.get(TOPICS_JSON_URL)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error fetching topics: {e}")
        return []

def fetch_questions(file_path: str):
    """
    جلب ملف الأسئلة من GitHub بالاعتماد على المسار (file_path) الخاص بالموضوع الفرعي.
    مثال: data/anatomy_of_limbs_lower_limbs.json
    """
    url = f"{BASE_RAW_URL}/{file_path}"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json()  # قائمة من القواميس (الأسئلة)
    except Exception as e:
        logger.error(f"Error fetching questions from {url}: {e}")
        return []

# ---------------------------------------------------------------------
# 5) مفاتيح لتخزين الحالة في user_data و chat_data
# ---------------------------------------------------------------------
TOPICS_KEY = "topics"
CUR_TOPIC_IDX_KEY = "current_topic_index"
CUR_SUBTOPIC_IDX_KEY = "current_subtopic_index"
NUM_QUESTIONS_KEY = "num_questions"
CURRENT_STATE_KEY = "current_state"

STATE_SELECT_TOPIC = "select_topic"
STATE_SELECT_SUBTOPIC = "select_subtopic"
STATE_ASK_NUM_QUESTIONS = "ask_num_questions"
STATE_SENDING_QUESTIONS = "sending_questions"

ACTIVE_QUIZ_KEY = "active_quiz"  # لتخزين بيانات الكويز في chat_data

# ---------------------------------------------------------------------
# 6) دوال لإنشاء أزرار InlineKeyboard
# ---------------------------------------------------------------------
def generate_topics_inline_keyboard(topics_data):
    """إنشاء كيبورد لقائمة المواضيع الرئيسية."""
    keyboard = []
    for i, topic in enumerate(topics_data):
        btn = InlineKeyboardButton(
            text=topic["topicName"],
            callback_data=f"topic_{i}"
        )
        keyboard.append([btn])
    return InlineKeyboardMarkup(keyboard)

def generate_subtopics_inline_keyboard(topic, topic_index):
    """إنشاء كيبورد لقائمة المواضيع الفرعية مع زر الرجوع."""
    keyboard = []
    subtopics = topic.get("subTopics", [])
    for j, sub in enumerate(subtopics):
        btn = InlineKeyboardButton(
            text=sub["name"],
            callback_data=f"subtopic_{topic_index}_{j}"
        )
        keyboard.append([btn])
    back_btn = InlineKeyboardButton("« رجوع للمواضيع", callback_data="go_back_topics")
    keyboard.append([back_btn])
    return InlineKeyboardMarkup(keyboard)

# ---------------------------------------------------------------------
# 7) أوامر البوت: /start
# ---------------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عند تنفيذ /start:
      - جلب قائمة المواضيع من GitHub.
      - عرضها على شكل أزرار.
    """
    topics_data = fetch_topics()
    context.user_data[TOPICS_KEY] = topics_data

    if not topics_data:
        await update.message.reply_text(
            "حدث خطأ في جلب المواضيع من GitHub! تأكد من صلاحية الرابط."
        )
        return

    context.user_data[CURRENT_STATE_KEY] = STATE_SELECT_TOPIC
    keyboard = generate_topics_inline_keyboard(topics_data)
    await update.message.reply_text(
        text="مرحبًا بك! اختر الموضوع الرئيسي من القائمة:",
        reply_markup=keyboard
    )

# ---------------------------------------------------------------------
# 8) أوامر البوت: /help
# ---------------------------------------------------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "الأوامر المتاحة:\n"
        "/start - لبدء اختيار المواضيع\n"
        "/help - عرض هذه الرسالة\n\n"
        "في المجموعات يمكنك تفعيل البوت بكتابة:\n"
        "«بوت سوي اسئلة» أو «بوت الاسئلة» أو «بوت وينك»."
    )
    await update.message.reply_text(help_text)

# ---------------------------------------------------------------------
# 9) هاندلر للأزرار (CallbackQueryHandler)
# ---------------------------------------------------------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_data = context.user_data
    topics_data = user_data.get(TOPICS_KEY, [])

    if data.startswith("topic_"):
        # اختيار موضوع رئيسي
        _, idx_str = data.split("_")
        topic_index = int(idx_str)
        user_data[CUR_TOPIC_IDX_KEY] = topic_index
        user_data[CURRENT_STATE_KEY] = STATE_SELECT_SUBTOPIC

        if topic_index < 0 or topic_index >= len(topics_data):
            await query.message.reply_text("خيار غير صحيح.")
            return

        chosen_topic = topics_data[topic_index]
        subtopics_keyboard = generate_subtopics_inline_keyboard(chosen_topic, topic_index)
        msg_text = (
            f"اختر الموضوع الفرعي لـ: *{chosen_topic['topicName']}*\n\n"
            f"{chosen_topic.get('description', '')}"
        )
        await query.message.edit_text(
            text=msg_text,
            parse_mode="Markdown",
            reply_markup=subtopics_keyboard
        )

    elif data == "go_back_topics":
        # الرجوع لقائمة المواضيع
        user_data[CURRENT_STATE_KEY] = STATE_SELECT_TOPIC
        keyboard = generate_topics_inline_keyboard(topics_data)
        await query.message.edit_text(
            text="اختر الموضوع الرئيسي من القائمة:",
            reply_markup=keyboard
        )

    elif data.startswith("subtopic_"):
        # اختيار موضوع فرعي
        _, t_idx_str, s_idx_str = data.split("_")
        t_idx = int(t_idx_str)
        s_idx = int(s_idx_str)
        user_data[CUR_TOPIC_IDX_KEY] = t_idx
        user_data[CUR_SUBTOPIC_IDX_KEY] = s_idx
        user_data[CURRENT_STATE_KEY] = STATE_ASK_NUM_QUESTIONS

        back_btn = InlineKeyboardButton(
            "« رجوع للمواضيع الفرعية",
            callback_data=f"go_back_subtopics_{t_idx}"
        )
        kb = InlineKeyboardMarkup([[back_btn]])
        await query.message.edit_text(
            text="أدخل عدد الأسئلة المطلوبة (أرسل رقمًا فقط):",
            reply_markup=kb
        )

    elif data.startswith("go_back_subtopics_"):
        # زر الرجوع لقائمة المواضيع الفرعية
        _, t_idx_str = data.split("_subtopics_")
        t_idx = int(t_idx_str)
        user_data[CUR_TOPIC_IDX_KEY] = t_idx
        user_data[CURRENT_STATE_KEY] = STATE_SELECT_SUBTOPIC
        if 0 <= t_idx < len(topics_data):
            chosen_topic = topics_data[t_idx]
            subtopics_keyboard = generate_subtopics_inline_keyboard(chosen_topic, t_idx)
            msg_text = (
                f"اختر الموضوع الفرعي لـ: *{chosen_topic['topicName']}*\n\n"
                f"{chosen_topic.get('description', '')}"
            )
            await query.message.edit_text(
                text=msg_text,
                parse_mode="Markdown",
                reply_markup=subtopics_keyboard
            )
        else:
            await query.message.edit_text("خيار غير صحيح.")
    else:
        await query.message.reply_text("لم أفهم هذا الخيار.")

# ---------------------------------------------------------------------
# 10) هاندلر استقبال الرسائل (لعدد الأسئلة + تريجر في المجموعات)
# ---------------------------------------------------------------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_msg = update.message.text.strip()
    lower_text = text_msg.lower()
    chat_id = update.message.chat_id

    # في المجموعات: إذا احتوى النص على إحدى العبارات، ننفذ /start
    if update.message.chat.type in ("group", "supergroup"):
        triggers = ["بوت سوي اسئلة", "بوت الاسئلة", "بوت وينك"]
        if any(trig.lower() in lower_text for trig in triggers):
            await start_command(update, context)
            return

    user_state = context.user_data.get(CURRENT_STATE_KEY, None)
    if user_state == STATE_ASK_NUM_QUESTIONS:
        # المستخدم أدخل عدد الأسئلة
        if not text_msg.isdigit():
            await update.message.reply_text("من فضلك أدخل رقمًا صحيحًا.")
            return
        num_q = int(text_msg)
        if num_q <= 0:
            await update.message.reply_text("العدد يجب أن يكون أكبر من صفر.")
            return

        topics_data = context.user_data.get(TOPICS_KEY, [])
        t_idx = context.user_data.get(CUR_TOPIC_IDX_KEY, 0)
        s_idx = context.user_data.get(CUR_SUBTOPIC_IDX_KEY, 0)

        if t_idx < 0 or t_idx >= len(topics_data):
            await update.message.reply_text("خطأ في اختيار الموضوع.")
            return

        subtopics = topics_data[t_idx].get("subTopics", [])
        if s_idx < 0 or s_idx >= len(subtopics):
            await update.message.reply_text("خطأ في اختيار الموضوع الفرعي.")
            return

        file_path = subtopics[s_idx]["file"]
        questions = fetch_questions(file_path)
        if not questions:
            await update.message.reply_text("لم أتمكن من جلب أسئلة لهذا الموضوع الفرعي.")
            return

        total_available = len(questions)
        if num_q > total_available:
            await update.message.reply_text(
                f"عدد الأسئلة المتوفرة: {total_available}\n"
                f"لا يمكن تزويدك بـ {num_q} سؤال."
            )
            return

        # عدد الأسئلة مناسب
        context.user_data[NUM_QUESTIONS_KEY] = num_q
        context.user_data[CURRENT_STATE_KEY] = STATE_SENDING_QUESTIONS

        await update.message.reply_text(
            f"سيتم إرسال {num_q} سؤال(أسئلة) على شكل استفتاء (Quiz). بالتوفيق!"
        )

        # تهيئة بيانات الكويز في chat_data
        quiz_data = {
            "poll_ids": [],
            "poll_correct_answers": {},
            "total": num_q,
            "participants": {}  # user_id -> {"answered_count":0, "correct_count":0, "wrong_count":0}
        }
        context.chat_data[ACTIVE_QUIZ_KEY] = quiz_data

        # نختار أسئلة عشوائيًا
        selected_questions = random.sample(questions, num_q)
        for q in selected_questions:
            raw_question = q.get("question", "سؤال بدون نص!")
            # إزالة تنسيقات HTML
            clean_question = re.sub(r"<.*?>", "", raw_question).strip()
            # تنسيق: Question X -> Question X -
            clean_question = re.sub(r"(Question\s*\d+)", r"\1 -", clean_question)

            options = q.get("options", [])
            correct_id = q.get("answer", 0)
            explanation = q.get("explanation", "")

            sent_msg = await context.bot.send_poll(
                chat_id=chat_id,
                question=clean_question,
                options=options,
                type=Poll.QUIZ,
                correct_option_id=correct_id,
                explanation=explanation,
                is_anonymous=False
            )
            if sent_msg.poll:
                pid = sent_msg.poll.id
                quiz_data["poll_ids"].append(pid)
                quiz_data["poll_correct_answers"][pid] = correct_id

        context.user_data[CURRENT_STATE_KEY] = None
    else:
        # أي رسالة أخرى نتجاهلها
        pass

# ---------------------------------------------------------------------
# 11) هاندلر لاستقبال إجابات الاستفتاء (PollAnswerHandler)
# ---------------------------------------------------------------------
async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    poll_answer = update.poll_answer
    user_id = poll_answer.user.id
    poll_id = poll_answer.poll_id
    selected_options = poll_answer.option_ids

    quiz_data = context.chat_data.get(ACTIVE_QUIZ_KEY)
    if not quiz_data or poll_id not in quiz_data["poll_ids"]:
        return

    if len(selected_options) == 1:
        chosen_index = selected_options[0]
        correct_option_id = quiz_data["poll_correct_answers"][poll_id]

        participants = quiz_data["participants"]
        if user_id not in participants:
            participants[user_id] = {
                "answered_count": 0,
                "correct_count": 0,
                "wrong_count": 0
            }
        p_data = participants[user_id]
        p_data["answered_count"] += 1

        if chosen_index == correct_option_id:
            p_data["correct_count"] += 1
        else:
            p_data["wrong_count"] += 1

        # إذا أكمل المستخدم جميع الأسئلة
        if p_data["answered_count"] == quiz_data["total"]:
            correct = p_data["correct_count"]
            wrong = p_data["wrong_count"]
            total = quiz_data["total"]

            user_name = poll_answer.user.full_name
            user_username = poll_answer.user.username
            if user_username:
                mention_text = f"@{user_username}"
            else:
                mention_text = f'<a href="tg://user?id={user_id}">{user_name}</a>'

            result_msg = (
                f"تهانينا {mention_text}!\n"
                f"لقد أكملت الإجابة على {total} سؤال.\n"
                f"الإجابات الصحيحة: {correct}\n"
                f"الإجابات الخاطئة: {wrong}\n"
                f"النتيجة: {correct} / {total}"
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=result_msg,
                parse_mode="HTML"
            )

# ---------------------------------------------------------------------
# 12) إنشاء تطبيق Flask بمسار /ping
# ---------------------------------------------------------------------
flask_app = Flask(__name__)

@flask_app.route("/ping")
def ping():
    # يمكنك عمل Ping على هذا المسار عبر Uptime Robot لإبقاء البوت نشطًا
    return "Bot is alive!"

# ---------------------------------------------------------------------
# 13) تشغيل بوت تيليجرام في Thread + تشغيل Flask
# ---------------------------------------------------------------------
def run_telegram_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(PollAnswerHandler(poll_answer_handler))
    app.run_polling()

if __name__ == "__main__":
    # تشغيل بوت تيليجرام في Thread منفصل
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    # تحديد المنفذ من متغير البيئة أو 8000 افتراضيًا
    port = int(os.environ.get("PORT", 8000))
    flask_app.run(host="0.0.0.0", port=port)
