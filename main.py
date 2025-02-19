import logging
import json
import random
import requests
import os

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PollAnswerHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# إعداد تسجيل المعلومات والأخطاء
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# مراحل Conversation
CHOOSING_TOPIC, CHOOSING_SUBTOPIC, TYPING_QUESTION_COUNT, QUIZ_IN_PROGRESS = range(4)

# لاحظ أننا أزلنا "data/" هنا. انتهينا مباشرة بـ "main"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/hhkuy/Sums_Q/main"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يعالج أمر /start:
    1. تحميل topics.json من GitHub.
    2. عرض قائمة المواضيع الرئيسية (Topic).
    """
    logger.info("تم استقبال أمر /start من المستخدم %s", update.effective_user.id)

    # هنا نضيف "/data/topics.json" لأننا حذفنا data/ من الثابت بالأعلى
    topics_url = GITHUB_RAW_BASE + "/data/topics.json"
    try:
        resp = requests.get(topics_url)
        resp.raise_for_status()
        topics_list = resp.json()  # يفترض أن يكون مصفوفة من المواضيع
    except Exception as e:
        logger.error("خطأ عند جلب/قراءة topics.json: %s", e)
        await update.message.reply_text("عذراً، حدث خطأ أثناء تحميل المواضيع من GitHub.")
        return ConversationHandler.END

    if not topics_list:
        await update.message.reply_text("لا توجد مواضيع في ملف topics.json!")
        return ConversationHandler.END

    # حفظ قائمة المواضيع في user_data لتسهيل العودة إليها
    context.user_data["topics_list"] = topics_list

    # إنشاء أزرار لكل Topic
    keyboard = []
    for i, topic in enumerate(topics_list):
        topic_name = topic.get("topicName", f"Topic {i}")
        callback_data = f"topic|{i}"
        keyboard.append([InlineKeyboardButton(topic_name, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "أهلاً بك! اختر أحد المواضيع:",
        reply_markup=reply_markup
    )
    return CHOOSING_TOPIC


async def choose_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عند اختيار المستخدم لموضوع رئيسي:
    - نعرض قائمة المواضيع الفرعية (subTopics) مع زر Back للرجوع.
    """
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    if data[0] != "topic":
        await query.edit_message_text("اختيار غير صالح. اكتب /start من جديد.")
        return ConversationHandler.END

    try:
        topic_index = int(data[1])
    except ValueError:
        await query.edit_message_text("اختيار غير صالح (ليس عدداً).")
        return ConversationHandler.END

    topics_list = context.user_data.get("topics_list", [])
    if topic_index < 0 or topic_index >= len(topics_list):
        await query.edit_message_text("اختيار خارج النطاق. اكتب /start مجدداً.")
        return ConversationHandler.END

    selected_topic = topics_list[topic_index]
    sub_topics = selected_topic.get("subTopics", [])

    context.user_data["selected_topic_index"] = topic_index

    keyboard = []
    for i, sub in enumerate(sub_topics):
        sub_name = sub.get("name", f"Subtopic {i}")
        callback_data = f"subtopic|{i}"
        keyboard.append([InlineKeyboardButton(sub_name, callback_data=callback_data)])

    # زر العودة لقائمة المواضيع الرئيسية
    keyboard.append([InlineKeyboardButton("« رجوع", callback_data="back|topics")])

    if not sub_topics:
        await query.edit_message_text("لا توجد مواضيع فرعية لهذا الموضوع.")
        return CHOOSING_TOPIC

    await query.edit_message_text(
        text=f"اختر موضوعاً فرعياً من **{selected_topic.get('topicName','Unnamed')}**:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CHOOSING_SUBTOPIC


async def back_to_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يُعيد المستخدم إلى قائمة المواضيع الرئيسية عند الضغط على زر Back.
    """
    query = update.callback_query
    await query.answer()

    topics_list = context.user_data.get("topics_list", [])
    if not topics_list:
        await query.edit_message_text("لا توجد مواضيع محفوظة. اكتب /start.")
        return ConversationHandler.END

    keyboard = []
    for i, topic in enumerate(topics_list):
        topic_name = topic.get("topicName", f"Topic {i}")
        callback_data = f"topic|{i}"
        keyboard.append([InlineKeyboardButton(topic_name, callback_data=callback_data)])

    await query.edit_message_text(
        text="اختر أحد المواضيع:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_TOPIC


async def choose_subtopic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يعالج اختيار المستخدم للموضوع الفرعي:
    - يحفظ مسار ملف الأسئلة في user_data
    - يطلب إدخال عدد الأسئلة.
    """
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    if data[0] != "subtopic":
        await query.edit_message_text("اختيار غير صالح.")
        return ConversationHandler.END

    try:
        sub_index = int(data[1])
    except ValueError:
        await query.edit_message_text("اختيار غير صالح (فهرس).")
        return ConversationHandler.END

    topic_index = context.user_data.get("selected_topic_index")
    topics_list = context.user_data.get("topics_list", [])
    if topic_index is None or not (0 <= topic_index < len(topics_list)):
        await query.edit_message_text("خطأ في الموضوع الرئيسي. اكتب /start من جديد.")
        return ConversationHandler.END

    selected_topic = topics_list[topic_index]
    sub_topics = selected_topic.get("subTopics", [])
    if sub_index < 0 or sub_index >= len(sub_topics):
        await query.edit_message_text("اختيار فرعي خارج النطاق.")
        return ConversationHandler.END

    subtopic_info = sub_topics[sub_index]
    file_path = subtopic_info.get("file")
    if not file_path:
        await query.edit_message_text("لم يتم العثور على مسار ملف الأسئلة.")
        return ConversationHandler.END

    # احفظ المسار في user_data
    context.user_data["questions_file"] = file_path

    await query.edit_message_text("كم عدد الأسئلة المطلوبة؟ (أدخل رقم)")
    return TYPING_QUESTION_COUNT


async def receive_question_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    بعد إدخال عدد الأسئلة:
    1. تحميل ملف الأسئلة من GitHub.
    2. اختيار (num_questions) أسئلة عشوائية.
    3. إرسالها على شكل Poll Quiz.
    """
    user_text = update.message.text.strip()
    logger.info("المستخدم %s أدخل عدد الأسئلة: %s", update.effective_user.id, user_text)

    try:
        num_questions = int(user_text)
        if num_questions <= 0:
            await update.message.reply_text("الرجاء إدخال رقم موجب.")
            return TYPING_QUESTION_COUNT
    except ValueError:
        await update.message.reply_text("الرجاء إدخال رقم صحيح.")
        return TYPING_QUESTION_COUNT

    context.user_data["num_questions"] = num_questions

    questions_file_path = context.user_data.get("questions_file")
    if not questions_file_path:
        await update.message.reply_text("لم يتم تحديد ملف الأسئلة. اكتب /start مجدداً.")
        return ConversationHandler.END

    # تجهيز الرابط الكامل للملف (لاحظ أننا وضعنا "/" بينهما)
    questions_url = GITHUB_RAW_BASE + "/" + questions_file_path
    logger.info("جلب الأسئلة من: %s", questions_url)

    try:
        resp = requests.get(questions_url)
        resp.raise_for_status()
        questions_list = resp.json()
    except Exception as e:
        logger.error("خطأ عند جلب/قراءة ملف الأسئلة: %s", e)
        await update.message.reply_text("حدث خطأ أثناء تحميل ملف الأسئلة من GitHub.")
        return ConversationHandler.END

    if not questions_list:
        await update.message.reply_text("الملف لا يحتوي على أسئلة.")
        return ConversationHandler.END

    logger.info("تم تحميل %d سؤال من الملف: %s", len(questions_list), questions_file_path)

    # اختيار عشوائي للأسئلة
    random.shuffle(questions_list)
    selected_questions = questions_list[:num_questions]

    context.user_data["selected_questions"] = selected_questions
    context.user_data["score"] = 0
    context.user_data["answered"] = 0
    context.user_data["total"] = len(selected_questions)
    context.user_data["polls"] = {}

    await update.message.reply_text("سيبدأ الاختبار الآن...")

    # إرسال كل سؤال على شكل Quiz Poll
    for idx, qdata in enumerate(selected_questions, start=1):
        question_text = qdata.get("question", f"سؤال {idx}")
        options = qdata.get("options", [])
        if not options:
            options = ["خيار 1", "خيار 2"]  # كإجراء احتياطي
        correct_index = qdata.get("answer", 0)
        explanation = qdata.get("explanation", "")

        # إرسال الاستفتاء
        sent_poll = await context.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=question_text,
            options=options,
            type="quiz",
            correct_option_id=correct_index,
            is_anonymous=False,
            explanation=explanation,
            open_period=120,  # 120 ثانية (يمكن تعديلها أو حذفها)
            parse_mode="HTML"
        )
        poll_id = sent_poll.poll.id

        context.user_data["polls"][poll_id] = {
            "correct_option_id": correct_index,
            "answered": False
        }

    return QUIZ_IN_PROGRESS


async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يعالج إجابات الاستفتاءات.
    إذا انتهت الأسئلة، يعرض النتيجة للمستخدم.
    """
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    selected_ids = poll_answer.option_ids
    user_id = poll_answer.user.id

    logger.info("استلام إجابة من المستخدم %s على الاستفتاء %s: %s",
                user_id, poll_id, selected_ids)

    polls_data = context.user_data.get("polls", {})
    if poll_id not in polls_data:
        logger.warning("poll_id غير معروف (%s). ربما جلسة منتهية.", poll_id)
        return

    poll_info = polls_data[poll_id]
    if poll_info["answered"]:
        logger.info("تمت الإجابة مسبقاً على هذا الاستفتاء.")
        return

    poll_info["answered"] = True

    correct_index = poll_info["correct_option_id"]
    if selected_ids and selected_ids[0] == correct_index:
        context.user_data["score"] += 1

    context.user_data["answered"] += 1
    if context.user_data["answered"] == context.user_data["total"]:
        score = context.user_data["score"]
        total = context.user_data["total"]
        logger.info("انتهاء الاختبار للمستخدم %s. النتيجة %d/%d", user_id, score, total)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"انتهى الاختبار!\nنتيجتك: {score} من {total}"
        )
        # تنظيف بيانات الجلسة
        context.user_data.clear()


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    أمر /cancel لإلغاء المحادثة في أي وقت.
    """
    logger.info("استخدام /cancel من قبل المستخدم %s", update.effective_user.id)
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END


def main():
    """
    الدالة الرئيسية لتشغيل البوت.
    """
    # ضع التوكن الخاص ببوتك هنا
    TOKEN = "7633072361:AAHnzREYTKKRFiTiq7HDZBalnwnmgivY8_I"

    logger.info("بدء تشغيل البوت...")
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_TOPIC: [
                CallbackQueryHandler(choose_topic, pattern=r"^topic\|\d+$"),
            ],
            CHOOSING_SUBTOPIC: [
                CallbackQueryHandler(back_to_topics, pattern=r"^back\|topics$"),
                CallbackQueryHandler(choose_subtopic, pattern=r"^subtopic\|\d+$"),
            ],
            TYPING_QUESTION_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_question_count),
            ],
            QUIZ_IN_PROGRESS: []  # المعالجة في handle_poll_answer
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    # إضافة ConversationHandler
    application.add_handler(conv_handler)
    # إضافة PollAnswerHandler
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    logger.info("البوت يعمل الآن. ابدأ بالأمر /start")
    application.run_polling()


if __name__ == "__main__":
    main()
