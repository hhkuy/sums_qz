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

# إعداد تسجيل الأخطاء
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# مراحل المحادثة
SELECT_SUBTOPIC, SELECT_NUM_QUESTIONS, WAITING_FOR_ANSWER = range(3)
MAX_QUESTIONS = 20  # الحد الأقصى لعدد الأسئلة

# الرابط الأساسي للوصول إلى ملفات الـ GitHub
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/hhkuy/Sums_Q/main/data/"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = requests.get(f"{GITHUB_RAW_BASE}topics.json")
        response.raise_for_status()
        topics_data = response.json()
    except Exception as e:
        logger.error(f"خطأ في تحميل المواضيع: {str(e)}")
        await update.message.reply_text("❌ حدث خطأ أثناء تحميل المواضيع.")
        return ConversationHandler.END

    if "main_topics" not in topics_data:
        await update.message.reply_text("⚠️ ملف المواضيع غير صحيح.")
        return ConversationHandler.END

    keyboard = []
    for main_topic in topics_data["main_topics"]:
        if "subtopics" not in main_topic:
            continue
        for sub in main_topic["subtopics"]:
            if "name" not in sub or "questions_file" not in sub:
                continue
            button_text = f"{main_topic.get('name', '')} - {sub['name']}"
            callback_data = f"subtopic|{sub['questions_file']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    if not keyboard:
        await update.message.reply_text("⚠️ لا توجد مواضيع متاحة حالياً.")
        return ConversationHandler.END

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📚 اختر موضوعاً فرعياً للاختبار:", reply_markup=reply_markup)
    return SELECT_SUBTOPIC

async def select_subtopic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("|")
    if len(data) != 2 or data[0] != "subtopic":
        await query.edit_message_text("⚠️ اختيار غير صحيح.")
        return ConversationHandler.END
    
    context.user_data["questions_file"] = data[1]
    await query.edit_message_text("❓ كم عدد الأسئلة التي ترغب بها؟ (1-20)")
    return SELECT_NUM_QUESTIONS

async def select_num_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        num_questions = int(update.message.text.strip())
        if num_questions < 1 or num_questions > MAX_QUESTIONS:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"⚠️ الرجاء إدخال رقم بين 1 و {MAX_QUESTIONS}.")
        return SELECT_NUM_QUESTIONS

    # تحميل الأسئلة من GitHub
    try:
        questions_url = f"{GITHUB_RAW_BASE}{context.user_data['questions_file']}"
        response = requests.get(questions_url)
        response.raise_for_status()
        questions_list = response.json()
    except Exception as e:
        logger.error(f"خطأ في تحميل الأسئلة: {str(e)}")
        await update.message.reply_text("❌ حدث خطأ في تحميل الأسئلة.")
        return ConversationHandler.END

    # التحقق من صحة هيكل الأسئلة
    valid_questions = []
    for q in questions_list:
        if all(key in q for key in ["question", "options", "answer"]) and len(q["options"]) >= 2:
            valid_questions.append(q)
    
    if not valid_questions:
        await update.message.reply_text("⚠️ لا توجد أسئلة صالحة في الملف.")
        return ConversationHandler.END
    
    num_questions = min(num_questions, len(valid_questions))
    random.shuffle(valid_questions)
    
    # حفظ البيانات الضرورية
    context.user_data.update({
        "questions": valid_questions[:num_questions],
        "score": 0,
        "total": num_questions,
        "current_question": 0,
        "polls": {}
    })

    await send_next_question(update, context)
    return WAITING_FOR_ANSWER

async def send_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    index = user_data["current_question"]
    
    if index >= user_data["total"]:
        await show_final_results(update, context)
        return
    
    question = user_data["questions"][index]
    try:
        sent_poll = await update.message.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=question["question"],
            options=question["options"],
            type="quiz",
            correct_option_id=question["answer"],
            is_anonymous=False,
            explanation=question.get("explanation", ""),
            open_period=30,
        )
        user_data["polls"][sent_poll.poll.id] = {
            "correct": question["answer"],
            "answered": False
        }
    except Exception as e:
        logger.error(f"خطأ في إرسال السؤال: {str(e)}")
        await update.message.reply_text("⚠️ حدث خطأ في إرسال السؤال.")

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id
    
    if poll_id not in user_data.get("polls", {}):
        return
    
    poll_data = user_data["polls"][poll_id]
    if poll_data["answered"]:
        return
    
    # تحديث النتيجة
    if poll_answer.option_ids and poll_answer.option_ids[0] == poll_data["correct"]:
        user_data["score"] += 1
    
    poll_data["answered"] = True
    user_data["current_question"] += 1
    
    # إرسال السؤال التالي أو النتائج
    if user_data["current_question"] < user_data["total"]:
        await send_next_question(update, context)
    else:
        await show_final_results(update, context)

async def show_final_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    score = user_data["score"]
    total = user_data["total"]
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🏁 انتهى الاختبار!\nنتيجتك: {score}/{total} ({round(score/total*100)}%)"
    )
    context.user_data.clear()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء الاختبار.")
    context.user_data.clear()
    return ConversationHandler.END

def main():
    TOKEN = "7633072361:AAHnzREYTKKRFiTiq7HDZBalnwnmgivY8_I"
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_SUBTOPIC: [CallbackQueryHandler(select_subtopic)],
            SELECT_NUM_QUESTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_num_questions)],
            WAITING_FOR_ANSWER: [
                PollAnswerHandler(handle_poll_answer),
                CommandHandler("cancel", cancel)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    main()
