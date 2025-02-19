import os
import random
import requests
import logging

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    Poll
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# -------------------------------------------
# إعدادات تسجيل (Logging)
# -------------------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------------------------------
# ثوابت خاصة بحالة المحادثة Conversation States
# -------------------------------------------
SELECTING_TOPIC, SELECTING_SUBTOPIC, GETTING_QUESTION_COUNT = range(3)

# -------------------------------------------
# عنوان الـ GitHub Raw لجلب ملفات الـ JSON
# لاحظ أننا نضع /data في النهاية لأن داخلها topics.json وبقية الملفات
# -------------------------------------------
GITHUB_BASE_RAW_URL = "https://raw.githubusercontent.com/hhkuy/Sums_Q/main/data"

# -------------------------------------------
# BOT TOKEN
# تنبيه: وضع التوكن في الكود يعرّضه للسرقة.
# -------------------------------------------
token = "7633072361:AAHnzREYTKKRFiTiq7HDZBalnwnmgivY8_I"  # ضع توكن البوت هنا

# -------------------------------------------
# دالة لجلب ملف topics.json من مستودع الأسئلة
# (الموجود في مجلد data)
# -------------------------------------------
def fetch_topics():
    # الملف موجود في المسار data/topics.json
    # بالتالي الرابط كاملاً سيكون:
    url = f"{GITHUB_BASE_RAW_URL}/topics.json"
    response = requests.get(url)
    response.raise_for_status()  # تحقّق من نجاح الطلب
    topics_data = response.json()
    return topics_data

# -------------------------------------------
# دالة لجلب الأسئلة من ملف JSON فرعي
# مثال: "data/anatomy_of_limbs_lower_limbs.json"
# -------------------------------------------
def fetch_questions(file_name: str):
    # في topics.json تم تخزين المسار على شكل: "data/xxxx.json"
    # لكننا بالفعل داخل مجلد data في GitHub_BASE_RAW_URL
    # مما يعني أننا لو استخدمنا url = f"{GITHUB_BASE_RAW_URL}/{file_name}"
    # فسيكون لدينا ..../data/data/...json
    # لذلك نتحقق إن كان يبدأ بـ "data/" ثم نزيلها:
    if file_name.startswith("data/"):
        file_name = file_name.replace("data/", "")
    # بناء الرابط
    url = f"{GITHUB_BASE_RAW_URL}/{file_name}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

# -------------------------------------------
# أمر /start
# يعرض رسالة ترحيب مع زر لاختيار الموضوع
# -------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحباً بك! أنا بوت الاختبارات.\n"
        "اضغط على الزر أدناه لاختيار الموضوع.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("اختر الموضوع", callback_data="choose_topic")]
        ])
    )

# -------------------------------------------
# عند الضغط على زر "اختر الموضوع"
# نجلب قائمة المواضيع من ملف topics.json
# -------------------------------------------
async def choose_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # نجلب المواضيع
    topics_data = fetch_topics()
    # نخزنها في user_data لاستخدامها لاحقًا
    context.user_data["topics_data"] = topics_data

    # بناء قائمة أزرار المواضيع
    keyboard = []
    for i, topic in enumerate(topics_data):
        btn_text = f"{topic['topicName']}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"topic_{i}")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # أرسل للمستخدم رسالة تحتوي على القائمة
    await query.message.reply_text(
        "اختر الموضوع من القائمة:",
        reply_markup=reply_markup
    )

    # نحذف الرسالة السابقة (اختياري لجعل المحادثة أنظف)
    await query.message.delete()

    return SELECTING_TOPIC

