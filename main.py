import logging
import json
import random
import requests
import os

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

# الدوال في البوت ستتعامل مع مراحل محادثة متعددة
SELECT_SUBTOPIC, SELECT_NUM_QUESTIONS, WAITING_FOR_ANSWER = range(3)

# ضع هنا رابط GitHub RAW للوصول إلى ملفاتك
# إن كان لديك مجلد /data يحتوي على topics.json وملفات الأسئلة.
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/hhkuy/Sums_Q/main/"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    دالة /start:
    1. تحميل ملف topics.json من GitHub.
    2. إنشاء قائمة أزرار للمواضيع الفرعية.
    3. استخدام أرقام (indices) في callback_data لتلافي أخطاء الطول/الرموز.
    """
    logger.info("استقبال أمر /start من المستخدم %s", update.effective_user.id)

    # نحاول جلب ملف المواضيع
    url = GITHUB_RAW_BASE + "data/topics.json"  
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("خطأ أثناء جلب المواضيع من GitHub: %s", e)
        await update.message.reply_text("تعذّر تحميل المواضيع من GitHub.")
        return ConversationHandler.END

    try:
        topics_list = response.json()  # يتوقع أن يكون مصفوفة من المواضيع
    except json.JSONDecodeError as e:
        logger.error("ملف topics.json ليس بصيغة JSON صحيحة: %s", e)
        await update.message.reply_text("ملف المواضيع غير صالح (JSON).")
        return ConversationHandler.END

    if not topics_list:
        await update.message.reply_text("لا توجد مواضيع في ملف topics.json!")
        return ConversationHandler.END

    # سنخزن مسارات ملفات الأسئلة في قائمة ليسهل الوصول إليها
    context.user_data["file_paths"] = []
    keyboard = []

    # يفترض أن كل عنصر من topics_list يحتوي مفاتيح مثل: topicName, subTopics (وهي مصفوفة)
    for topic in topics_list:
        sub_topics = topic.get("subTopics", [])
        topic_name = topic.get("topicName", "Unnamed")
        for sub in sub_topics:
            sub_name = sub.get("name")
            file_path = sub.get("file")
            if not sub_name or not file_path:
                continue  # إذا كان هناك نقص في البيانات

            # خزّن المسار في قائمة user_data["file_paths"]
            index = len(context.user_data["file_paths"])
            context.user_data["file_paths"].append(file_path)

            # ضع الفهرس في callback_data
            callback_data = f"subtopic|{index}"
            button_text = f"{topic_name} - {sub_name}"

            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    if not keyboard:
        await update.message.reply_text("لا توجد مواضيع فرعية للاختيار منها.")
        return ConversationHandler.END

    # عرض الأزرار
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("اختر موضوعاً فرعياً للاختبار:", reply_markup=reply_markup)
    return SELECT_SUBTOPIC

async def select_subtopic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عند اختيار المستخدم لموضوع فرعي:
    1. يتم فكّ الفهرس من الـ callback_data واسترجاع المسار.
    2. يُطلب من المستخدم عدد الأسئلة.
    """
    query = update.callback_query
    await query.answer()

    logger.info("المستخدم %s اختار موضوعاً فرعياً.", query.from_user.id)

    data = query.data.split("|")
    if data[0] != "subtopic":
        await query.edit_message_text("اختيار غير صالح.")
        return ConversationHandler.END

    try:
        index = int(data[1])
    except ValueError:
        await query.edit_message_text("اختيار غير صالح (فهرس).")
        return ConversationHandler.END

    file_paths = context.user_data.get("file_paths", [])
    if index < 0 or index >= len(file_paths):
        await query.edit_message_text("اختيار غير صالح (خارج النطاق).")
        return ConversationHandler.END

    selected_file_path = file_paths[index]
    context.user_data["questions_file"] = selected_file_path

    await query.edit_message_text("كم عدد الأسئلة التي ترغب في الحصول عليها؟ (أدخل رقم)")
    return SELECT_NUM_QUESTIONS

