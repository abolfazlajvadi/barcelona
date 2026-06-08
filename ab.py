import os
import sqlite3
import random
import string
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ---------- تنظیمات اولیه ----------
TOKEN = "8981742192:AAHC8z6u6GifXgMIafvzv0tn_Q2LV1mM2bQ"
BOT_USERNAME = "nevergivup_bot"
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

# جدول کاربران
c.execute("""CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    link_code TEXT UNIQUE,
    link_full TEXT UNIQUE
)""")

# جدول کلیک‌ها
c.execute("""CREATE TABLE IF NOT EXISTS clicks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_code TEXT,
    clicker_id INTEGER,
    ip TEXT,
    user_agent TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)""")

# جدول تنظیمات کاربر
c.execute("""CREATE TABLE IF NOT EXISTS user_settings (
    telegram_id INTEGER PRIMARY KEY,
    capture_text TEXT,
    capture_photo_id TEXT
)""")

# جدول گزارش‌های در انتظار
c.execute("""CREATE TABLE IF NOT EXISTS pending_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_code TEXT,
    owner_id INTEGER,
    clicker_id INTEGER,
    expires_at DATETIME,
    cancelled BOOLEAN DEFAULT FALSE
)""")
conn.commit()

# ---------- توابع کمکی ----------
def generate_link(telegram_id):
    """تولید لینک با آیدی عددی ثابت کاربر"""
    code = str(telegram_id)
    full_link = f"https://t.me/{BOT_USERNAME}?start=track_{code}"
    c.execute("INSERT OR REPLACE INTO users (telegram_id, link_code, link_full) VALUES (?, ?, ?)", 
              (telegram_id, code, full_link))
    conn.commit()
    return full_link

def get_owner_id_by_code(code):
    """دریافت آیدی صاحب لینک از کد"""
    try:
        return int(code)
    except:
        return None

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

def get_clicker_info(clicker_id):
    """دریافت اطلاعات کامل شخص کلیک‌کننده"""
    try:
        chat = bot.get_chat(clicker_id)
        first_name = chat.first_name or ""
        last_name = chat.last_name or ""
        name = f"{first_name} {last_name}".strip()
        username = f"@{chat.username}" if chat.username else "ندارد"
        bio = "ندارد"
        try:
            if hasattr(chat, 'bio') and chat.bio:
                bio = chat.bio
        except:
            pass
        return {
            "name": name if name else "ناشناس",
            "username": username,
            "bio": bio,
            "telegram_id": clicker_id
        }
    except:
        return {
            "name": "کاربر ناشناس",
            "username": "نامشخص",
            "bio": "ندارد",
            "telegram_id": clicker_id
        }

def get_owner_name(owner_id):
    """دریافت نام صاحب لینک برای نمایش در پیام تله"""
    try:
        chat = bot.get_chat(owner_id)
        first_name = chat.first_name or ""
        last_name = chat.last_name or ""
        return f"{first_name} {last_name}".strip()
    except:
        return "صاحب پروفایل"

def is_user_member(user_id):
    """بررسی عضویت در کانال"""
    for channel in CHANNELS:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except:
            return False
    return True

def send_report_after_delay(link_code, owner_id, clicker_id, capture_text, capture_photo, delay=75):
    """ارسال گزارش به صاحب لینک بعد از تاخیر"""
    time.sleep(delay)
    
    c.execute("SELECT cancelled FROM pending_reports WHERE link_code = ? AND clicker_id = ? AND owner_id = ? ORDER BY id DESC LIMIT 1", 
              (link_code, clicker_id, owner_id))
    result = c.fetchone()
    
    if not result or result[0] == False:
        clicker_info = get_clicker_info(clicker_id)
        
        report_text = (
            f"🎯 **یک فضول در تله افتاد!** 😂\n\n"
            f"👤 **نام:** {clicker_info['name']}\n"
            f"🆔 **یوزرنیم:** {clicker_info['username']}\n"
            f"📝 **بیوگرافی:** {clicker_info['bio']}\n"
            f"⏰ **زمان:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"{capture_text}"
        )
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(InlineKeyboardButton("📩 پیام ناشناس", callback_data=f"msg_{clicker_id}"))
        
        if clicker_info['username'] != "ندارد" and clicker_info['username'] != "نامشخص":
            username_clean = clicker_info['username'].replace('@', '')
            if username_clean:
                keyboard.add(InlineKeyboardButton("👤 مشاهده پروفایل", url=f"https://t.me/{username_clean}"))
        
        try:
            if capture_photo:
                bot.send_photo(owner_id, capture_photo, caption=report_text, reply_markup=keyboard, parse_mode='Markdown')
            else:
                bot.send_message(owner_id, report_text, reply_markup=keyboard, parse_mode='Markdown')
        except:
            pass