# -------------------------------------------
# عند اختيار موضوع، نعرض قائمة المواضيع الفرعية
# -------------------------------------------
async def topic_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data  # مثال "topic_0"
    _, topic_index_str = data.split("_")
    topic_index = int(topic_index_str)

    topics_data = context.user_data.get("topics_data", [])
    selected_topic = topics_data[topic_index]

    context.user_data["selected_topic"] = selected_topic

    # بناء قائمة المواضيع الفرعية
    subtopics = selected_topic.get("subTopics", [])
    keyboard = []
    for i, st in enumerate(subtopics):
        keyboard.append(
            [InlineKeyboardButton(st['name'], callback_data=f"sub_{i}")]
        )

    # زر رجوع للعودة لقائمة المواضيع
    keyboard.append([InlineKeyboardButton("رجوع", callback_data="back_to_topics")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(
        f"الموضوع المختار: {selected_topic['topicName']}\n"
        f"اختر الموضوع الفرعي:",
        reply_markup=reply_markup
    )
    # حذف الرسالة السابقة
    await query.message.delete()

    return SELECTING_SUBTOPIC

# -------------------------------------------
# زر الرجوع من المواضيع الفرعية إلى المواضيع
# -------------------------------------------
async def back_to_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    topics_data = context.user_data.get("topics_data", [])

    keyboard = []
    for i, topic in enumerate(topics_data):
        btn_text = f"{topic['topicName']}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"topic_{i}")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(
        "اختر الموضوع من القائمة:",
        reply_markup=reply_markup
    )
    await query.message.delete()

    return SELECTING_TOPIC

# -------------------------------------------
# عند اختيار الموضوع الفرعي
# يطلب من المستخدم إدخال عدد الأسئلة
# -------------------------------------------
async def subtopic_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data  # مثلاً "sub_0"
    _, sub_index_str = data.split("_")
    sub_index = int(sub_index_str)

    selected_topic = context.user_data["selected_topic"]
    subtopics = selected_topic.get("subTopics", [])
    selected_subtopic = subtopics[sub_index]

    context.user_data["selected_subtopic"] = selected_subtopic

    # سنطلب من المستخدم إدخال عدد الأسئلة
    keyboard = [
        [InlineKeyboardButton("رجوع", callback_data="back_to_subtopics")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(
        f"اخترت الموضوع الفرعي: {selected_subtopic['name']}\n"
        f"أدخل عدد الأسئلة التي تريدها (فقط رقم) أو اضغط 'رجوع':",
        reply_markup=reply_markup
    )
    await query.message.delete()

    return GETTING_QUESTION_COUNT

# -------------------------------------------
# زر الرجوع من مرحلة إدخال عدد الأسئلة للعودة لقائمة المواضيع الفرعية
# -------------------------------------------
async def back_to_subtopics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_topic = context.user_data["selected_topic"]
    subtopics = selected_topic.get("subTopics", [])

    keyboard = []
    for i, st in enumerate(subtopics):
        keyboard.append(
            [InlineKeyboardButton(st['name'], callback_data=f"sub_{i}")]
        )
    keyboard.append([InlineKeyboardButton("رجوع", callback_data="back_to_topics")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(
        f"الموضوع المختار: {selected_topic['topicName']}\n"
        "اختر الموضوع الفرعي:",
        reply_markup=reply_markup
    )
    await query.message.delete()

    return SELECTING_SUBTOPIC

# -------------------------------------------
# استقبال عدد الأسئلة من المستخدم
# -------------------------------------------
async def receive_question_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text)
        context.user_data["question_count"] = count

        # جلب ملف الأسئلة للموضوع الفرعي المختار
        subtopic = context.user_data["selected_subtopic"]
        file_name = subtopic["file"]  # مثال: "data/anatomy_of_limbs_lower_limbs.json"

        questions = fetch_questions(file_name)

        # اختيار عشوائي لعدد count من الأسئلة
        if count > len(questions):
            count = len(questions)  # إذا طلب المستخدم أكثر مما هو متوفر

        selected_questions = random.sample(questions, count)
        context.user_data["selected_questions"] = selected_questions

        # إرسال الأسئلة على شكل Poll Quiz
        for idx, q in enumerate(selected_questions, start=1):
            question_text = q["question"]
            options = q["options"]
            correct_idx = q["answer"]  # هذا الفهرس الصحيح (0-based)
            explanation = q.get("explanation", "")

            # مراعاة حدود تيليجرام (السؤال <= 300 حرف، الشرح <= 200 حرف)
            if len(question_text) > 300:
                question_text = question_text[:297] + "..."
            if len(explanation) > 200:
                explanation = explanation[:197] + "..."

            await update.message.chat.send_poll(
                question=question_text,
                options=options,
                type=Poll.QUIZ,
                correct_option_id=correct_idx,
                explanation=explanation,
                is_anonymous=False  # يمكن تغييره إلى True إذا أردته مجهولاً
            )

        await update.message.reply_text(
            "تم إنشاء الاختبار وإرسال الأسئلة بنجاح!\n"
            "بالتوفيق!"
        )

        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("الرجاء إدخال رقم صحيح.")
        return GETTING_QUESTION_COUNT

# -------------------------------------------
# دالة للإلغاء أو الخروج من أي مرحلة
# -------------------------------------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية. اكتب /start للبدء من جديد.")
    return ConversationHandler.END

# -------------------------------------------
# الدالة الرئيسية لتشغيل البوت
# -------------------------------------------
def main():
    # استخدمنا التوكن بشكل صريح في الكود:
    # token = "PUT_YOUR_BOT_TOKEN_HERE"
    # إذا أردت تشغيله محلياً، لا تحتاج لمتغير بيئة.
    # أما إذا نشرت على منصة، فاحذر ظهور التوكن للعلن.
    
    if not token or token == "PUT_YOUR_BOT_TOKEN_HERE":
        print("يرجى وضع توكن البوت في المتغير 'token' داخل الكود.")
        return

    # ننشئ الـ Application
    app = ApplicationBuilder().token(token).build()

    # نصنع ConversationHandler لتنظيم حوار المستخدم
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_TOPIC: [
                CallbackQueryHandler(topic_chosen, pattern=r"^topic_\d+$"),
            ],
            SELECTING_SUBTOPIC: [
                CallbackQueryHandler(subtopic_chosen, pattern=r"^sub_\d+$"),
                CallbackQueryHandler(back_to_topics, pattern="^back_to_topics$")
            ],
            GETTING_QUESTION_COUNT: [
                CallbackQueryHandler(back_to_subtopics, pattern="^back_to_subtopics$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_question_count),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
    )

    # إضافة الهاندلر إلى التطبيق
    app.add_handler(conv_handler)
    # للتسهيل، نضيف أمر /cancel يخرج من المحادثة
    app.add_handler(CommandHandler("cancel", cancel))

    # معالجة زر (choose_topic)
    app.add_handler(CallbackQueryHandler(choose_topic, pattern="^choose_topic$"))

    # بدء التشغيل
    print("البوت يعمل الآن...")
    app.run_polling()


if __name__ == "__main__":
    main()
