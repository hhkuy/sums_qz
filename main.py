import logging
import requests
import json
import random

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Poll,
    PollOption,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ===================================================
# 1) إعدادات وتسجيل لوج
# ===================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# ===================================================
# 2) روابط GitHub لسحب الملفات (topics.json وملفات الأسئلة)
# ===================================================
# مستودع الأمثلة الذي ذكرتَه:
BASE_RAW_URL = "https://raw.githubusercontent.com/hhkuy/Sums_Q/main"  # رابط المستودع الأساسي (يمكن تعديله حسب الفرع/folder)

TOPICS_JSON_URL = f"{BASE_RAW_URL}/topics.json"
# ملاحظة: ملف الـ JSON "topics.json" موجود في جذر المجلد حسب ما ذُكر في الرابط:
# https://github.com/hhkuy/Sums_Q/blob/main/topics.json
#
# وعند تحميل ملفات الأسئلة، يجب أن نستخدم المسار (file) الموجود في السجل
# مثلا: data/anatomy_of_limbs_upper_limbs.json -> BASE_RAW_URL + "/" + "data/anatomy_of_limbs_upper_limbs.json"

# ===================================================
# 3) دوال جلب البيانات من GitHub
# ===================================================
def fetch_topics():
    """
    جلب ملف الـ topics.json من مستودع GitHub على شكل list[dict].
    """
    try:
        response = requests.get(TOPICS_JSON_URL)
        response.raise_for_status()
        return response.json()  # قائمة القواميس
    except Exception as e:
        logger.error(f"Error fetching topics: {e}")
        return []


def fetch_questions(file_path: str):
    """
    جلب ملف الأسئلة من GitHub بالاعتماد على المسار (file_path) الخاص بالموضوع الفرعي.
    يعيد List[dict] من الأسئلة.
    """
    url = f"{BASE_RAW_URL}/{file_path}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()  # قائمة الأسئلة
    except Exception as e:
        logger.error(f"Error fetching questions from {url}: {e}")
        return []

# ===================================================
# 4) القوائم الرئيسية وحالة السياق
# ===================================================
# سنحتفظ ببعض المعلومات في context.user_data لكي نستطيع التنقل بـ زر الرجوع
# - current_topic_index: اندكس الموضوع الحالي
# - current_subtopic_index: اندكس الموضوع الفرعي
# - topics: قائمة المواضيع كاملة
# - subtopics: قائمة المواضيع الفرعية للموضوع المختار
# - questions_list: قائمة الأسئلة الخاصة بالموضوع الفرعي المختار
# - num_questions: عدد الأسئلة التي سيختبر بها المستخدم

# المفاتيح الرئيسية في user_data
TOPICS_KEY = "topics"
CUR_TOPIC_IDX_KEY = "current_topic_index"
CUR_SUBTOPIC_IDX_KEY = "current_subtopic_index"
NUM_QUESTIONS_KEY = "num_questions"
CURRENT_STATE_KEY = "current_state"
QUESTIONS_KEY = "questions_list"

# سنعرّف بعض الـ States (بشكل نصي بسيط)
STATE_SELECT_TOPIC = "select_topic"
STATE_SELECT_SUBTOPIC = "select_subtopic"
STATE_ASK_NUM_QUESTIONS = "ask_num_questions"
STATE_SENDING_QUESTIONS = "sending_questions"

# ===================================================
# 5) دوال المساعدة لإنشاء الأزرار
# ===================================================
def generate_topics_inline_keyboard(topics_data):
    """
    إنشاء إنلاين كيبورد لقائمة المواضيع.
    """
    keyboard = []
    for i, topic in enumerate(topics_data):
        btn = InlineKeyboardButton(text=topic["topicName"], callback_data=f"topic_{i}")
        keyboard.append([btn])
    # لا حاجة لزر الرجوع هنا لأن /start هو أعلى شيء
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


