import logging
import json
import random
import requests

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# إعداد تسجيل الأخطاء والمعلومات
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# تعريف مراحل المحادثة
SELECT_TOPIC, SELECT_SUBTOPIC, SELECT_NUM_QUESTIONS, WAITING_FOR_ANSWER = range(4)

# رابط GitHub RAW لتحميل ملفات البيانات (topics.json والملفات الخاصة بالأسئلة)
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/hhkuy/Sums_Q/main/"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    دالة /start:
    - تحميل ملف topics.json من GitHub.
    - عرض قائمة المواضيع الرئيسية للمستخدم.
    """
    logger.info("استقبال أمر /start من المستخدم %s", update.effective_user.id)

    url = GITHUB_RAW_BASE + "data/topics.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("خطأ أثناء جلب المواضيع من GitHub: %s", e)
        await update.message.reply_text("تعذّر تحميل المواضيع من GitHub.")
        return ConversationHandler.END

    try:
        topics_list = response.json()  # نتوقع أن يكون مصفوفة من المواضيع
    except json.JSONDecodeError as e:
        logger.error("ملف topics.json ليس بصيغة JSON صحيحة: %s", e)
        await update.message.reply_text("ملف المواضيع غير صالح (JSON).")
        return ConversationHandler.END

    if not topics_list:
        await update.message.reply_text("لا توجد مواضيع في ملف topics.json!")
        return ConversationHandler.END

    # حفظ بيانات المواضيع في user_data لإعادة استخدامها
    context.user_data["topics_data"] = topics_list

    # إنشاء قائمة أزرار للمواضيع الرئيسية فقط
    keyboard = []
    for index, topic in enumerate(topics_list):
        topic_name = topic.get("topicName", "بدون اسم")
        keyboard.append([InlineKeyboardButton(topic_name, callback_data=f"topic|{index}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("اختر موضوعاً للاختبار:", reply_markup=reply_markup)
    return SELECT_TOPIC

async def select_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عند اختيار موضوع رئيسي:
    - يتم استخراج فهرس الموضوع وعرض المواضيع الفرعية الخاصة به.
    """
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")
    if data[0] != "topic":
        await query.edit_message_text("اختيار غير صالح.")
        return ConversationHandler.END

    try:
        topic_index = int(data[1])
    except ValueError:
        await query.edit_message_text("اختيار غير صالح (فهرس).")
        return ConversationHandler.END

    topics_data = context.user_data.get("topics_data", [])
    if topic_index < 0 or topic_index >= len(topics_data):
        await query.edit_message_text("اختيار غير صالح (خارج النطاق).")
        return ConversationHandler.END

    selected_topic = topics_data[topic_index]
    context.user_data["selected_topic_index"] = topic_index

    sub_topics = selected_topic.get("subTopics", [])
    if not sub_topics:
        await query.edit_message_text("لا توجد مواضيع فرعية في هذا الموضوع.")
        return ConversationHandler.END

    keyboard = []
    for index, sub in enumerate(sub_topics):
        sub_name = sub.get("name")
        if not sub_name:
            continue
        # ترميز بيانات الموضع الفرعي مع رقم الموضوع والفهرس الفرعي
        keyboard.append([InlineKeyboardButton(sub_name, callback_data=f"subtopic|{topic_index}|{index}")])
    # إضافة زر رجوع للعودة لقائمة المواضيع الرئيسية
    keyboard.append([InlineKeyboardButton("رجوع", callback_data="back_to_topics")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("اختر موضوعاً فرعياً للاختبار:", reply_markup=reply_markup)
    return SELECT_SUBTOPIC

async def back_to_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    دالة العودة إلى قائمة المواضيع الرئيسية.
    """
    query = update.callback_query
    await query.answer()
    topics_data = context.user_data.get("topics_data", [])
    if not topics_data:
        await query.edit_message_text("لا توجد مواضيع.")
        return ConversationHandler.END

    keyboard = []
    for index, topic in enumerate(topics_data):
        topic_name = topic.get("topicName", "بدون اسم")
        keyboard.append([InlineKeyboardButton(topic_name, callback_data=f"topic|{index}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("اختر موضوعاً للاختبار:", reply_markup=reply_markup)
    return SELECT_TOPIC

async def select_subtopic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عند اختيار موضوع فرعي:
    - يتم استخراج مسار ملف الأسئلة الخاص به.
    - يُطلب من المستخدم إدخال عدد الأسئلة.
    """
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    if data[0] != "subtopic":
        await query.edit_message_text("اختيار غير صالح.")
        return ConversationHandler.END

    try:
        topic_index = int(data[1])
        sub_index = int(data[2])
    except ValueError:
        await query.edit_message_text("اختيار غير صالح (فهرس).")
        return ConversationHandler.END

    topics_data = context.user_data.get("topics_data", [])
    if topic_index < 0 or topic_index >= len(topics_data):
        await query.edit_message_text("اختيار غير صالح (خارج النطاق).")
        return ConversationHandler.END

    selected_topic = topics_data[topic_index]
    sub_topics = selected_topic.get("subTopics", [])
    if sub_index < 0 or sub_index >= len(sub_topics):
        await query.edit_message_text("اختيار غير صالح (خارج النطاق).")
        return ConversationHandler.END

    selected_sub = sub_topics[sub_index]
    file_path = selected_sub.get("file")
    if not file_path:
        await query.edit_message_text("ملف الأسئلة غير موجود.")
        return ConversationHandler.END

    context.user_data["questions_file"] = file_path

    await query.edit_message_text("كم عدد الأسئلة التي ترغب في الحصول عليها؟ (أدخل رقم)")
    return SELECT_NUM_QUESTIONS

async def select_num_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    بعد إدخال عدد الأسئلة:
    - تحميل ملف الأسئلة من GitHub.
    - اختيار عدد عشوائي من الأسئلة وإرسال كل سؤال على شكل استفتاء (quiz).
    """
    num_text = update.message.text.strip()
    logger.info("المستخدم %s أدخل عدد الأسئلة: %s", update.effective_user.id, num_text)

    try:
        num_questions = int(num_text)
        if num_questions <= 0:
            await update.message.reply_text("الرجاء إدخال رقم موجب.")
            return SELECT_NUM_QUESTIONS
    except ValueError:
        await update.message.reply_text("الرجاء إدخال رقم صحيح.")
        return SELECT_NUM_QUESTIONS

    context.user_data["num_questions"] = num_questions

    questions_file = context.user_data.get("questions_file")
    if not questions_file:
        await update.message.reply_text("ملف الأسئلة غير محدد.")
        return ConversationHandler.END

    questions_url = GITHUB_RAW_BASE + questions_file
    logger.info("جلب الأسئلة من: %s", questions_url)
    try:
        response = requests.get(questions_url)
        response.raise_for_status()
        questions_list = response.json()
    except requests.RequestException as e:
        logger.error("خطأ أثناء جلب الأسئلة: %s", e)
        await update.message.reply_text("حدث خطأ أثناء تحميل الأسئلة من GitHub.")
        return ConversationHandler.END
    except json.JSONDecodeError as e:
        logger.error("ملف الأسئلة JSON غير صالح: %s", e)
        await update.message.reply_text("ملف الأسئلة غير صالح (JSON).")
        return ConversationHandler.END

    if not questions_list:
        await update.message.reply_text("لا توجد أسئلة في هذا الملف.")
        return ConversationHandler.END

    random.shuffle(questions_list)
    selected_questions = questions_list[:num_questions]

    context.user_data["selected_questions"] = selected_questions
    context.user_data["score"] = 0
    context.user_data["total"] = len(selected_questions)
    context.user_data["answered"] = 0
    context.user_data["polls"] = {}

    await update.message.reply_text("سيبدأ الاختبار الآن. أجب عن الأسئلة التالية:")

    for i, question in enumerate(selected_questions, start=1):
        q_text = question.get("question", f"سؤال #{i}")
        options = question.get("options", ["خيار 1", "خيار 2"])
        correct_id = question.get("answer", 0)  # رقم الخيار الصحيح
        explanation = question.get("explanation", "")

        sent_poll = await update.message.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=q_text,
            options=options,
            type="quiz",
            correct_option_id=correct_id,
            is_anonymous=False,
            explanation=explanation,
            open_period=120,  # مدة الرد بالثواني (يمكن التعديل)
            parse_mode="HTML"
        )
        poll_id = sent_poll.poll.id
        context.user_data["polls"][poll_id] = {
            "correct_option_id": correct_id,
            "answered": False
        }

    return WAITING_FOR_ANSWER

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    معالجة إجابات الاستفتاء وعرض النتيجة عند الانتهاء من جميع الأسئلة.
    """
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    selected_options = poll_answer.option_ids
    user_id = poll_answer.user.id

    logger.info("إجابة جديدة من المستخدم %s على poll_id=%s, selected=%s", user_id, poll_id, selected_options)

    if "polls" in context.user_data and poll_id in context.user_data["polls"]:
        poll_data = context.user_data["polls"][poll_id]
        if poll_data["answered"]:
            logger.info("تمت الإجابة مسبقاً على هذا الاستفتاء.")
            return

        poll_data["answered"] = True

        if selected_options and selected_options[0] == poll_data["correct_option_id"]:
            context.user_data["score"] += 1

        context.user_data["answered"] += 1

        if context.user_data["answered"] == context.user_data["total"]:
            score = context.user_data["score"]
            total = context.user_data["total"]
            logger.info("انتهاء الاختبار للمستخدم %s. النتيجة: %d/%d", user_id, score, total)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"انتهى الاختبار!\nنتيجتك: {score} من {total}"
            )
            context.user_data.clear()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    أمر /cancel لإلغاء الاختبار أو المحادثة.
    """
    logger.info("استخدم المستخدم %s أمر /cancel", update.effective_user.id)
    await update.message.reply_text("تم إلغاء الاختبار.")
    return ConversationHandler.END

def main():
    """
    الدالة الرئيسية لتشغيل البوت باستخدام التوكن.
    """
    # ضع هنا توكن البوت الخاص بك
    TOKEN = "7633072361:AAHnzREYTKKRFiTiq7HDZBalnwnmgivY8_I"

    logger.info("بدء تشغيل البوت...")
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_TOPIC: [
                CallbackQueryHandler(select_topic, pattern="^topic\\|")
            ],
            SELECT_SUBTOPIC: [
                CallbackQueryHandler(select_subtopic, pattern="^subtopic\\|"),
                CallbackQueryHandler(back_to_topics, pattern="^back_to_topics$")
            ],
            SELECT_NUM_QUESTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_num_questions)
            ],
            # مرحلة WAITING_FOR_ANSWER ليست بحاجة لمعالجات إضافية؛ ننتظر إجابات الاستفتاء
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    application.add_handler(conv_handler)
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    logger.info("البوت يعمل الآن. ارسل /start للبدء.")
    application.run_polling()

if __name__ == "__main__":
    main()