async def select_num_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    بعد إدخال عدد الأسئلة:
    1. يقوم بتحميل ملف الأسئلة من GitHub.
    2. يختار عدد عشوائي منها.
    3. يرسلها على شكل استفتاءات Quiz.
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

    # جلب ملف الأسئلة
    questions_url = GITHUB_RAW_BASE + context.user_data["questions_file"]
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

    # خلط الأسئلة عشوائياً واختيار العدد المطلوب
    random.shuffle(questions_list)
    selected_questions = questions_list[:num_questions]

    context.user_data["selected_questions"] = selected_questions
    context.user_data["score"] = 0
    context.user_data["total"] = len(selected_questions)
    context.user_data["answered"] = 0
    context.user_data["polls"] = {}

    await update.message.reply_text("سيبدأ الاختبار الآن. أجب عن الأسئلة التالية:")

    # إرسال كل سؤال على شكل استفتاء (Poll) من نوع quiz
    for i, question in enumerate(selected_questions, start=1):
        q_text = question.get("question", f"سؤال #{i}")
        options = question.get("options", ["خيار 1", "خيار 2"])
        correct_id = question.get("answer", 0)  # الفهرس الصحيح
        explanation = question.get("explanation", "")

        # هنا نرسل الاستفتاء
        sent_poll = await update.message.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=q_text,
            options=options,
            type="quiz",
            correct_option_id=correct_id,
            is_anonymous=False,
            explanation=explanation,
            open_period=120,  # مدة متاحة للرد 120 ثانية، يمكن تغييرها
            parse_mode="HTML"  # لتفعيل تنسيق الـHTML في السؤال
        )
        poll_id = sent_poll.poll.id
        context.user_data["polls"][poll_id] = {
            "correct_option_id": correct_id,
            "answered": False
        }

    return WAITING_FOR_ANSWER

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    دالة لمعالجة إجابات الاستفتاء (quiz).
    عند اكتمال جميع الإجابات، تُرسل النتيجة للمستخدم.
    """
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    selected_options = poll_answer.option_ids
    user_id = poll_answer.user.id

    logger.info("إجابة جديدة من المستخدم %s على poll_id=%s, selected=%s",
                user_id, poll_id, selected_options)

    if "polls" in context.user_data and poll_id in context.user_data["polls"]:
        poll_data = context.user_data["polls"][poll_id]
        if poll_data["answered"]:
            logger.info("تمت الإجابة مسبقاً على هذا الاستفتاء.")
            return

        poll_data["answered"] = True

        if selected_options and selected_options[0] == poll_data["correct_option_id"]:
            context.user_data["score"] += 1

        context.user_data["answered"] += 1

        # إذا أكمل المستخدم الإجابة على جميع الأسئلة
        if context.user_data["answered"] == context.user_data["total"]:
            score = context.user_data["score"]
            total = context.user_data["total"]
            logger.info("انتهاء الاختبار للمستخدم %s. النتيجة: %d/%d", user_id, score, total)

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"انتهى الاختبار!\nنتيجتك: {score} من {total}"
            )
            # تنظيف بيانات الجلسة
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
    # <-- ضع التوكن الخاص ببوتك هنا -->
    TOKEN = "7633072361:AAHnzREYTKKRFiTiq7HDZBalnwnmgivY8_I"

    logger.info("بدء تشغيل البوت...")
    application = Application.builder().token(TOKEN).build()

    # إعداد ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_SUBTOPIC: [CallbackQueryHandler(select_subtopic)],
            SELECT_NUM_QUESTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_num_questions)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # نضيف ConversationHandler إلى التطبيق
    application.add_handler(conv_handler)

    # نضيف PollAnswerHandler لمعالجة إجابات الاستفتاء
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    logger.info("البوت يعمل الآن. ارسل /start للبدء.")
    application.run_polling()

if __name__ == "__main__":
    main()
