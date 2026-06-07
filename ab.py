import os
import sqlite3
import random
import string
from datetime import datetime
from flask import Flask, request, redirect, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ---------- تنظیمات اولیه ----------
TOKEN = "8981742192:AAHC8z6u6GifXgMIafvzv0tn_Q2LV1mM2bQ"
BASE_URL = "https://barcelona-l5tu.onrender.com"  # آدرس سرویس شما در Render
CHANNELS = ["@film01385"]  # لیست کانال‌های اجباری

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ---------- دیتابیس (استفاده از /tmp در Render) ----------
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
    """دریافت IP واقعی کاربر (حتی با پروکسی)"""
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0]
    return request.remote_addr

def generate_link(telegram_id):
    """ساخت یک لینک اختصاصی جدید برای کاربر"""
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    full_link = f"{BASE_URL}/track/{code}"
    c.execute("INSERT OR REPLACE INTO users (telegram_id, link_code, link_full) VALUES (?, ?, ?)", 
              (telegram_id, code, full_link))
    conn.commit()
    return full_link

def get_user_id_by_code(code):
    """پیدا کردن Telegram ID کاربر از روی کد لینک"""
    c.execute("SELECT telegram_id FROM users WHERE link_code = ?", (code,))
    result = c.fetchone()
    return result[0] if result else None

# ---------- بررسی عضویت در کانال‌های اجباری ----------
def is_user_member(user_id):
    for channel in CHANNELS:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except:
            return False
    return True

# ---------- نمایش پنل کاربری ----------
def show_panel(chat_id, message_id=None):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("🔗 دریافت لینک من", callback_data="get_link"))
    # در صورت نیاز می‌توانید دکمه‌های دیگر را اضافه کنید
    keyboard.add(InlineKeyboardButton("📖 راهنما", callback_data="help"))
    
    if message_id:
        bot.edit_message_text(
            "👋 به پنل کاربری خوش آمدید.\n\n"
            "از دکمه زیر برای دریافت لینک اختصاصی خود استفاده کنید.\n"
            "این لینک را در بیوگرافی تلگرام خود قرار دهید.",
            chat_id, message_id, reply_markup=keyboard
        )
    else:
        bot.send_message(
            chat_id,
            "👋 به پنل کاربری خوش آمدید.\n\n"
            "از دکمه زیر برای دریافت لینک اختصاصی خود استفاده کنید.\n"
            "این لینک را در بیوگرافی تلگرام خود قرار دهید.",
            reply_markup=keyboard
        )

# ---------- هندلر دستور /start ----------
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if is_user_member(user_id):
        show_panel(message.chat.id)
    else:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_membership"))
        bot.reply_to(
            message,
            f"🔐 برای استفاده از ربات، ابتدا در کانال‌های زیر عضو شوید:\n{chr(10).join(CHANNELS)}",
            reply_markup=keyboard
        )

# ---------- هندلر دکمه‌های شیشه‌ای ----------
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    if call.data == "check_membership":
        if is_user_member(user_id):
            bot.edit_message_text("✅ عضویت شما تأیید شد!", chat_id, call.message.message_id)
            show_panel(chat_id)
        else:
            bot.answer_callback_query(call.id, "❌ شما هنوز در همه کانال‌ها عضو نشده‌اید.", show_alert=True)
    
    elif call.data == "get_link":
        link = generate_link(user_id)
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("🌐 باز کردن لینک", url=link))
        bot.edit_message_text(
            f"🔗 لینک اختصاصی شما:\n\n{link}\n\n"
            "این لینک را در بیوگرافی یا جایی که می‌خواهید قرار دهید.\n"
            "هر کس روی آن کلیک کند، برای شما گزارش می‌شود.",
            chat_id, call.message.message_id,
            reply_markup=keyboard
        )
    
    elif call.data == "help":
        bot.edit_message_text(
            "📖 **راهنمای ربات**\n\n"
            "1. ابتدا در کانال‌های اجباری عضو شوید.\n"
            "2. سپس از پنل، لینک اختصاصی خود را دریافت کنید.\n"
            "3. لینک را در بیوگرافی تلگرام خود قرار دهید.\n"
            "4. هر کس روی لینک کلیک کند، نام کاربری و اطلاعات کلیک برای شما ارسال می‌شود.\n\n"
            "⚡ توجه: این ربات اطلاعات بازدید از پروفایل را نشان نمی‌دهد، بلکه فقط کلیک روی لینک را ثبت می‌کند.",
            chat_id, call.message.message_id,
            parse_mode='Markdown'
        )
        show_panel(chat_id, call.message.message_id)  # بازگشت به پنل بعد از ۵ ثانیه
    else:
        bot.answer_callback_query(call.id, "⏳ این بخش در حال توسعه است.", show_alert=True)

# ========== مسیرهای Flask (وب‌هوک و ردیابی) ==========
@app.route('/webhook', methods=['POST'])
def webhook():
    """دریافت و پردازش درخواست‌های جدید از تلگرام"""
    try:
        json_str = request.get_data().decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/track/<code>')
def track_click(code):
    """ثبت کلیک روی لینک اختصاصی و ارسال گزارش"""
    user_a_id = get_user_id_by_code(code)  # صاحب لینک
    ip_address = get_ip()
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    # ثبت اطلاعات کلیک در دیتابیس
    c.execute("INSERT INTO clicks (link_code, ip, user_agent) VALUES (?, ?, ?)", 
              (code, ip_address, user_agent))
    conn.commit()
    
    # ارسال پیام به صاحب لینک
    if user_a_id:
        try:
            bot.send_message(
                user_a_id,
                f"🎯 **یک نفر روی لینک اختصاصی شما کلیک کرد!**\n"
                f"📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🌐 IP: {ip_address}",
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Error sending to {user_a_id}: {e}")
    
    # هدایت کاربر به یک مقصد دلخواه (مثلاً کانال شما)
    return redirect("https://t.me/your_channel", code=302)

@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

@app.route('/', methods=['GET'])
def index():
    return "ربات آنلاین است", 200

# ---------- تنظیم وب‌هوک ----------
def set_webhook():
    webhook_url = f"{BASE_URL}/webhook"
    result = bot.set_webhook(url=webhook_url)
    if result:
        print(f"✅ Webhook با موفقیت تنظیم شد: {webhook_url}")
    else:
        print(f"❌ تنظیم Webhook ناموفق بود")

# ---------- اجرای اصلی ----------
if __name__ == '__main__':
    set_webhook()
    # اجرای فلاسک روی پورت ۱۰۰۰۰ (Render به طور خودکار این پورت را در اختیار دارد)
    app.run(host='0.0.0.0', port=10000)
