import nest_asyncio
nest_asyncio.apply()

import sqlite3
import random
import string
from datetime import datetime
from flask import Flask, request, redirect
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio

# ---------- تنظیمات اولیه ----------
TOKEN = "8981742192:AAHC8z6u6GifXgMIafvzv0tn_Q2LV1mM2bQ"
BASE_URL = "https://barcelona-l5tu.onrender.com"  # آدرس اصلی سرویس (بدون / در انتها)
CHANNELS = ["@film01385"]  # لیست کانال‌های اجباری

# ---------- Flask ----------
flask_app = Flask(__name__)

# ---------- دیتابیس ----------
conn = sqlite3.connect("tracker.db", check_same_thread=False)
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
    """دریافت IP واقعی کاربر (حتی با پروکسی)"""
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0]
    return request.remote_addr

def generate_link(telegram_id):
    """ساخت لینک اختصاصی برای کاربر"""
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    full_link = f"{BASE_URL}/track/{code}"
    c.execute("INSERT OR REPLACE INTO users (telegram_id, link_code, link_full) VALUES (?, ?, ?)", 
              (telegram_id, code, full_link))
    conn.commit()
    return full_link

def get_user_id_by_code(code):
    """پیدا کردن telegram_id کاربر از روی کد لینک"""
    c.execute("SELECT telegram_id FROM users WHERE link_code = ?", (code,))
    result = c.fetchone()
    return result[0] if result else None

# ---------- بررسی عضویت در کانال ----------
async def is_member(user_id):
    for channel in CHANNELS:
        try:
            member = await application.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except:
            return False
    return True

# ---------- نمایش پنل کاربری ----------
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

# ---------- هندلرهای ربات تلگرام ----------
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
            await show_panel(update, context)
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

# ========== مسیرهای Flask (برای وب‌هوک و ردیابی کلیک) ==========
@flask_app.route('/webhook', methods=['POST'])
def webhook():
    """دریافت آپدیت از تلگرام"""
    try:
        update = Update.de_json(request.get_json(), application.bot)
        asyncio.run(application.process_update(update))
        return "ok", 200
    except Exception as e:
        print(f"خطا در وب‌هوک: {e}")
        return "error", 500

@flask_app.route('/track/<code>')
def track_click(code):
    """ثبت کلیک و ارسال گزارش به صاحب لینک"""
    # پیدا کردن صاحب لینک
    user_a_id = get_user_id_by_code(code)
    
    # ثبت اطلاعات کلیک در دیتابیس
    ip_address = get_ip()
    user_agent = request.headers.get('User-Agent', 'Unknown')
    c.execute("INSERT INTO clicks (link_code, ip, user_agent) VALUES (?, ?, ?)", 
              (code, ip_address, user_agent))
    conn.commit()
    
    # ارسال پیام به کاربر A (صاحب لینک) در صورت وجود
    if user_a_id:
        try:
            # استفاده از event loop موجود برای ارسال پیام
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
            print(f"خطا در ارسال پیام به کاربر {user_a_id}: {e}")
    
    # هدایت کاربر B به یک صفحه یا کانال دلخواه
    return redirect("https://t.me/your_channel", code=302)

@flask_app.route('/')
def index():
    return "ربات آنلاین است", 200

# ========== اجرای اصلی ==========
if __name__ == "__main__":
    # ساخت نمونه از Application
    application = Application.builder().token(TOKEN).build()
    
    # اضافه کردن هندلرها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_buttons))
    
    # تنظیم Webhook
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.bot.set_webhook(url=f"{BASE_URL}/webhook"))
    print(f"✅ Webhook تنظیم شد: {BASE_URL}/webhook")
    
    # اجرای Flask (با ترد جداگانه برای ربات)
    from threading import Thread
    def run_flask():
        flask_app.run(host="0.0.0.0", port=10000)
    
    Thread(target=run_flask).start()
    
    # اجرای ربات (برای پردازش آپدیت‌های پس‌زمینه)
    loop.run_forever()