# ---------- کیبورد دائمی ----------
def get_main_reply_keyboard():
    keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=False)
    keyboard.add(KeyboardButton("🔗 دریافت لینک من"))
    keyboard.add(KeyboardButton("💰 خرید اشتراک پرو"))
    keyboard.add(KeyboardButton("🛡 خرید سپر"))
    keyboard.add(KeyboardButton("🖼 تنظیم عکس مچ‌گیری"))
    keyboard.add(KeyboardButton("✏️ تنظیم متن مچ‌گیری"))
    keyboard.add(KeyboardButton("📖 راهنما"))
    return keyboard

def show_panel(chat_id):
    bot.send_message(chat_id, "👋 به پنل کاربری خود خوش آمدید.", reply_markup=get_main_reply_keyboard())

# ---------- هندلر دکمه‌های Reply ----------
@bot.message_handler(func=lambda message: True)
def handle_reply_buttons(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text
    
    if not is_user_member(user_id):
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("🔹 کانال اول", url="https://t.me/film01385"))
        keyboard.add(InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership"))
        bot.reply_to(message, "👋 برای استفاده از ربات ابتدا در کانال عضو شوید:", reply_markup=keyboard)
        return
    
    if text == "🔗 دریافت لینک من":
        link = generate_link(user_id)
        inline_keyboard = InlineKeyboardMarkup()
        inline_keyboard.add(
            InlineKeyboardButton("📋 کپی لینک", callback_data=f"copy_{user_id}"),
            InlineKeyboardButton("🔒 مخفی کردن", callback_data="hide_link")
        )
        bot.send_message(chat_id, f"🔗 **لینک اختصاصی شما:**\n\n`{link}`", reply_markup=inline_keyboard, parse_mode='Markdown')
    
    elif text == "💰 خرید اشتراک پرو":
        bot.send_message(chat_id, "💰 بخش خرید اشتراک پرو در حال توسعه است.\nبه زودی...")
    
    elif text == "🛡 خرید سپر":
        bot.send_message(chat_id, "🛡 بخش خرید سپر در حال توسعه است.\nبه زودی...")
    
    elif text == "🖼 تنظیم عکس مچ‌گیری":
        msg = bot.send_message(chat_id, "🖼 لطفاً عکس مورد نظر خود را ارسال کنید:")
        bot.register_next_step_handler(msg, receive_capture_photo)
    
    elif text == "✏️ تنظیم متن مچ‌گیری":
        msg = bot.send_message(chat_id, "✏️ لطفاً متن مورد نظر خود را ارسال کنید:")
        bot.register_next_step_handler(msg, receive_capture_text)
    
    elif text == "📖 راهنما":
        help_text = (
            "📚 **راهنمای ربات مچ‌گیری**\n\n"
            "1️⃣ روی دکمه «دریافت لینک من» کلیک کنید\n"
            "2️⃣ لینک را در بیوگرافی خود قرار دهید\n"
            "3️⃣ هر کس روی لینک کلیک کند، مشخصاتش برای شما ارسال می‌شود\n\n"
            "✨ می‌توانید متن و عکس تله را شخصی‌سازی کنید."
        )
        bot.send_message(chat_id, help_text, parse_mode='Markdown')
    
    else:
        bot.send_message(chat_id, "❌ لطفاً از دکمه‌های زیر استفاده کنید.", reply_markup=get_main_reply_keyboard())

# ---------- هندلر استارت (بخش اصلی تله) ----------
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    text = message.text
    
    # بررسی اگر کاربر با لینک اختصاصی وارد شده باشد
    if text.startswith("/start track_"):
        code = text.split("track_")[1]
        owner_id = get_owner_id_by_code(code)
        clicker_id = user_id
        
        if owner_id and owner_id != clicker_id:
            # ذخیره کلیک در دیتابیس
            c.execute("INSERT INTO clicks (link_code, clicker_id, ip, user_agent) VALUES (?, ?, ?, ?)", 
                      (code, clicker_id, "N/A", "N/A"))
            conn.commit()
            
            capture_text = get_user_capture_text(owner_id)
            capture_photo = get_user_capture_photo(owner_id)
            
            # ذخیره در pending_reports
            c.execute("INSERT INTO pending_reports (link_code, owner_id, clicker_id, expires_at) VALUES (?, ?, ?, ?)",
                      (code, owner_id, clicker_id, datetime.now() + timedelta(seconds=75)))
            conn.commit()
            
            # دریافت نام صاحب لینک
            owner_name = get_owner_name(owner_id)
            
            # ========== پیام تله به کلیک‌کننده ==========
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("❌ عدم ارسال گزارش فضولی", callback_data=f"cancel_{code}_{clicker_id}"))
            
            trap_message = (
                f"⚠️ **نبايد اين فضولی رو ميکردی!**\n\n"
                f"الان اين فضوليت برای {owner_name} ارسال شد، "
                f"بهتره قبل از اينکه بياد ببينه، خودت بهش بگی داشتی فضولی ميکردی 😂\n\n"
                f"برای عدم ارسال دکمه زیر را فشار دهید (فرصت شما 1 دقیقه و 15 ثانیه)\n\n"
                f"❌ عدم ارسال گزارش فضولی"
            )
            
            try:
                bot.send_message(clicker_id, trap_message, reply_markup=keyboard, parse_mode='Markdown')
            except Exception as e:
                print(f"Error sending trap: {e}")
            
            # استارت تایمر 75 ثانیه
            timer_thread = threading.Thread(
                target=send_report_after_delay,
                args=(code, owner_id, clicker_id, capture_text, capture_photo, 75)
            )
            timer_thread.start()
            
        elif owner_id == clicker_id:
            bot.send_message(clicker_id, "⚠️ شما روی لینک خودتان کلیک کردید!")
        else:
            bot.send_message(clicker_id, "❌ لینک نامعتبر است!")
    
    # نمایش پنل به کاربر
    if is_user_member(user_id):
        show_panel(message.chat.id)
    else:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("🔹 کانال اول", url="https://t.me/film01385"))
        keyboard.add(InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership"))
        bot.reply_to(message, "👋 برای استفاده از ربات ابتدا در کانال عضو شوید:", reply_markup=keyboard)

# ---------- هندلر دکمه‌های Inline ----------
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    if call.data == "check_membership":
        if is_user_member(user_id):
            bot.edit_message_text("✅ عضویت شما تأیید شد!", chat_id, call.message.message_id)
            show_panel(chat_id)
        else:
            bot.answer_callback_query(call.id, "❌ شما هنوز عضو نشده‌اید!", show_alert=True)
    
    elif call.data.startswith("copy_"):
        owner_id = call.data.split("_")[1]
        link = f"https://t.me/{BOT_USERNAME}?start=track_{owner_id}"
        bot.send_message(chat_id, f"🔗 لینک اختصاصی شما:\n`{link}`", parse_mode='Markdown')
        bot.answer_callback_query(call.id, "✅ لینک ارسال شد!")
    
    elif call.data == "hide_link":
        bot.edit_message_text("🔗 لینک مخفی شد.", chat_id, call.message.message_id)
        bot.answer_callback_query(call.id)
    
    elif call.data.startswith("cancel_"):
        _, code, clicker_id = call.data.split("_")
        clicker_id = int(clicker_id)
        
        if user_id != clicker_id:
            bot.answer_callback_query(call.id, "این دکمه مال تو نیست!", show_alert=True)
            return
        
        c.execute("UPDATE pending_reports SET cancelled = TRUE WHERE link_code = ? AND clicker_id = ?", (code, clicker_id))
        conn.commit()
        
        bot.edit_message_text(
            "✅ **گزارش فضولی ارسال نشد!**\n\nاين فرصت رو غنيمت بدون و ديگه فضولی نکن.",
            chat_id,
            call.message.message_id,
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id, "گزارش کنسل شد!")
    
    elif call.data.startswith("msg_"):
        target_id = int(call.data.split("_")[1])
        bot.send_message(chat_id, "✍️ **پیام ناشناس خود را بنویسید:**", parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(chat_id, lambda m: send_anonymous_message(m, target_id))
        bot.answer_callback_query(call.id)

# ---------- ارسال پیام ناشناس ----------
def send_anonymous_message(message, target_id):
    sender_id = message.from_user.id
    if message.text:
        try:
            bot.send_message(target_id, f"📩 **پیام ناشناس:**\n\n{message.text}", parse_mode='Markdown')
            bot.send_message(sender_id, "✅ پیام شما **ناشناس** ارسال شد.", parse_mode='Markdown')
        except Exception as e:
            bot.send_message(sender_id, f"❌ خطا: {e}")
    else:
        bot.send_message(sender_id, "❌ لطفاً فقط متن ارسال کنید.")

# ---------- دریافت تنظیمات ----------
def receive_capture_text(message):
    user_id = message.from_user.id
    text = message.text
    save_user_settings(user_id, text=text)
    bot.send_message(message.chat.id, f"✅ متن تله ذخیره شد:\n\n{text}")
    show_panel(message.chat.id)

def receive_capture_photo(message):
    user_id = message.from_user.id
    if message.photo:
        photo_id = message.photo[-1].file_id
        save_user_settings(user_id, photo_id=photo_id)
        bot.send_message(message.chat.id, "✅ عکس تله ذخیره شد.")
    else:
        bot.send_message(message.chat.id, "❌ لطفاً یک عکس ارسال کنید.")
    show_panel(message.chat.id)

# ---------- مسیرهای Flask ----------
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.get_data().decode('UTF-8'))
        bot.process_new_updates([update])
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 500

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
