import sqlite3
import random
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask, request
import asyncio
import nest_asyncio

# اعمال nest_asyncio برای حل مشکل حلقه رویداد
nest_asyncio.apply()

TOKEN = "8981742192:AAHC8z6u6GifXgMIafvzv0tn_Q2LV1mM2bQ"
BASE_URL = "https://barcelona-l5tu.onrender.com"  # آدرس اصلی سرویس شما در Render
CHANNELS = ["@film01385"]

# Flask app
flask_app = Flask(__name__)

# ========== دیتابیس ==========
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

# ========== توابع ربات ==========
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
def webhook():
    try:
        update = Update.de_json(request.get_json(), application.bot)
        # استفاده از asyncio.run برای اجرای تابع async
        asyncio.run(application.process_update(update))
        return "ok", 200
    except Exception as e:
        print(f"خطا در وب‌هوک: {e}")
        import traceback
        traceback.print_exc()
        return "error", 500

@flask_app.route('/')
def index():
    return "ربات آنلاین است - نسخه Webhook"

@flask_app.route('/test')
def test():
    return "Webhook endpoint is working!", 200

# ========== ساخت اپلیکیشن تلگرام (قبل از وب هوک) ==========
application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(handle_buttons))

# تنظیم Webhook (با یک حلقه رویداد جداگانه)
async def setup_webhook():
    await application.bot.set_webhook(url=f"{BASE_URL}/webhook")
    print(f"✅ Webhook تنظیم شد: {BASE_URL}/webhook")

# اجرای تنظیم Webhook
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(setup_webhook())

# Flask app بدون if __name__ برای Gunicorn
# برنامه به صورت مستقیم توسط Gunicorn اجرا می‌شود
