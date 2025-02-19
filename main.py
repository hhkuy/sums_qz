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

# تفعيل تسجيل المعلومات والأخطاء
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# تعريف المراحل في Conversation
CHOOSING_TOPIC, CHOOSING_SUBTOPIC, TYPING_QUESTION_COUNT, QUIZ_IN_PROGRESS = range(4)

# ضَع هنا الرابط الأساسي لملفاتك على GitHub (raw)
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/hhkuy/Sums_Q/main/"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يعالج أمر /start:
    1. جلب ملف topics.json من GitHub.
    2. عرض قائمة المواضيع الرئيسية على شكل أزرار.
    """
    logger.info("تم استقبال أمر /start من المستخدم %s", update.effective_user.id)

    # مسار ملف المواضيع
    topics_url = GITHUB_RAW_BASE + "data/topics.json"
    try:
        resp = requests.get(topics_url)
        resp.raise_for_status()
        topics_list = resp.json()  # نفترض أنه مصفوفة من المواضيع
    except Exception as e:
        logger.error("خطأ في جلب أو قراءة topics.json: %s", e)
        await update.message.reply_text("عذراً، حدث خطأ أثناء تحميل المواضيع.")
        return ConversationHandler.END

    if not topics_list:
        await update.message.reply_text("لا توجد مواضيع في ملف topics.json!")
        return ConversationHandler.END

    # نحفظ المواضيع في user_data حتى لا نضطر لإعادة التحميل عند العودة (Back)
    context.user_data["topics_list"] = topics_list

    # نبني الأزرار (لكل topic زر)
    keyboard = []
    for i, topic in enumerate(topics_list):
        topic_name = topic.get("topicName", f"Topic {i}")
        callback_data = f"topic|{i}"
        keyboard.append([InlineKeyboardButton(topic_name, callback_data=callback_data)])

    # نعرض الأزرار
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "أهلاً بك! اختر أحد المواضيع:",
        reply_markup=reply_markup
    )

    return CHOOSING_TOPIC


async def choose_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عند اختيار المستخدم لموضوع رئيسي:
    - نعرض قائمة المواضيع الفرعية (subTopics) مع زر للرجوع (Back).
    """
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    if data[0] != "topic":
        # في حال وصول callback_data غير متوقع
        await query.edit_message_text("خطأ في الاختيار. جرّب /start من جديد.")
        return ConversationHandler.END

    try:
        topic_index = int(data[1])
    except ValueError:
        await query.edit_message_text("اختيار غير صالح (فهرس).")
        return ConversationHandler.END

    topics_list = context.user_data.get("topics_list", [])
    if topic_index < 0 or topic_index >= len(topics_list):
        await query.edit_message_text("اختيار غير صالح (خارج النطاق).")
        return ConversationHandler.END

    selected_topic = topics_list[topic_index]
    sub_topics = selected_topic.get("subTopics", [])

    context.user_data["selected_topic_index"] = topic_index

    # نبني قائمة الأزرار للمواضيع الفرعية
    keyboard = []
    for i, sub in enumerate(sub_topics):
        name = sub.get("name", f"Subtopic {i}")
        # نخزّن المسار في user_data["file_paths"] لاحقاً أم مباشرةً؟ 
        # يمكننا تخزينه الآن أو تمرير index. سنختار index.
        callback_data = f"subtopic|{i}"
        keyboard.append([InlineKeyboardButton(name, callback_data=callback_data)])

    # زر العودة للمواضيع الرئيسية
    keyboard.append([InlineKeyboardButton("« رجوع", callback_data="back|topics")])

    if not keyboard:
        await query.edit_message_text("لا توجد مواضيع فرعية لهذا الموضوع.")
        return CHOOSING_TOPIC

    # عرض المواضيع الفرعية
    await query.edit_message_text(
        text=f"اختر موضوعاً فرعياً من **{selected_topic.get('topicName','Unnamed')}**:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CHOOSING_SUBTOPIC


async def back_to_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يعيد عرض قائمة المواضيع الرئيسية عندما يضغط المستخدم زر (Back).
    """
    query = update.callback_query
    await query.answer()

    topics_list = context.user_data.get("topics_list", [])
    if not topics_list:
        await query.edit_message_text("لا توجد مواضيع محفوظة. استخدم /start.")
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
    بعد اختيار المستخدم لموضوع فرعي:
    - نحفظ مسار الملف في user_data ونطلب عدد الأسئلة.
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
    if topic_index is None or topic_index < 0 or topic_index >= len(topics_list):
        await query.edit_message_text("الموضوع غير محدد بشكل صحيح. استخدم /start من جديد.")
        return ConversationHandler.END

    selected_topic = topics_list[topic_index]
    sub_topics = selected_topic.get("subTopics", [])
    if sub_index < 0 or sub_index >= len(sub_topics):
        await query.edit_message_text("اختيار غير صالح (خارج النطاق).")
        return ConversationHandler.END

    # نحفظ مسار الملف
    subtopic_info = sub_topics[sub_index]
    file_path = subtopic_info.get("file")
    context.user_data["questions_file"] = file_path

    await query.edit_message_text("كم عدد الأسئلة التي تريدها؟ (أدخل رقم)")
    return TYPING_QUESTION_COUNT


async def receive_question_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    بعد استقبال عدد الأسئلة المطلوب:
    - نجلب ملف الأسئلة
    - نختار بالصدفة العدد المطلوب
    - نرسلها على شكل Poll Quiz
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

    # الآن نجلب ملف الأسئلة
    questions_file_path = context.user_data.get("questions_file")
    if not questions_file_path:
        await update.message.reply_text("لم يتم تحديد ملف الأسئلة. أعد المحاولة من /start.")
        return ConversationHandler.END

    # نحصل على الرابط الكامل
    questions_url = GITHUB_RAW_BASE + questions_file_path
    logger.info("جلب الأسئلة من: %s", questions_url)

    try:
        resp = requests.get(questions_url)
        resp.raise_for_status()
        questions_list = resp.json()
    except Exception as e:
        logger.error("خطأ في جلب أو قراءة ملف الأسئلة: %s", e)
        await update.message.reply_text("حدث خطأ أثناء تحميل الأسئلة من GitHub.")
        return ConversationHandler.END

    if not questions_list:
        await update.message.reply_text("الملف لا يحتوي على أسئلة.")
        return ConversationHandler.END

    # اختيار عشوائي لعدد من الأسئلة
    random.shuffle(questions_list)
    selected_questions = questions_list[:num_questions]

    # نخزّن بيانات الاختبار
    context.user_data["selected_questions"] = selected_questions
    context.user_data["score"] = 0
    context.user_data["answered"] = 0
    context.user_data["total"] = len(selected_questions)
    context.user_data["polls"] = {}

    await update.message.reply_text("سيبدأ الاختبار الآن...")

    # إرسال كل سؤال على شكل استفتاء Quiz
    for idx, question_data in enumerate(selected_questions, start=1):
        question_text = question_data.get("question", f"سؤال {idx}")
        options = question_data.get("options", [])
        if not options:
            options = ["خيار 1", "خيار 2"]  # احتياط

        correct_index = question_data.get("answer", 0)
        explanation = question_data.get("explanation", "")

        # نستخدم context.bot لإرسال الاستفتاء في نفس المحادثة
        sent_poll = await context.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=question_text,
            options=options,
            type="quiz",
            correct_option_id=correct_index,
            is_anonymous=False,
            explanation=explanation,
            open_period=120,  # مدة توفر الإجابة 120 ثانية (يمكن تعديلها أو حذفها)
            parse_mode="HTML"
        )
        poll_id = sent_poll.poll.id
        # نحفظ بيانات الاستفتاء
        context.user_data["polls"][poll_id] = {
            "correct_option_id": correct_index,
            "answered": False
        }

    return QUIZ_IN_PROGRESS


async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يعالج إجابة المستخدم على كل استفتاء.
    إذا انتهى المستخدم من الإجابة على جميع الأسئلة، يُرسل له النتيجة.
    """
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    selected_option_ids = poll_answer.option_ids
    user_id = poll_answer.user.id

    logger.info(
        "إجابة مستخدم %s على الاستفتاء %s: %s",
        user_id, poll_id, selected_option_ids
    )

    polls_data = context.user_data.get("polls", {})
    if poll_id not in polls_data:
        logger.warning("Poll ID غير معروف.")
        return

    poll_info = polls_data[poll_id]
    if poll_info["answered"]:
        # تمّت الإجابة مسبقاً
        return

    poll_info["answered"] = True

    correct_id = poll_info["correct_option_id"]
    if selected_option_ids and selected_option_ids[0] == correct_id:
        context.user_data["score"] += 1

    context.user_data["answered"] += 1

    # إذا أجاب المستخدم على كل الأسئلة
    if context.user_data["answered"] == context.user_data["total"]:
        score = context.user_data["score"]
        total = context.user_data["total"]
        logger.info("انتهاء الاختبار للمستخدم %s - النتيجة %d/%d", user_id, score, total)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"انتهى الاختبار!\nنتيجتك: {score} من {total}"
        )
        # تنظيف بيانات الجلسة
        context.user_data.clear()


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    أمر /cancel لإنهاء المحادثة في أي وقت.
    """
    logger.info("استخدام أمر /cancel من قبل المستخدم %s", update.effective_user.id)
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END


def main():
    """
    الدالة الرئيسية لتشغيل البوت.
    """
    TOKEN = "7633072361:AAHnzREYTKKRFiTiq7HDZBalnwnmgivY8_I"  # ← ضع التوكن الخاص ببوتك هنا

    logger.info("بدء تشغيل البوت...")
    application = Application.builder().token(TOKEN).build()

    # بناء ConversationHandler
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
            QUIZ_IN_PROGRESS: []  # الإجابات تُلتقط بواسطة PollAnswerHandler
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    # إضافة ConversationHandler
    application.add_handler(conv_handler)

    # إضافة PollAnswerHandler لمعالجة إجابات الاستفتاءات
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    logger.info("البوت يعمل الآن... ابدأ بكتابة /start.")
    application.run_polling()


if __name__ == "__main__":
    main()
