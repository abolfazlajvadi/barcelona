# import nest_asyncio
# nest_asyncio.apply()

import sqlite3
import random
import string
from datetime import datetime
from threading import Thread
from flask import Flask, request, redirect
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio

# ---------- تنظیمات اولیه ----------
TOKEN = "8981742192:AAHC8z6u6GifXgMIafvzv0tn_Q2LV1mM2bQ"
BASE_URL = "https://barcelona-l5tu.onrender.com"
CHANNELS = ["@film01385"]

# ---------- Flask ----------
flask_app = Flask(__name__)

# ---------- دیتابیس (مسیر /tmp برای Render) ----------
conn = sqlite3.connect("/tmp/tracker.db", check_same_thread=False)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    link_code TEXT UNIQUE,
    link_full TEXT UNIQUE
)""")
c.execute("""CREATE TABLE IF NOT EXISTS clicks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_code TEXT,
    ip TEXT,
    user_agent TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)""")
conn.commit()

# ---------- توابع کمکی ----------
def get_ip():
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0]
    return request.remote_addr

def generate_link(telegram_id):
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    full_link = f"{BASE_URL}/track/{code}"
    c.execute("INSERT OR REPLACE INTO users (telegram_id, link_code, link_full) VALUES (?, ?, ?)", 
              (telegram_id, code, full_link))
    conn.commit()
    return full_link

def get_user_id_by_code(code):
    c.execute("SELECT telegram_id FROM users WHERE link_code = ?", (code,))
    result = c.fetchone()
    return result[0] if result else None

# ---------- بررسی عضویت ----------
async def is_member(user_id):
    for channel in CHANNELS:
        try:
            member = await application.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except:
            return False
    return True

# ---------- نمایش پنل ----------
async def show_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None):
    keyboard = [
        [InlineKeyboardButton("🔗 دریافت لینک من", callback_data="get_link")],
        [InlineKeyboardButton("💰 خرید اشتراک پرو", callback_data="buy_sub")],
        [InlineKeyboardButton("🛡 خرید سپر", callback_data="buy_shield")],
        [InlineKeyboardButton("🖼 تنظیم عکس", callback_data="set_photo")],
        [InlineKeyboardButton("✏️ تنظیم متن", callback_data="set_text")],
        [InlineKeyboardButton("📖 راهنما", callback_data="help")]
    ]
    target = message or update.message
    await target.reply_text(
        "به پنل کاربری خود خوش آمدید.\nلطفاً یک گزینه را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- هندلرهای ربات ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await is_member(user.id):
        await show_panel(update, context)
    else:
        keyboard = [[InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_membership")]]
        await update.message.reply_text(
            f"🔐 ابتدا در کانال‌های زیر عضو شوید:\n{chr(10).join(CHANNELS)}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "check_membership":
        if await is_member(user_id):
            await query.edit_message_text("✅ عضویت تأیید شد! در حال نمایش پنل...")
            await show_panel(update, context, message=query.message)
        else:
            await query.edit_message_text("❌ شما هنوز عضو همه کانال‌ها نشده‌اید.")
    elif data == "get_link":
        link = generate_link(user_id)
        keyboard = [[InlineKeyboardButton("🌐 باز کردن لینک", url=link)]]
        await query.edit_message_text(
            f"🔗 لینک اختصاصی شما:\n\n{link}\n\n"
            "این لینک را در بیوگرافی تلگرام خود قرار دهید.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.edit_message_text("⏳ این بخش در حال توسعه است.")

# ========== مسیرهای Flask ==========
@flask_app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = Update.de_json(request.get_json(), application.bot)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.process_update(update))
        return "ok", 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return "error", 500

@flask_app.route('/track/<code>')
def track_click(code):
    user_a_id = get_user_id_by_code(code)
    ip_address = get_ip()
    user_agent = request.headers.get('User-Agent', 'Unknown')
    c.execute("INSERT INTO clicks (link_code, ip, user_agent) VALUES (?, ?, ?)", 
              (code, ip_address, user_agent))
    conn.commit()
    
    if user_a_id:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                application.bot.send_message(
                    chat_id=user_a_id,
                    text=f"🎯 یک نفر روی لینک اختصاصی شما کلیک کرد!\n"
                         f"📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            )
        except Exception as e:
            print(f"Error sending to {user_a_id}: {e}")
    
    return redirect("https://t.me/your_channel", code=302)

@flask_app.route('/')
def index():
    return "ربات آنلاین است", 200

# ========== اجرای اصلی ==========
if __name__ == "__main__":
    # ایجاد نمونه Application در سطح جهانی
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_buttons))
    
    # تنظیم Webhook
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.bot.set_webhook(url=f"{BASE_URL}/webhook"))
    print(f"✅ Webhook set: {BASE_URL}/webhook")
    
    # اجرای Flask در یک ترد جداگانه
    def run_flask():
        flask_app.run(host="0.0.0.0", port=10000)
    
    Thread(target=run_flask).start()
    
    # اجرای حلقه اصلی asyncio (برای پردازش آپدیت‌ها)
    loop.run_forever()
