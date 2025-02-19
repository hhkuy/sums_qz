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

# إعدادات التسجيل
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# تعريف مراحل المحادثة
SELECT_TOPIC, SELECT_SUBTOPIC, SELECT_NUM_QUESTIONS, WAITING_FOR_ANSWER = range(4)

# رابط قاعدة ملفات GitHub
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/hhkuy/Sums_Q/main/"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة المواضيع الرئيسية مع زر إلغاء"""
    await show_topics(update, context)
    return SELECT_TOPIC

async def show_topics(update: Update, context: ContextTypes.DEFAULT_TYPE, edit_message: bool = False):
    """عرض/تحديث قائمة المواضيع الرئيسية"""
    try:
        response = requests.get(f"{GITHUB_RAW_BASE}data/topics.json")
        response.raise_for_status()
        topics_data = response.json()
    except Exception as e:
        logger.error(f"خطأ في جلب المواضيع: {e}")
        await update.message.reply_text("حدث خطأ في تحميل المواضيع!")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(topic["topicName"], callback_data=f"topic|{idx}")]
        for idx, topic in enumerate(topics_data)
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if edit_message and update.callback_query:
        await update.callback_query.edit_message_text(
            "اختر الموضوع الرئيسي:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "مرحبا! اختر الموضوع الرئيسي:",
            reply_markup=reply_markup
        )

async def show_subtopics(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_idx: int):
    """عرض المواضيع الفرعية لموضوع معين"""
    query = update.callback_query
    await query.answer()

    try:
        response = requests.get(f"{GITHUB_RAW_BASE}data/topics.json")
        response.raise_for_status()
        topics_data = response.json()
        topic = topics_data[topic_idx]
    except Exception as e:
        logger.error(f"خطأ في جلب المواضيع الفرعية: {e}")
        await query.edit_message_text("حدث خطأ في تحميل المواضيع الفرعية!")
        return ConversationHandler.END

    keyboard = []
    for sub_idx, subtopic in enumerate(topic["subTopics"]):
        keyboard.append([
            InlineKeyboardButton(
                subtopic["name"],
                callback_data=f"subtopic|{topic_idx}|{sub_idx}"
            )
        ])
    
    # إضافة زر الرجوع
    keyboard.append([InlineKeyboardButton("رجوع", callback_data="back_to_topics")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"اختر الموضوع الفرعي لـ {topic['topicName']}:",
        reply_markup=reply_markup
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أحداث الأزرار"""
    query = update.callback_query
    data = query.data.split("|")

    if data[0] == "topic":
        await show_subtopics(update, context, int(data[1]))
        return SELECT_SUBTOPIC

    elif data[0] == "subtopic":
        topic_idx = int(data[1])
        sub_idx = int(data[2])
        
        try:
            response = requests.get(f"{GITHUB_RAW_BASE}data/topics.json")
            topics_data = response.json()
            file_path = topics_data[topic_idx]["subTopics"][sub_idx]["file"]
            context.user_data["selected_file"] = file_path
            await query.edit_message_text("أدخل عدد الأسئلة المطلوبة:")
            return SELECT_NUM_QUESTIONS
        except Exception as e:
            logger.error(f"خطأ في اختيار الموضوع الفرعي: {e}")
            await query.edit_message_text("حدث خطأ في اختيار الموضوع الفرعي!")
            return ConversationHandler.END

    elif data[0] == "back_to_topics":
        await show_topics(update, context, edit_message=True)
        return SELECT_TOPIC

    await query.answer()
    return SELECT_TOPIC

async def handle_num_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة عدد الأسئلة وإرسالها"""
    try:
        num_questions = int(update.message.text)
        if num_questions < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("الرجاء إدخال رقم صحيح موجب!")
        return SELECT_NUM_QUESTIONS

    file_path = context.user_data.get("selected_file")
    if not file_path:
        await update.message.reply_text("حدث خطأ في تحديد الملف!")
        return ConversationHandler.END

    try:
        response = requests.get(f"{GITHUB_RAW_BASE}{file_path}")
        questions = response.json()
        random.shuffle(questions)
        selected_questions = questions[:num_questions]
    except Exception as e:
        logger.error(f"خطأ في جلب الأسئلة: {e}")
        await update.message.reply_text("حدث خطأ في تحميل الأسئلة!")
        return ConversationHandler.END

    context.user_data["questions"] = selected_questions
    context.user_data["score"] = 0
    context.user_data["current_question"] = 0

    await send_next_question(update, context)
    return WAITING_FOR_ANSWER

async def send_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال السؤال التالي"""
    questions = context.user_data["questions"]
    current_idx = context.user_data["current_question"]
    
    if current_idx >= len(questions):
        await show_final_results(update, context)
        return ConversationHandler.END

    question = questions[current_idx]
    options = question["options"]
    
    await update.message.reply_poll(
        question=question["question"],
        options=options,
        type="quiz",
        correct_option_id=question["answer"],
        explanation=question.get("explanation", ""),
        is_anonymous=False,
        open_period=60
    )

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تتبع الإجابات وتحديث النتائج"""
    answer = update.poll_answer
    poll_id = answer.poll_id
    
    if context.user_data.get("current_question", 0) < len(context.user_data["questions"]):
        question = context.user_data["questions"][context.user_data["current_question"]]
        if answer.option_ids[0] == question["answer"]:
            context.user_data["score"] += 1
        
        context.user_data["current_question"] += 1
        await send_next_question(update.effective_user, context)

async def show_final_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض النتائج النهائية"""
    total = len(context.user_data["questions"])
    score = context.user_data["score"]
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"انتهى الاختبار!\nالنتيجة: {score}/{total}"
    )
    context.user_data.clear()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء الاختبار"""
    await update.message.reply_text("تم إلغاء الاختبار.")
    context.user_data.clear()
    return ConversationHandler.END

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    TOKEN = "7633072361:AAHnzREYTKKRFiTiq7HDZBalnwnmgivY8_I"
    
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECT_TOPIC: [CallbackQueryHandler(handle_callback)],
            SELECT_SUBTOPIC: [CallbackQueryHandler(handle_callback)],
            SELECT_NUM_QUESTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_num_questions)
            ],
            WAITING_FOR_ANSWER: [PollAnswerHandler(handle_poll_answer)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
