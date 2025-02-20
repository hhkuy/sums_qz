import logging
import requests
import json
import random

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
    filters
)

# إعداد اللوج
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -----------------------------
# 1) ضع توكن البوت الخاص بك هنا
# -----------------------------
BOT_TOKEN = "7633072361:AAHnzREYTKKRFiTiq7HDZBalnwnmgivY8_I"

# -----------------------------
# 2) روابط GitHub لجلب الملفات
# -----------------------------
# نفترض أن ملف topics.json موجود في: https://github.com/hhkuy/Sums_Q/blob/main/data/topics.json
# وملفات الأسئلة في مجلد data أيضًا (مثل data/anatomy_of_limbs_lower_limbs.json)
BASE_RAW_URL = "https://raw.githubusercontent.com/hhkuy/Sums_Q/main"

# لاحِظ أننا وضعنا /data/ لأنك ذكرت أن topics.json موجود في مجلد data
TOPICS_JSON_URL = f"{BASE_RAW_URL}/data/topics.json"


# -----------------------------
# 3) دوال لجلب البيانات من GitHub
# -----------------------------
def fetch_topics():
    """جلب ملف الـ topics.json من GitHub على شكل list[dict]."""
    try:
        response = requests.get(TOPICS_JSON_URL)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching topics: {e}")
        return []


def fetch_questions(file_path: str):
    """
    جلب ملف الأسئلة من GitHub بالاعتماد على المسار (file_path) الخاص بالموضوع الفرعي.
    المسار في الـ JSON عادةً مثل: data/anatomy_of_limbs_lower_limbs.json
    """
    # نبني الرابط الكامل
    url = f"{BASE_RAW_URL}/{file_path}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()  # قائمة من القواميس (الأسئلة)
    except Exception as e:
        logger.error(f"Error fetching questions from {url}: {e}")
        return []


# -----------------------------
# 4) مفاتيح لتخزين الحالة في user_data
# -----------------------------
TOPICS_KEY = "topics"
CUR_TOPIC_IDX_KEY = "current_topic_index"
CUR_SUBTOPIC_IDX_KEY = "current_subtopic_index"
NUM_QUESTIONS_KEY = "num_questions"
CURRENT_STATE_KEY = "current_state"
QUESTIONS_KEY = "questions_list"

STATE_SELECT_TOPIC = "select_topic"
STATE_SELECT_SUBTOPIC = "select_subtopic"
STATE_ASK_NUM_QUESTIONS = "ask_num_questions"
STATE_SENDING_QUESTIONS = "sending_questions"


# -----------------------------
# 5) دوال لإنشاء الأزرار (InlineKeyboard)
# -----------------------------
def generate_topics_inline_keyboard(topics_data):
    """
    إنشاء إنلاين كيبورد لقائمة المواضيع.
    """
    keyboard = []
    for i, topic in enumerate(topics_data):
        btn = InlineKeyboardButton(text=topic["topicName"], callback_data=f"topic_{i}")
        keyboard.append([btn])
    return InlineKeyboardMarkup(keyboard)


def generate_subtopics_inline_keyboard(topic, topic_index):
    """
    إنشاء إنلاين كيبورد لقائمة المواضيع الفرعية + زر الرجوع.
    """
    keyboard = []
    subtopics = topic.get("subTopics", [])
    for j, sub in enumerate(subtopics):
        btn = InlineKeyboardButton(
            text=sub["name"],
            callback_data=f"subtopic_{topic_index}_{j}"
        )
        keyboard.append([btn])

    # زر الرجوع لقائمة المواضيع
    back_btn = InlineKeyboardButton("« رجوع للمواضيع", callback_data="go_back_topics")
    keyboard.append([back_btn])
    return InlineKeyboardMarkup(keyboard)


