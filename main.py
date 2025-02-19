import telebot
import requests
import json
import random

# استبدل 'YOUR_BOT_TOKEN' بالتوكن الخاص ببوتك
bot = telebot.TeleBot('YOUR_BOT_TOKEN')

# رابط المستودع على GitHub
GITHUB_REPO_URL = "https://raw.githubusercontent.com/username/repo/main/"

# تحميل ملف topics.json
topics_url = GITHUB_REPO_URL + "data/topics.json"
response = requests.get(topics_url)
topics_data = response.json()

# حالة المستخدم
user_state = {}

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    user_state[user_id] = {"step": "select_topic"}
    show_topics(message)

def show_topics(message):
    user_id = message.chat.id
    markup = telebot.types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True)
    for topic in topics_data:
        markup.add(telebot.types.KeyboardButton(topic['topicName']))
    bot.send_message(user_id, "اختر الموضوع:", reply_markup=markup)

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "select_topic")
def handle_topic_selection(message):
    user_id = message.chat.id
    selected_topic = message.text
    user_state[user_id]["selected_topic"] = selected_topic
    user_state[user_id]["step"] = "select_subtopic"

    # البحث عن الموضوع المحدد
    topic = next((t for t in topics_data if t['topicName'] == selected_topic), None)
    if topic:
        markup = telebot.types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True)
        for sub_topic in topic['subTopics']:
            markup.add(telebot.types.KeyboardButton(sub_topic['name']))
        bot.send_message(user_id, "اختر الموضوع الفرعي:", reply_markup=markup)
    else:
        bot.send_message(user_id, "الموضوع غير موجود، يرجى المحاولة مرة أخرى.")
        show_topics(message)

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "select_subtopic")
def handle_subtopic_selection(message):
    user_id = message.chat.id
    selected_subtopic = message.text
    user_state[user_id]["selected_subtopic"] = selected_subtopic
    user_state[user_id]["step"] = "ask_question_count"

    bot.send_message(user_id, "كم عدد الأسئلة التي تريدها؟")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "ask_question_count")
def handle_question_count(message):
    user_id = message.chat.id
    try:
        question_count = int(message.text)
        if question_count <= 0:
            raise ValueError
        user_state[user_id]["question_count"] = question_count
        user_state[user_id]["step"] = "start_quiz"

        # جلب ملف الأسئلة
        selected_topic = user_state[user_id]["selected_topic"]
        selected_subtopic = user_state[user_id]["selected_subtopic"]
        topic = next((t for t in topics_data if t['topicName'] == selected_topic), None)
        if topic:
            sub_topic = next((st for st in topic['subTopics'] if st['name'] == selected_subtopic), None)
            if sub_topic:
                questions_url = GITHUB_REPO_URL + sub_topic['file']
                response = requests.get(questions_url)
                questions_data = response.json()
                user_state[user_id]["questions"] = random.sample(questions_data, min(question_count, len(questions_data)))
                user_state[user_id]["current_question"] = 0
                user_state[user_id]["score"] = 0
                send_question(user_id)
            else:
                bot.send_message(user_id, "الموضوع الفرعي غير موجود، يرجى المحاولة مرة أخرى.")
                show_topics(message)
        else:
            bot.send_message(user_id, "الموضوع غير موجود، يرجى المحاولة مرة أخرى.")
            show_topics(message)
    except ValueError:
        bot.send_message(user_id, "الرجاء إدخال عدد صحيح موجب.")

def send_question(user_id):
    current_question = user_state[user_id]["current_question"]
    questions = user_state[user_id]["questions"]
    if current_question < len(questions):
        question_data = questions[current_question]
        question_text = question_data['question']
        options = question_data['options']
        markup = telebot.types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True)
        for option in options:
            markup.add(telebot.types.KeyboardButton(option))
        bot.send_message(user_id, question_text, reply_markup=markup)
    else:
        bot.send_message(user_id, f"انتهى الاختبار! نتيجتك: {user_state[user_id]['score']}/{len(questions)}")
        user_state[user_id] = {}

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "start_quiz")
def handle_answer(message):
    user_id = message.chat.id
    current_question = user_state[user_id]["current_question"]
    questions = user_state[user_id]["questions"]
    question_data = questions[current_question]
    correct_answer = question_data['options'][question_data['answer']]
    user_answer = message.text

    if user_answer == correct_answer:
        user_state[user_id]["score"] += 1
        bot.send_message(user_id, "إجابة صحيحة!")
    else:
        bot.send_message(user_id, f"إجابة خاطئة! الإجابة الصحيحة هي: {correct_answer}")

    user_state[user_id]["current_question"] += 1
    send_question(user_id)

# تشغيل البوت
bot.polling()
