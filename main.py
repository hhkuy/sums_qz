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

# مراحل المحادثة
SELECT_SUBTOPIC, SELECT_NUM_QUESTIONS, WAITING_FOR_ANSWER = range(3)

# الرابط الأساسي للوصول إلى ملفات GitHub (يجب تعديل اسم المستخدم والمستودع حسب حالتك)
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/hhkuy/Sums_Q/main/data/"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عند تشغيل /start يقوم البوت بتحميل ملف topics.json من GitHub وعرض قائمة المواضيع الفرعية للمستخدم.
    """
    logger.info("تم استقبال أمر /start من المستخدم: %s", update.effective_user.id)

    url = GITHUB_RAW_BASE + "topics.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("خطأ أثناء جلب المواضيع من GitHub: %s", e)
        await update.message.reply_text("حدث خطأ أثناء تحميل المواضيع من GitHub.")
        return ConversationHandler.END

    try:
        topics_data = response.json()
    except json.JSONDecodeError as e:
        logger.error("ملف topics.json غير صالح JSON: %s", e)
        await update.message.reply_text("ملف المواضيع غير صالح (JSON).")
        return ConversationHandler.END

    main_topics = topics_data.get("main_topics", [])
    if not main_topics:
        # إذا كان لا يوجد أي main_topics فسيظهر للمستخدم تنبيه
        await update.message.reply_text("لا توجد مواضيع رئيسية في ملف topics.json!")
        return ConversationHandler.END

    # بناء قائمة أزرار للمواضيع الفرعية
    keyboard = []
    for main_topic in main_topics:
        subtopics = main_topic.get("subtopics", [])
        for sub in subtopics:
            if "name" in sub and "questions_file" in sub:
                button_text = f"{main_topic['name']} - {sub['name']}"
                callback_data = f"subtopic|{sub['questions_file']}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    if not keyboard:
        # إذا لم يكن هناك أي مواضيع فرعية
        await update.message.reply_text("لا توجد مواضيع فرعية للاختيار منها.")
        return ConversationHandler.END

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("اختر موضوعاً فرعياً للاختبار:", reply_markup=reply_markup)

    # ننتقل للمرحلة التالية من المحادثة
    return SELECT_SUBTOPIC

async def select_subtopic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    بعد اختيار المستخدم للموضوع الفرعي، يتم تخزين اسم ملف الأسئلة في بيانات الجلسة وطلب إدخال عدد الأسئلة.
    """
    query = update.callback_query
    await query.answer()
    logger.info("قام المستخدم: %s باختيار موضوع فرعي.", query.from_user.id)

    data = query.data.split("|")
    if data[0] != "subtopic":
        await query.edit_message_text("اختيار غير صحيح.")
        return ConversationHandler.END

    context.user_data["questions_file"] = data[1]
    await query.edit_message_text("كم عدد الأسئلة التي ترغب بها للاختبار؟ (أدخل رقم)")
    return SELECT_NUM_QUESTIONS

