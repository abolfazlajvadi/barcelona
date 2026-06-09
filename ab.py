import sqlite3
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ---------- تنظیمات ----------
TOKEN = "8981742192:AAHC8z6u6GifXgMIafvzv0tn_Q2LV1mM2bQ"
BOT_USERNAME = "nevergivup_bot"
BASE_URL = "https://barcelona-l5tu.onrender.com"
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ---------- دیتابیس ----------
conn = sqlite3.connect("/tmp/tracker.db", check_same_thread=False)
c = conn.cursor()

c.execute("DROP TABLE IF EXISTS users")
c.execute("CREATE TABLE users (telegram_id INTEGER PRIMARY KEY, link_code TEXT UNIQUE)")

c.execute("""CREATE TABLE IF NOT EXISTS pending_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_code TEXT,
    owner_id INTEGER,
    clicker_id INTEGER,
    message_id INTEGER,
    expires_at DATETIME,
    cancelled BOOLEAN DEFAULT FALSE
)""")
conn.commit()

# ---------- توابع ----------
def generate_link(telegram_id):
    code = str(telegram_id)
    c.execute("INSERT OR REPLACE INTO users (telegram_id, link_code) VALUES (?, ?)", (telegram_id, code))
    conn.commit()
    return f"https://t.me/{BOT_USERNAME}?start=track_{code}"

def get_owner_id_by_code(code):
    try:
        return int(code)
    except:
        return None

def get_owner_name(owner_id):
    try:
        chat = bot.get_chat(owner_id)
        first_name = chat.first_name or ""
        last_name = chat.last_name or ""
        return f"{first_name} {last_name}".strip()
    except:
        return "صاحب پروفایل"

def get_clicker_name(clicker_id):
    try:
        chat = bot.get_chat(clicker_id)
        first_name = chat.first_name or ""
        last_name = chat.last_name or ""
        return f"{first_name} {last_name}".strip()
    except:
        return "کاربر ناشناس"

def delete_message_later(chat_id, message_id, delay, clicker_id, owner_name):
    time.sleep(delay)
    try:
        bot.delete_message(chat_id, message_id)
    except:
        pass
    
    final_message = f"😅 **فضولی کردی و {owner_name} فهمید!**\n\nدیگه این کارو نکن 😊"
    try:
        bot.send_message(chat_id, final_message, parse_mode='Markdown')
    except:
        pass

def send_report_after_delay(link_code, owner_id, clicker_id, delay=75):
    time.sleep(delay)
    c.execute("SELECT cancelled FROM pending_reports WHERE link_code = ? AND clicker_id = ? AND owner_id = ? ORDER BY id DESC LIMIT 1", 
              (link_code, clicker_id, owner_id))
    result = c.fetchone()
    
    if not result or result[0] == False:
        clicker_name = get_clicker_name(clicker_id)
        report_msg = f"🎯 **یک فضول در تله افتاد!**\n\n👤 نام: {clicker_name}\n⏰ زمان: {datetime.now().strftime('%H:%M:%S')}"
        try:
            bot.send_message(owner_id, report_msg, parse_mode='Markdown')
        except:
            pass

# ---------- هندلر استارت (بدون پیام تست) ----------
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    text = message.text
    
    if text.startswith("/start track_"):
        code = text.split("track_")[1]
        owner_id = get_owner_id_by_code(code)
        clicker_id = user_id
        
        if owner_id and owner_id != clicker_id:
            owner_name = get_owner_name(owner_id)
            
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("❌ عدم ارسال گزارش فضولی", callback_data=f"cancel_{code}_{clicker_id}"))
            
            trap_message = (
                f"⚠️ **نبايد اين فضولی رو ميکردی!** 🥰\n\n"
                f"الان اين فضوليت برای {owner_name} ارسال شد، "
                f"بهتره قبل از اينکه بياد ببينه، خودت بهش بگی داشتی فضولی ميکردی 😊\n\n"
                f"برای عدم ارسال دکمه زير را فشار دهيد (فرصت شما 1 دقيقه و 15 ثانيه)\n\n"
                f"❌ عدم ارسال گزارش فضولی"
            )
            
            # فرستادن مستقیم پیام تله - بدون هیچ پیام اضافی
            msg = bot.send_message(clicker_id, trap_message, reply_markup=keyboard, parse_mode='Markdown')
            
            c.execute("INSERT INTO pending_reports (link_code, owner_id, clicker_id, message_id, expires_at) VALUES (?, ?, ?, ?, ?)",
                      (code, owner_id, clicker_id, msg.message_id, datetime.now() + timedelta(seconds=75)))
            conn.commit()
            
            threading.Thread(target=delete_message_later, args=(clicker_id, msg.message_id, 75, clicker_id, owner_name)).start()
            threading.Thread(target=send_report_after_delay, args=(code, owner_id, clicker_id, 75)).start()
            
        elif owner_id == clicker_id:
            bot.send_message(clicker_id, "⚠️ این لینک مال خودته!")
        else:
            bot.send_message(clicker_id, "❌ لینک نامعتبر!")
    else:
        # start ساده - فقط یک پیام خوش‌آمدگویی ساده
        bot.send_message(user_id, "👋 به ربات خوش آمدی.\nبرای دریافت لینک /link رو بفرست.")

# ---------- دریافت لینک ----------
@bot.message_handler(commands=['link'])
def get_link(message):
    user_id = message.from_user.id
    link = generate_link(user_id)
    bot.send_message(user_id, f"🔗 لینک اختصاصی تو:\n`{link}`\n\nاین لینک رو تو بیوگرافیت بذار.", parse_mode='Markdown')

# ---------- دکمه لغو گزارش ----------
@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_"))
def cancel_report(call):
    _, code, clicker_id = call.data.split("_")
    clicker_id = int(clicker_id)
    
    if call.from_user.id != clicker_id:
        bot.answer_callback_query(call.id, "این دکمه مال تو نیست!", show_alert=True)
        return
    
    c.execute("UPDATE pending_reports SET cancelled = TRUE WHERE link_code = ? AND clicker_id = ?", (code, clicker_id))
    conn.commit()
    
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    
    bot.send_message(
        call.message.chat.id,
        "✅ **گزارش فضولی ارسال نشد!**\n\nاين فرصت رو غنيمت بدون و ديگه فضولی نکن.",
        parse_mode='Markdown'
    )
    bot.answer_callback_query(call.id, "گزارش کنسل شد!")

# ---------- مسیرهای Flask ----------
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.get_data().decode('UTF-8'))
        bot.process_new_updates([update])
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/')
def index():
    return "ربات آنلاین است", 200

def set_webhook():
    bot.set_webhook(url=f"{BASE_URL}/webhook")
    print("✅ Webhook set")

if __name__ == '__main__':
    set_webhook()
    app.run(host='0.0.0.0', port=10000)