# ===================================================
# 6) هاندلرز الأوامر الرئيسية
# ===================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    هاندلر للأمر /start يعرض قائمة المواضيع.
    """
    # جلب قائمة المواضيع وتخزينها في user_data (مرة واحدة)
    topics_data = fetch_topics()
    context.user_data[TOPICS_KEY] = topics_data

    if not topics_data:
        await update.message.reply_text("حدث خطأ في جلب المواضيع من GitHub!")
        return

    context.user_data[CURRENT_STATE_KEY] = STATE_SELECT_TOPIC
    keyboard = generate_topics_inline_keyboard(topics_data)

    await update.message.reply_text(
        text="مرحبًا بك! اختر الموضوع الرئيسي من القائمة:",
        reply_markup=keyboard
    )


# ===================================================
# 7) هاندلر للـ CallbackQuery (الأزرار)
# ===================================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # لمنع ظهور الـ 'loading...'

    data = query.data

    # ------------------------------------------------------------------------
    # إذا كانت الصيغة "topic_{i}" => يعني اختار موضوع رئيسي
    # ------------------------------------------------------------------------
    if data.startswith("topic_"):
        # مثال: data = "topic_3"
        _, idx_str = data.split("_")
        topic_index = int(idx_str)
        context.user_data[CUR_TOPIC_IDX_KEY] = topic_index
        context.user_data[CURRENT_STATE_KEY] = STATE_SELECT_SUBTOPIC

        topics_data = context.user_data.get(TOPICS_KEY, [])
        if topic_index < 0 or topic_index >= len(topics_data):
            await query.message.reply_text("خيار غير صحيح.")
            return

        chosen_topic = topics_data[topic_index]
        # عرض المواضيع الفرعية
        subtopics_keyboard = generate_subtopics_inline_keyboard(chosen_topic, topic_index)
        msg_text = f"اختر الموضوع الفرعي لـ: *{chosen_topic['topicName']}*\n\n{chosen_topic['description']}"
        await query.message.edit_text(
            text=msg_text,
            parse_mode="Markdown",
            reply_markup=subtopics_keyboard
        )

    # ------------------------------------------------------------------------
    # زر الرجوع لقائمة المواضيع
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
    # إذا كانت الصيغة subtopic_{topic_index}_{sub_index}
    # ------------------------------------------------------------------------
    elif data.startswith("subtopic_"):
        # مثال: data = "subtopic_0_2"
        _, t_idx_str, s_idx_str = data.split("_")
        t_idx = int(t_idx_str)
        s_idx = int(s_idx_str)
        context.user_data[CUR_TOPIC_IDX_KEY] = t_idx
        context.user_data[CUR_SUBTOPIC_IDX_KEY] = s_idx
        context.user_data[CURRENT_STATE_KEY] = STATE_ASK_NUM_QUESTIONS

        # يمكننا سؤال المستخدم مباشرةً عن العدد في نفس الرسالة
        # أو نستخدم `reply_markup` بعرض زر رجوع فقط (لأننا سندخل العدد بالكتابة).
        back_btn = InlineKeyboardButton("« رجوع للمواضيع الفرعية", callback_data=f"go_back_subtopics_{t_idx}")
        kb = InlineKeyboardMarkup([[back_btn]])

        # عرض رسالة تطلب من المستخدم إدخال عدد الأسئلة
        await query.message.edit_text(
            text="أدخل عدد الأسئلة المطلوبة (أرسل رقمًا فقط):",
            reply_markup=kb
        )

    # ------------------------------------------------------------------------
    # زر الرجوع لقائمة المواضيع الفرعية
    # ------------------------------------------------------------------------
    elif data.startswith("go_back_subtopics_"):
        # استعادة الـ topic_index
        _, t_idx_str = data.split("_subtopics_")
        t_idx = int(t_idx_str)
        context.user_data[CUR_TOPIC_IDX_KEY] = t_idx
        context.user_data[CURRENT_STATE_KEY] = STATE_SELECT_SUBTOPIC

        topics_data = context.user_data.get(TOPICS_KEY, [])
        if 0 <= t_idx < len(topics_data):
            chosen_topic = topics_data[t_idx]
            subtopics_keyboard = generate_subtopics_inline_keyboard(chosen_topic, t_idx)
            msg_text = f"اختر الموضوع الفرعي لـ: *{chosen_topic['topicName']}*\n\n{chosen_topic['description']}"
            await query.message.edit_text(
                text=msg_text,
                parse_mode="Markdown",
                reply_markup=subtopics_keyboard
            )
        else:
            await query.message.edit_text("خيار غير صحيح.")

    else:
        await query.message.reply_text("لم أفهم هذا الخيار.")


# ===================================================
# 8) هاندلر استقبال الرسائل (للتعامل مع إدخال عدد الأسئلة)
# ===================================================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state = context.user_data.get(CURRENT_STATE_KEY, None)

    # إذا كنا في مرحلة "ASK_NUM_QUESTIONS" فنحن ننتظر إدخال عدد الأسئلة
    if user_state == STATE_ASK_NUM_QUESTIONS:
        text = update.message.text.strip()
        if not text.isdigit():
            await update.message.reply_text("من فضلك أدخل رقمًا صحيحًا.")
            return

        num_q = int(text)
        if num_q <= 0:
            await update.message.reply_text("العدد يجب أن يكون أكبر من صفر.")
            return

        # حفظ العدد في user_data
        context.user_data[NUM_QUESTIONS_KEY] = num_q
        context.user_data[CURRENT_STATE_KEY] = STATE_SENDING_QUESTIONS

        # الآن نجلب الأسئلة من الملف المناسب
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

        file_path = subtopics[s_idx]["file"]  # مسار ملف الأسئلة
        questions = fetch_questions(file_path)
        if not questions:
            await update.message.reply_text("لم أتمكن من جلب أسئلة لهذا الموضوع الفرعي.")
            return

        # إذا كان العدد المطلوب أكبر من الأسئلة المتوفرة، نستخدم جميع الأسئلة.
        if num_q > len(questions):
            num_q = len(questions)

        # اختيار عشوائي أو بالترتيب. هنا سنختار عشوائيًا:
        random.shuffle(questions)
        selected_questions = questions[:num_q]

        # تخزينها في user_data (لو احتجنا)
        context.user_data[QUESTIONS_KEY] = selected_questions

        # إرسال رسالة توضيحية
        await update.message.reply_text(f"سيتم إرسال {num_q} سؤال(أسئلة) في شكل Poll. بالتوفيق!")

        # إرسال الأسئلة
        # ملاحظة: تيليجرام يسمح بـ 10 خيارات فقط في الـ Poll. أسئلتك غالبًا فيها 4 خيارات، فهذا مناسب.
        for idx, q in enumerate(selected_questions, start=1):
            question_text = q["question"]
            options = q["options"]  # قائمة الاختيارات
            # مطلوب تحديد index الإجابة الصحيحة لفحصه => Telegram Poll يحتاج تحديد correct_option_id للأحادية
            correct_id = q["answer"]  # بالنسبة للـ JSON المعطى: index من 0-based أم 1-based؟
            # لاحظ أن "answer": 2 => قد يكون index=2 (لو كان 0-based يصبح الخيار الثالث). تأكد من التوافق.
            # حسب الأمثلة، يبدو أنه 0-based, لكن الأرقام في الأمثلة "answer": 2 ... إلخ. تحققنا من الأسئلة مثال:
            # "answer": 2 => تعني الخيار رقم 2 من الـ 0-based؛ إذا لديك شك تأكد بتعديل الصيغة.

            # تحضير السؤال كـ Poll
            # سنختار يكون "is_anonymous=False" و "type=Poll.QUIZ" ليظهر كـ Quiz
            # لو أردنا تجميع الإجابات دون إظهار الصح والخطأ نستعمل type=Poll.REGULAR
            await context.bot.send_poll(
                chat_id=update.message.chat_id,
                question=f"سؤال {idx}: {question_text}",
                options=options,
                type=Poll.QUIZ,
                correct_option_id=correct_id,
                explanation=q["explanation"] if "explanation" in q else "",
                is_anonymous=False
            )

        # بعد إرسال الأسئلة، يمكننا إعادة الحالة إلى شيء آخر (مثلا الإنتهاء)
        context.user_data[CURRENT_STATE_KEY] = None

    else:
        # أي رسالة أخرى في غير وقتها
        await update.message.reply_text("أرسل /start لاختيار الموضوع من جديد أو اضغط على الأزرار المتاحة.")


# ===================================================
# 9) دالة الـ main وتشغيل البوت
# ===================================================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "الأوامر المتاحة:\n"
        "/start - لبدء اختيار المواضيع\n"
        "/help - عرض هذه الرسالة\n\n"
        "يمكنك أيضًا منادات البوت في المجموعات وسيعمل."
    )
    await update.message.reply_text(help_text)


def main():
    # ضع التوكن الخاص بك هنا
    BOT_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"

    # إنشاء التطبيق
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ربط الهاندلرز
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))

    # الهاندلر للأزرار (CallbackQuery)
    app.add_handler(CallbackQueryHandler(callback_handler))

    # الهاندلر للرسائل النصية العادية (لاستقبال عدد الأسئلة)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # تشغيل البوت (Blocking)
    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
