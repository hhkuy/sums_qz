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

# إعداد تسجيل الأخطاء
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# مراحل المحادثة
SELECT_SUBTOPIC, SELECT_NUM_QUESTIONS, WAITING_FOR_ANSWER = range(3)

# الرابط الأساسي للوصول إلى ملفات GitHub (مجلد data في repo الخاص بك)
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/hhkuy/Sums_Q/main/data/"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عند تشغيل /start يقوم البوت بتحميل ملف topics.json من GitHub وعرض قائمة المواضيع الفرعية للمستخدم.
    """
    url = GITHUB_RAW_BASE + "topics.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("خطأ أثناء جلب المواضيع: %s", e)
        await update.message.reply_text("حدث خطأ أثناء تحميل المواضيع من GitHub.")
        return ConversationHandler.END

    topics_data = response.json()

    # بناء قائمة أزرار للمواضيع الفرعية
    keyboard = []
    # نفترض أن بنية topics.json كالتالي:
    # {
    #   "main_topics": [
    #       {
    #           "name": "الموضوع الرئيسي",
    #           "subtopics": [
    #               {
    #                   "name": "الموضوع الفرعي",
    #                   "questions_file": "اسم_ملف_الأسئلة.json"
    #               },
    #               ...
    #           ]
    #       },
    #       ...
    #   ]
    # }
    for main_topic in topics_data.get("main_topics", []):
        for sub in main_topic.get("subtopics", []):
            button_text = f"{main_topic['name']} - {sub['name']}"
            # تمرير اسم ملف الأسئلة ضمن بيانات callback
            callback_data = f"subtopic|{sub['questions_file']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("اختر موضوعاً فرعياً للاختبار:", reply_markup=reply_markup)
    return SELECT_SUBTOPIC

async def select_subtopic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    بعد اختيار المستخدم للموضوع الفرعي، يتم تخزين اسم ملف الأسئلة في بيانات الجلسة وطلب إدخال عدد الأسئلة.
    """
    query = update.callback_query
    await query.answer()

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
    try:
        num_questions = int(num_text)
    except ValueError:
        await update.message.reply_text("يرجى إدخال رقم صحيح.")
        return SELECT_NUM_QUESTIONS

    context.user_data["num_questions"] = num_questions

    # تحميل ملف الأسئلة من GitHub
    questions_url = GITHUB_RAW_BASE + context.user_data["questions_file"]
    try:
        response = requests.get(questions_url)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("خطأ أثناء جلب الأسئلة: %s", e)
        await update.message.reply_text("حدث خطأ أثناء تحميل الأسئلة من GitHub.")
        return ConversationHandler.END

    questions_list = response.json()
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
    for question in selected_questions:
        q_text = question["question"]
        options = question["options"]
        correct_id = question["answer"]  # مؤشر الإجابة الصحيحة

        sent_poll = await update.message.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=q_text,
            options=options,
            type="quiz",
            correct_option_id=correct_id,
            is_anonymous=False,  # لجعل الإجابات غير مجهولة لتتبعها
            explanation=question.get("explanation", ""),
            open_period=60,  # مدة فتح الاستفتاء (يمكن التعديل)
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

    if "polls" in context.user_data and poll_id in context.user_data["polls"]:
        poll_data = context.user_data["polls"][poll_id]
        if poll_data["answered"]:
            return  # في حال تم الإجابة مسبقاً على هذا السؤال
        poll_data["answered"] = True

        if selected_options and selected_options[0] == poll_data["correct_option_id"]:
            context.user_data["score"] += 1
        context.user_data["answered"] += 1

        # إذا أجاب المستخدم على جميع الأسئلة يتم إرسال النتيجة
        if context.user_data["answered"] == context.user_data["total"]:
            score = context.user_data["score"]
            total = context.user_data["total"]
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
    await update.message.reply_text("تم إلغاء الاختبار.")
    return ConversationHandler.END

def main():
    """
    الدالة الرئيسية لتشغيل البوت باستخدام التوكن المُعطى.
    """
    TOKEN = "7633072361:AAHnzREYTKKRFiTiq7HDZBalnwnmgivY8_I"
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_SUBTOPIC: [CallbackQueryHandler(select_subtopic)],
            SELECT_NUM_QUESTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_num_questions)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    application.add_handler(conv_handler)
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    logger.info("البوت يعمل الآن...")
    application.run_polling()

if __name__ == "__main__":
    main()
