import sqlite3
import random
import string
from datetime import datetime
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ---------- تنظیمات ساده ----------
TOKEN = "8981742192:AAHC8z6u6GifXgMIafvzv0tn_Q2LV1mM2bQ"
BOT_USERNAME = "nevergivup_bot"
BASE_URL = "https://barcelona-l5tu.onrender.com"
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ---------- دیتابیس ----------
conn = sqlite3.connect("/tmp/tracker.db", check_same_thread=False)
c = conn.cursor()

# حذف جدول‌های قبلی و ساخت دوباره (برای اطمینان)
c.execute("DROP TABLE IF EXISTS users")
c.execute("CREATE TABLE users (telegram_id INTEGER PRIMARY KEY, link_code TEXT UNIQUE)")
conn.commit()

# ---------- تابع لینک با آیدی عددی ----------
def generate_link(telegram_id):
    code = str(telegram_id)  # آیدی عددی خودشه
    c.execute("INSERT OR REPLACE INTO users (telegram_id, link_code) VALUES (?, ?)", (telegram_id, code))
    conn.commit()
    return f"https://t.me/{BOT_USERNAME}?start=track_{code}"

def get_owner_id_by_code(code):
    try:
        # کد همون آیدی عددیه، پس خودش رو برگردون
        return int(code)
    except:
        return None

# ---------- هندلر استارت (بخش اصلی) ----------
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    text = message.text
    
    # پیام تست به کاربر (مهم!)
    bot.send_message(user_id, f"✅ ربات کار می‌کند. متن دریافتی: {text}")
    
    # بررسی اگر لینک اختصاصی بود
    if text.startswith("/start track_"):
        code = text.split("track_")[1]
        owner_id = get_owner_id_by_code(code)
        
        # پیام دوم برای دیباگ
        bot.send_message(user_id, f"🔍 کد استخراج شده: {code}, صاحب لینک: {owner_id}")
        
        if owner_id and owner_id != user_id:
            # ========== پیام تله به کلیک‌کننده ==========
            trap_msg = "⚠️ **تو در تله افتادی!**\n\nصاحب پروفایل از بازدید تو مطلع شد."
            bot.send_message(user_id, trap_msg, parse_mode='Markdown')
            
            # ========== گزارش به صاحب لینک ==========
            clicker_name = message.from_user.first_name
            report_msg = f"🎯 **یک فضول در تله افتاد!**\n\n👤 نام: {clicker_name}\n⏰ زمان: {datetime.now().strftime('%H:%M:%S')}"
            bot.send_message(owner_id, report_msg, parse_mode='Markdown')
            
        elif owner_id == user_id:
            bot.send_message(user_id, "⚠️ این لینک مال خودته!")
        else:
            bot.send_message(user_id, "❌ لینک نامعتبر!")
    else:
        bot.send_message(user_id, "👋 به ربات خوش آمدی. برای دریافت لینک /link رو بفرست.")

# ---------- دریافت لینک ----------
@bot.message_handler(commands=['link'])
def get_link(message):
    user_id = message.from_user.id
    link = generate_link(user_id)
    bot.send_message(user_id, f"🔗 لینک اختصاصی تو:\n`{link}`\n\nاین لینک رو تو بیوگرافیت بذار.", parse_mode='Markdown')

# ---------- مسیر وب‌هوک ----------
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
