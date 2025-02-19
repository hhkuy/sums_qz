# main.py
import json
import random
from uuid import uuid4
import requests
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# Configuration
TOKEN = "7633072361:AAHnzREYTKKRFiTiq7HDZBalnwnmgivY8_I"
BOT_USERNAME = "@SumsQuestionsBot"
GITHUB_BASE_URL = "https://raw.githubusercontent.com/hhkuy/Sums_Q/main/"

# States
SELECT_TOPIC, SELECT_SUBTOPIC, SELECT_QUESTION_COUNT, TAKE_QUIZ = range(4)

def get_topics_data():
    url = f"{GITHUB_BASE_URL}topics.json"
    response = requests.get(url)
    return response.json() if response.status_code == 200 else []

def get_subtopics(topic_name):
    topics = get_topics_data()
    for topic in topics:
        if topic['topicName'] == topic_name:
            return topic['subTopics']
    return []

def load_questions(subtopic_file):
    try:
        url = f"{GITHUB_BASE_URL}{subtopic_file}"
        response = requests.get(url)
        return response.json() if response.status_code == 200 else []
    except Exception as e:
        print(f"Error loading questions: {e}")
        return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    topics = get_topics_data()
    keyboard = [
        [InlineKeyboardButton(topic["topicName"], callback_data=f"topic_{i}")]
        for i, topic in enumerate(topics)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "مرحبا! اختر الموضوع:",
        reply_markup=reply_markup
    )
    return SELECT_TOPIC

async def select_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    topic_index = int(query.data.split('_')[1])
    topics = get_topics_data()
    topic = topics[topic_index]
    context.user_data['selected_topic'] = topic
    
    subtopics = topic['subTopics']
    keyboard = [
        [InlineKeyboardButton(st['name'], callback_data=f"subtopic_{i}")]
        for i, st in enumerate(subtopics)
    ]
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_topics")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"اختر الموضوع الفرعي لـ {topic['topicName']}:",
        reply_markup=reply_markup
    )
    return SELECT_SUBTOPIC

async def select_subtopic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_topics":
        return await start(update, context)
    
    subtopic_index = int(query.data.split('_')[1])
    topic = context.user_data['selected_topic']
    subtopic = topic['subTopics'][subtopic_index]
    context.user_data['selected_subtopic'] = subtopic
    
    await query.edit_message_text(
        f"أدخل عدد الأسئلة التي تريدها (1-{len(load_questions(subtopic['file']))}):"
    )
    return SELECT_QUESTION_COUNT

async def select_question_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    subtopic = context.user_data['selected_subtopic']
    questions = load_questions(subtopic['file'])
    
    try:
        num_questions = int(update.message.text)
        max_questions = len(questions)
        if 1 <= num_questions <= max_questions:
            selected_questions = random.sample(questions, num_questions)
            context.user_data['quiz'] = {
                'questions': selected_questions,
                'current_question': 0,
                'score': 0,
                'quiz_id': str(uuid4())
            }
            
            return await send_question(update, context)
        else:
            await update.message.reply_text(f"الرجاء إدخال رقم بين 1 و {max_questions}")
            return SELECT_QUESTION_COUNT
    except ValueError:
        await update.message.reply_text("الرجاء إدخال رقم صحيح")
        return SELECT_QUESTION_COUNT

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    quiz = context.user_data['quiz']
    current = quiz['current_question']
    question = quiz['questions'][current]
    
    keyboard = [
        [InlineKeyboardButton(opt, callback_data=f"answer_{i}")]
        for i, opt in enumerate(question['options'])
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            f"السؤال {current + 1}:\n{question['question']}",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    else:
        await update.callback_query.edit_message_text(
            f"السؤال {current + 1}:\n{question['question']}",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    
    return TAKE_QUIZ

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    quiz = context.user_data['quiz']
    current = quiz['current_question']
    question = quiz['questions'][current]
    selected_answer = int(query.data.split('_')[1])
    
    # Save user answer
    question['userAnswer'] = selected_answer
    
    # Check answer
    if selected_answer == question['answer']:
        quiz['score'] += 1
    
    # Move to next question
    quiz['current_question'] += 1
    
    if quiz['current_question'] < len(quiz['questions']):
        return await send_question(update, context)
    else:
        return await show_results(update, context)

async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    quiz = context.user_data['quiz']
    score = quiz['score']
    total = len(quiz['questions'])
    
    result_text = f"النتيجة النهائية: {score}/{total}\n\n"
    
    for i, q in enumerate(quiz['questions']):
        result_text += f"السؤال {i+1}:\n"
        result_text += f"إجابتك: {q['options'][q['userAnswer']]}\n"
        result_text += f"الإجابة الصحيحة: {q['answerText']}\n"
        result_text += f"التفسير: {q['explanation']}\n\n"
    
    await update.callback_query.edit_message_text(result_text)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        'تم الإلغاء',
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

def main() -> None:
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECT_TOPIC: [CallbackQueryHandler(select_topic, pattern=r'^topic_\d+$')],
            SELECT_SUBTOPIC: [
                CallbackQueryHandler(select_subtopic, pattern=r'^subtopic_\d+$'),
                CallbackQueryHandler(select_topic, pattern=r'^back_to_topics$')
            ],
            SELECT_QUESTION_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_question_count)],
            TAKE_QUIZ: [CallbackQueryHandler(handle_answer, pattern=r'^answer_\d+$')]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    
    # Handle mentions in groups
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(rf'@{BOT_USERNAME}'),
        start
    ))

    application.run_polling()

if __name__ == '__main__':
    main()
