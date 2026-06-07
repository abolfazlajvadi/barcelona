import logging
import sqlite3
import random
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask, request

TOKEN = "8981742192:AAHC8z6u6GifXgMIafvzv0tn_Q2LV1mM2bQ"
BASE_URL = "https://barcelona-l5tu.onrender.com"  # آدرس اصلی، بدون /webhook
CHANNELS = ["@film01385"]

# Flask app
flask_app = Flask(__name__)

# دیتابیس
conn = sqlite3.connect("tracker.db", check_same_thread=False)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    link TEXT UNIQUE
)""")
c.execute("""CREATE TABLE IF NOT EXISTS clicks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link TEXT,
    ip TEXT,
    user_agent TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)""")
conn.commit()

def generate_link(telegram_id):
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    link = f"{BASE_URL}/track/{code}"
    c.execute("INSERT OR REPLACE INTO users (telegram_id, link) VALUES (?, ?)", (telegram_id, link))
    conn.commit()
    return link

async def is_member(user_id):
    for channel in CHANNELS:
        try:
            member = await application.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except:
            return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await is_member(user.id):
        await show_panel(update, context)
    else:
        keyboard = [[InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_membership")]]
        await update.message.reply_text(
            "🔐 ابتدا در کانال‌های زیر عضو شوید:\n" + "\n".join(CHANNELS),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔗 دریافت لینک من", callback_data="get_link")],
        [InlineKeyboardButton("💰 خرید اشتراک پرو", callback_data="buy_sub")],
        [InlineKeyboardButton("🛡 خرید سپر", callback_data="buy_shield")],
        [InlineKeyboardButton("🖼 تنظیم عکس", callback_data="set_photo")],
        [InlineKeyboardButton("✏️ تنظیم متن", callback_data="set_text")],
        [InlineKeyboardButton("📖 راهنما", callback_data="help")]
    ]
    await update.message.reply_text(
        "به پنل کاربری خود خوش آمدید.\nلطفاً یک گزینه را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "check_membership":
        if await is_member(user_id):
            await show_panel(update, context)
        else:
            await query.edit_message_text("❌ شما هنوز عضو همه کانال‌ها نشده‌اید.")
    elif data == "get_link":
        link = generate_link(user_id)
        await query.edit_message_text(f"🔗 لینک اختصاصی شما:\n{link}\n\nاین لینک را در بیوگرافی تلگرام خود قرار دهید.")
    else:
        await query.edit_message_text("این بخش در حال توسعه است.")

# ========== Webhook ==========
@flask_app.route('/webhook', methods=['POST'])
def webhook():  # این تابع را به حالت عادی (غیر async) تغییر دادیم
    try:
        update = Update.de_json(request.get_json(), application.bot)
        application.process_update(update)  # await را برداشتیم
        return "ok", 200
    except Exception as e:
        print(f"خطا در وب‌هوک: {e}")
        return "error", 500

@flask_app.route('/')
def index():
    return "ربات آنلاین است"

if __name__ == "__main__":
    # ساخت اپلیکیشن تلگرام
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_buttons))

    # مقداردهی اولیه Webhook (اینجا دیگر نیازی به /webhook اضافه نیست)
    application.bot.set_webhook(url=f"{BASE_URL}/webhook")

    # اجرای Flask
    flask_app.run(host="0.0.0.0", port=10000)