# -----------------------------
# 6) أوامر البوت: /start
# -----------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    هاندلر للأمر /start يعرض قائمة المواضيع.
    """
    topics_data = fetch_topics()
    context.user_data[TOPICS_KEY] = topics_data

    if not topics_data:
        await update.message.reply_text("حدث خطأ في جلب المواضيع من GitHub! تأكد من المسار وصلاحية الوصول.")
        return

    context.user_data[CURRENT_STATE_KEY] = STATE_SELECT_TOPIC
    keyboard = generate_topics_inline_keyboard(topics_data)

    await update.message.reply_text(
        text="مرحبًا بك! اختر الموضوع الرئيسي من القائمة:",
        reply_markup=keyboard
    )


# -----------------------------
# 7) أوامر البوت: /help
# -----------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "الأوامر المتاحة:\n"
        "/start - لبدء اختيار المواضيع\n"
        "/help - عرض هذه الرسالة\n\n"
        "يمكنك أيضًا مناداتي في المجموعات وسيعمل البوت عند الإشارة إليه."
    )
    await update.message.reply_text(help_text)


# -----------------------------
# 8) هاندلر للأزرار (CallbackQuery)
# -----------------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    # ------------------------------------------------------------------------
    # 1) اختيار موضوع رئيسي: data = "topic_{i}"
    # ------------------------------------------------------------------------
    if data.startswith("topic_"):
        _, idx_str = data.split("_")
        topic_index = int(idx_str)
        context.user_data[CUR_TOPIC_IDX_KEY] = topic_index
        context.user_data[CURRENT_STATE_KEY] = STATE_SELECT_SUBTOPIC

        topics_data = context.user_data.get(TOPICS_KEY, [])
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

    # ------------------------------------------------------------------------
    # 2) زر الرجوع لقائمة المواضيع: data = "go_back_topics"
    # ------------------------------------------------------------------------
    elif data == "go_back_topics":
        context.user_data[CURRENT_STATE_KEY] = STATE_SELECT_TOPIC
        topics_data = context.user_data.get(TOPICS_KEY, [])
        keyboard = generate_topics_inline_keyboard(topics_data)
        await query.message.edit_text(
            text="اختر الموضوع الرئيسي من القائمة:",
            reply_markup=keyboard
        )

    # ------------------------------------------------------------------------
    # 3) اختيار موضوع فرعي: data = "subtopic_{topic_index}_{sub_index}"
    # ------------------------------------------------------------------------
    elif data.startswith("subtopic_"):
        _, t_idx_str, s_idx_str = data.split("_")
        t_idx = int(t_idx_str)
        s_idx = int(s_idx_str)
        context.user_data[CUR_TOPIC_IDX_KEY] = t_idx
        context.user_data[CUR_SUBTOPIC_IDX_KEY] = s_idx
        context.user_data[CURRENT_STATE_KEY] = STATE_ASK_NUM_QUESTIONS

        # زر رجوع لقائمة المواضيع الفرعية
        back_btn = InlineKeyboardButton("« رجوع للمواضيع الفرعية", callback_data=f"go_back_subtopics_{t_idx}")
        kb = InlineKeyboardMarkup([[back_btn]])

        await query.message.edit_text(
            text="أدخل عدد الأسئلة المطلوبة (أرسل رقمًا فقط):",
            reply_markup=kb
        )

    # ------------------------------------------------------------------------
    # 4) زر الرجوع لقائمة المواضيع الفرعية: data = "go_back_subtopics_{t_idx}"
    # ------------------------------------------------------------------------
    elif data.startswith("go_back_subtopics_"):
        _, t_idx_str = data.split("_subtopics_")
        t_idx = int(t_idx_str)
        context.user_data[CUR_TOPIC_IDX_KEY] = t_idx
        context.user_data[CURRENT_STATE_KEY] = STATE_SELECT_SUBTOPIC

        topics_data = context.user_data.get(TOPICS_KEY, [])
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


# -----------------------------
# 9) هاندلر استقبال الرسائل النصية (لعدد الأسئلة)
# -----------------------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state = context.user_data.get(CURRENT_STATE_KEY, None)

    if user_state == STATE_ASK_NUM_QUESTIONS:
        text = update.message.text.strip()
        if not text.isdigit():
            await update.message.reply_text("من فضلك أدخل رقمًا صحيحًا.")
            return

        num_q = int(text)
        if num_q <= 0:
            await update.message.reply_text("العدد يجب أن يكون أكبر من صفر.")
            return

        context.user_data[NUM_QUESTIONS_KEY] = num_q
        context.user_data[CURRENT_STATE_KEY] = STATE_SENDING_QUESTIONS

        # جلب المعلومات اللازمة
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

        # لو العدد المطلوب أكبر من عدد الأسئلة، نستخدم جميع الأسئلة
        if num_q > len(questions):
            num_q = len(questions)

        # نختار عشوائيًا (يمكن التبديل إلى الترتيب)
        random.shuffle(questions)
        selected_questions = questions[:num_q]

        # إرسال رسالة تفيد بعدد الأسئلة
        await update.message.reply_text(f"سيتم إرسال {num_q} سؤال(أسئلة) على شكل استفتاء (Quiz). بالتوفيق!")

        # إرسال الأسئلة على شكل Poll (Quiz)
        for idx, q in enumerate(selected_questions, start=1):
            question_text = q.get("question", "لا يوجد نص للسؤال")
            options = q.get("options", [])
            correct_id = q.get("answer", 0)  # انتبه هل هو 0-based أم 1-based

            # إذا كان في ملفاتك answer = 2 مثلاً وتعني الخيار الثالث (أي 0-based = 2)
            # فتأكد أنها متوافقة مع indexing في تيليجرام.
            # هنا نفترض أنها 0-based كما في أمثلتك.

            explanation = q.get("explanation", "")

            # إرسال الاستفتاء
            await context.bot.send_poll(
                chat_id=update.message.chat_id,
                question=f"سؤال {idx}: {question_text}",
                options=options,
                type=Poll.QUIZ,
                correct_option_id=correct_id,
                explanation=explanation,
                is_anonymous=False
            )

        # بعد الإرسال، يمكن إعادة الحالة أو تركها None
        context.user_data[CURRENT_STATE_KEY] = None

    else:
        # أي رسالة أخرى لا نفعل بها شيئًا
        await update.message.reply_text("استخدم /start لاختيار موضوع أو تابع الأزرار.")


# -----------------------------
# 10) دالة main لتشغيل البوت
# -----------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # أوامر
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))

    # أزرار (CallbackQuery)
    app.add_handler(CallbackQueryHandler(callback_handler))

    # رسائل نصية (لعدد الأسئلة)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
