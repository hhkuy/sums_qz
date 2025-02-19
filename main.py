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

# إعداد مستوى تسجيل المعلومات والأخطاء
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# مراحل المحادثة
SELECT_SUBTOPIC, SELECT_NUM_QUESTIONS, WAITING_FOR_ANSWER = range(3)

# الرابط الأساسي للوصول إلى ملفاتك في GitHub
# لاحظ أننا لم نضع "/data/" في النهاية؛
# لأن ملفاتك في topics.json تبدأ بـ "data/..."
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/hhkuy/Sums_Q/main/"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يعالج أمر /start:
    1. يقوم بتحميل ملف topics.json من GitHub.
    2. يستخرج قائمة المواضيع الرئيسية (جذر المصفوفة).
    3. يبني أزرار الاختيار من subTopics.
    """
    logger.info("تم استقبال أمر /start من المستخدم %s", update.effective_user.id)

    # رابط ملف المواضيع
    url = GITHUB_RAW_BASE + "data/topics.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("خطأ أثناء جلب المواضيع من GitHub: %s", e)
        await update.message.reply_text("حدث خطأ أثناء تحميل المواضيع من GitHub.")
        return ConversationHandler.END

    # محاولة تحويل الاستجابة إلى JSON
    try:
        topics_list = response.json()  # بناءً على الشكل الذي عرضته أنت (مصـفوفة)
    except json.JSONDecodeError as e:
        logger.error("ملف topics.json غير صالح JSON: %s", e)
        await update.message.reply_text("ملف المواضيع غير صالح (JSON).")
        return ConversationHandler.END

    if not topics_list:
        # إذا كانت المصفوفة فارغة
        await update.message.reply_text("لا توجد مواضيع في ملف topics.json!")
        return ConversationHandler.END

    # بناء قائمة أزرار للمواضيع الفرعية
    keyboard = []
    for topic in topics_list:
        # كل عنصر يحتوي على مفاتيح مثل: topicName, description, subTopics (قائمة)
        sub_topics = topic.get("subTopics", [])
        for sub in sub_topics:
            # من خلال بنية JSON:  "name": "<subtopic name>", "file": "<path to JSON>"
            sub_name = sub.get("name")
            file_path = sub.get("file")

            if not sub_name or not file_path:
                continue  # تجاوز أي عنصر ناقص

            # نص الزر
            button_text = f"{topic['topicName']} - {sub_name}"

            # نمرر مسار الملف عبر callback_data حتى نعرف أي ملف سنقرأه لاحقًا
            callback_data = f"subtopic|{file_path}"

            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    if not keyboard:
        # إذا لم يكن هناك أي مواضيع فرعية
        await update.message.reply_text("لا توجد مواضيع فرعية للاختيار منها.")
        return ConversationHandler.END

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("اختر موضوعاً فرعياً للاختبار:", reply_markup=reply_markup)

    return SELECT_SUBTOPIC

async def select_subtopic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يعالج اختيار الموضوع الفرعي:
    1. يحفظ اسم (مسار) ملف الأسئلة في user_data.
    2. يطلب من المستخدم إدخال عدد الأسئلة.
    """
    query = update.callback_query
    await query.answer()

    logger.info("قام المستخدم %s باختيار موضوع فرعي", query.from_user.id)

    data = query.data.split("|")
    if data[0] != "subtopic":
        await query.edit_message_text("اختيار غير صحيح.")
        return ConversationHandler.END

    # حفظ مسار ملف الأسئلة
    context.user_data["questions_file"] = data[1]
    await query.edit_message_text("كم عدد الأسئلة التي ترغب بها للاختبار؟ (أدخل رقم)")

    return SELECT_NUM_QUESTIONS

async def select_num_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    بعد إدخال عدد الأسئلة:
    1. تحميل ملف الأسئلة من GitHub.
    2. اختيار عدد عشوائي منها.
    3. إرسالها على شكل استفتاء (Poll) من نوع quiz.
    """
    num_text = update.message.text.strip()
    logger.info("المستخدم %s أدخل عدد الأسئلة: %s", update.effective_user.id, num_text)

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

    # اختيار عشوائي للأسئلة
    random.shuffle(questions_list)
    selected_questions = questions_list[:num_questions]

    # حفظ تفاصيل الاختبار في user_data
    context.user_data["selected_questions"] = selected_questions
    context.user_data["score"] = 0
    context.user_data["total"] = len(selected_questions)
    context.user_data["answered"] = 0
    context.user_data["polls"] = {}  # لتخزين poll_id مع بيانات السؤال

    await update.message.reply_text("يبدأ الاختبار الآن. أجب عن الأسئلة التالية:")

    # إرسال كل سؤال
    for i, question in enumerate(selected_questions, start=1):
        q_text = question.get("question", f"سؤال #{i} (لا يوجد نص)")
        options = question.get("options", ["خيار 1", "خيار 2"])
        correct_id = question.get("answer", 0)  # المؤشر الافتراضي للإجابة الصحيحة
        explanation = question.get("explanation", "")

        sent_poll = await update.message.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=q_text,
            options=options,
            type="quiz",
            correct_option_id=correct_id,
            is_anonymous=False,  # لجعل الإجابات غير مجهولة لتتبع من يجيب
            explanation=explanation,
            open_period=60,  # مدة الاستفتاء (بالثواني) ويمكن إلغاؤه أو تعديله
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
    يعالج إجابة المستخدم على الاستفتاء (quiz).
    عند اكتمال إجابات جميع الأسئلة، يرسل النتيجة النهائية.
    """
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    selected_options = poll_answer.option_ids
    user_id = poll_answer.user.id

    logger.info("استلام إجابة من المستخدم %s على poll_id=%s, options=%s", user_id, poll_id, selected_options)

    # التأكد من وجود poll_id في بيانات المستخدم
    if "polls" in context.user_data and poll_id in context.user_data["polls"]:
        poll_data = context.user_data["polls"][poll_id]
        if poll_data["answered"]:
            # تمّت الإجابة مسبقًا
            logger.info("تمت الإجابة على هذا السؤال مسبقاً من قبل المستخدم %s", user_id)
            return

        poll_data["answered"] = True

        # التحقق من صحة الإجابة
        if selected_options and selected_options[0] == poll_data["correct_option_id"]:
            context.user_data["score"] += 1

        context.user_data["answered"] += 1

        # إذا وصلنا لنهاية جميع الأسئلة
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
    يعالج أمر /cancel لإلغاء الاختبار.
    """
    logger.info("المستخدم %s أرسل /cancel", update.effective_user.id)
    await update.message.reply_text("تم إلغاء الاختبار.")
    return ConversationHandler.END

def main():
    """
    الدالة الرئيسية لتشغيل البوت بواسطة التوكن.
    """
    TOKEN = "7633072361:AAHnzREYTKKRFiTiq7HDZBalnwnmgivY8_I"  # ← ضع التوكن الخاص بك هنا

    logger.info("بدء تشغيل البوت...")
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_SUBTOPIC: [CallbackQueryHandler(select_subtopic)],
            SELECT_NUM_QUESTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_num_questions)],
            # PollAnswerHandler سيعمل في أي وقت يتلقى فيه إجابة على الاستفتاء
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # إضافة ConversationHandler
    application.add_handler(conv_handler)

    # إضافة PollAnswerHandler لمعالجة إجابات الاستفتاءات (quiz)
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    logger.info("البوت يعمل الآن... جاهز لاستقبال الأوامر.")
    application.run_polling()

if __name__ == "__main__":
    main()