async def select_num_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    بعد إدخال عدد الأسئلة، يقوم البوت بتحميل ملف الأسئلة من GitHub واختيار عدد عشوائي منها ثم إرسالها على شكل استفتاءات (polls).
    """
    num_text = update.message.text.strip()
    logger.info("المستخدم: %s أدخل عدد الأسئلة: %s", update.effective_user.id, num_text)

    try:
        num_questions = int(num_text)
        if num_questions <= 0:
            await update.message.reply_text("يرجى إدخال رقم موجب.")
            return SELECT_NUM_QUESTIONS
    except ValueError:
        await update.message.reply_text("يرجى إدخال رقم صحيح.")
        return SELECT_NUM_QUESTIONS

    context.user_data["num_questions"] = num_questions

    # تحميل ملف الأسئلة من GitHub
    questions_url = GITHUB_RAW_BASE + context.user_data["questions_file"]
    logger.info("جلب الأسئلة من الملف: %s", questions_url)
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
    # لتخزين معرفات الاستفتاءات والبيانات الخاصة بها
    context.user_data["polls"] = {}

    await update.message.reply_text("يبدأ الاختبار الآن. أجب عن الأسئلة التالية:")

    # إرسال كل سؤال على شكل استفتاء من نوع quiz
    for i, question in enumerate(selected_questions, start=1):
        q_text = question.get("question", f"سؤال #{i} (لم يتم العثور على نص السؤال)")
        options = question.get("options", ["خيار 1", "خيار 2"])
        correct_id = question.get("answer", 0)  # مؤشر الإجابة الصحيحة الافتراضي 0
        explanation = question.get("explanation", "")

        sent_poll = await update.message.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=q_text,
            options=options,
            type="quiz",
            correct_option_id=correct_id,
            is_anonymous=False,  # لجعل الإجابات غير مجهولة لتتبعها
            explanation=explanation,
            open_period=60,  # مدة فتح الاستفتاء (بالثواني) - يمكن التعديل أو حذفها
            parse_mode="HTML"
        )
        poll_id = sent_poll.poll.id
        context.user_data["polls"][poll_id] = {
            "correct_option_id": correct_id,
            "answered": False,
        }
    return WAITING_FOR_ANSWER

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عند استلام إجابة من المستخدم على استفتاء ما، يتم التحقق من صحة الإجابة وتحديث النتيجة.
    عند انتهاء جميع الأسئلة يُرسل البوت النتيجة النهائية للمستخدم.
    """
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    selected_options = poll_answer.option_ids
    user_id = poll_answer.user.id

    logger.info("Poll Answer من المستخدم %s - poll_id=%s - selected=%s", user_id, poll_id, selected_options)

    if "polls" in context.user_data and poll_id in context.user_data["polls"]:
        poll_data = context.user_data["polls"][poll_id]
        if poll_data["answered"]:
            logger.info("تمت الإجابة مسبقاً على هذا الـ poll_id.")
            return  # في حال تم الإجابة مسبقاً على هذا السؤال
        poll_data["answered"] = True

        # التحقق من الإجابة الصحيحة
        if selected_options and selected_options[0] == poll_data["correct_option_id"]:
            context.user_data["score"] += 1
        context.user_data["answered"] += 1

        # إذا أجاب المستخدم على جميع الأسئلة يتم إرسال النتيجة
        if context.user_data["answered"] == context.user_data["total"]:
            score = context.user_data["score"]
            total = context.user_data["total"]
            logger.info("انتهى الاختبار للمستخدم %s. النتيجة %d من %d.", user_id, score, total)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"انتهى الاختبار!\nنتيجتك: {score} من {total}"
            )
            # تنظيف بيانات الجلسة
            context.user_data.clear()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    في حال استخدام أمر /cancel يتم إلغاء الاختبار.
    """
    logger.info("المستخدم %s أرسل /cancel", update.effective_user.id)
    await update.message.reply_text("تم إلغاء الاختبار.")
    return ConversationHandler.END

def main():
    """
    الدالة الرئيسية لتشغيل البوت باستخدام التوكن المُعطى.
    """
    # ضَع التوكن الخاص بالبوت هنا:
    TOKEN = "7633072361:AAHnzREYTKKRFiTiq7HDZBalnwnmgivY8_I"

    logger.info("بدء تشغيل البوت...")
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_SUBTOPIC: [CallbackQueryHandler(select_subtopic)],
            SELECT_NUM_QUESTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_num_questions)],
            # المرحلة الأخيرة WAITING_FOR_ANSWER يتم التعامل معها عبر PollAnswerHandler
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # إضافة ConversationHandler
    application.add_handler(conv_handler)
    # إضافة PollAnswerHandler لمعالجة إجابات الاستفتاءات
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    # بدء تشغيل البوت
    logger.info("البوت يعمل الآن... انتظر الأوامر.")
    application.run_polling()

if __name__ == "__main__":
    main()
