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
    full_link = f"https://t.me/{BOT_USERNAME}?start=track_{code}"
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

# ---------- ایجاد Reply Keyboard (صفحه‌کلید دائمی) ----------
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

# ---------- نمایش پنل کاربری ----------
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
        link_code = link.split('_')[-1]
        
        inline_keyboard = InlineKeyboardMarkup(row_width=2)
        inline_keyboard.add(
            InlineKeyboardButton("📋 کپی لینک من", callback_data=f"copy_{link_code}"),
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
            "به محض اینکه شخصی روی لینک شما کلیک کند، ربات اطلاعات کامل او را برای شما ارسال می‌کند:\n"
            "▫️ نام و نام خانوادگی\n"
            "▫️ آیدی (لینک ورود به پیوی)\n"
            "▫️ بیوگرافی\n"
            "▫️ عکس پروفایل\n\n"
            "**۲. اشتراک ویژه (پرو - ۳۰ روزه):**\n"
            "با تهیه اشتراک پرو، امکانات پیشرفته زیر در اختیار شما قرار می‌گیرد:\n"
            "🔹 **ارسال پیام ناشناس:** می‌توانید از طریق ربات، برای شخصی که در تله شما افتاده است به صورت کاملاً ناشناس پیام ارسال کنید.\n"
            "🔹 **مشاهده پروفایل افراد بدون آیدی:** اگر شخصی که در تله افتاده آیدی عمومی (Username) نداشته باشد، "
            "با اشتراک پرو همچنان می‌توانید عکس پروفایل و بیوگرافی او را مشاهده کنید.\n\n"
            "**۳. شخصی‌سازی تله (متن و عکس مچ‌گیری):**\n"
            "شما می‌توانید واکنش ربات به فردی که در تله می‌افتد را کاملاً شخصی‌سازی کنید:\n"
            "🔹 **تنظیم متن مچ‌گیری:** پیامی که فرد به محض کلیک روی لینک شما دریافت می‌کند را تغییر دهید.\n"
            "🔹 **تنظیم عکس مچ‌گیری:** علاوه بر متن، می‌توانید یک تصویر دلخواه تنظیم کنید تا به محض ورود شخص، آن عکس نیز برای وی ارسال شود.\n\n"
            "💬 در صورت بروز هرگونه مشکل یا داشتن سوالات بیشتر، با @Ao_0077 در ارتباط باشید."
        )
        
        bot.send_message(chat_id, help_text, parse_mode='Markdown')
    
    else:
        bot.send_message(chat_id, "❌ لطفاً از دکمه‌های زیر استفاده کنید.", reply_markup=get_main_reply_keyboard())

# ---------- هندلر دستور start (قسمت اصلی تله) ----------
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
            
            # دریافت اطلاعات کلیک‌کننده
            clicker_info = get_clicker_info(clicker_id)
            capture_text = get_user_capture_text(owner_id)
            capture_photo = get_user_capture_photo(owner_id)
            
            # ========== 1. ارسال پیام تله به کلیک‌کننده (فضول) ==========
            trap_message = f"⚠️ **توجه! تو در تله افتادی!**\n\nفرد مورد نظر از بازدید تو مطلع شد.\n\n{capture_text}"
            
            try:
                if capture_photo:
                    bot.send_photo(clicker_id, capture_photo, caption=trap_message, parse_mode='Markdown')
                else:
                    bot.send_message(clicker_id, trap_message, parse_mode='Markdown')
            except Exception as e:
                print(f"Error sending trap to clicker: {e}")
            
            # ========== 2. ارسال گزارش به صاحب لینک ==========
            report_text = (
                f"🔔 **بازدید جدید!**\n\n"
                f"👤 **نام:** {clicker_info['name']}\n"
                f"🆔 **آیدی:** {clicker_info['username']}\n"
                f"📝 **بیو:** {clicker_info['bio']}\n"
                f"⏰ **زمان:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"🎯 {capture_text}"
            )
            
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("📩 ارسال پیام ناشناس", callback_data=f"msg_{clicker_id}"))
            
            try:
                if capture_photo:
                    bot.send_photo(owner_id, capture_photo, caption=report_text, reply_markup=keyboard, parse_mode='Markdown')
                else:
                    bot.send_message(owner_id, report_text, reply_markup=keyboard, parse_mode='Markdown')
            except Exception as e:
                print(f"Error sending report to owner: {e}")
            
        else:
            if owner_id == clicker_id:
                bot.send_message(clicker_id, "⚠️ شما روی لینک خودتان کلیک کردید! این بازدید گزارش نمی‌شود.")
            else:
                bot.send_message(clicker_id, "❌ لینک نامعتبر است!")
        
        # نمایش پنل به کاربر (چه صاحب لینک باشد چه کلیک‌کننده)
        if is_user_member(user_id):
            show_panel(message.chat.id)
        else:
            keyboard = InlineKeyboardMarkup(row_width=1)
            for channel in CHANNELS:
                display_name = CHANNEL_NAMES.get(channel, channel)
                keyboard.add(InlineKeyboardButton(f"🔹 {display_name}", url=f"https://t.me/{channel[1:]}"))
            keyboard.add(InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership"))
            bot.reply_to(message, "👋 برای استفاده از ربات ابتدا در کانال های زیر عضو شوید:", reply_markup=keyboard)
        
        return
    
    # start معمولی (بدون کد)
    if is_user_member(user_id):
        show_panel(message.chat.id)
    else:
        keyboard = InlineKeyboardMarkup(row_width=1)
        for channel in CHANNELS:
            display_name = CHANNEL_NAMES.get(channel, channel)
            keyboard.add(InlineKeyboardButton(f"🔹 {display_name}", url=f"https://t.me/{channel[1:]}"))
        keyboard.add(InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership"))
        bot.reply_to(message, "👋 برای استفاده از ربات ابتدا در کانال های زیر عضو شوید:", reply_markup=keyboard)

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
    
    elif call.data.startswith("copy_"):
        link_code = call.data.split("_")[1]
        link = f"https://t.me/{BOT_USERNAME}?start=track_{link_code}"
        bot.send_message(chat_id, f"🔗 لینک اختصاصی شما برای کپی:\n\n`{link}`", parse_mode='Markdown')
        bot.answer_callback_query(call.id, "✅ لینک برای کپی ارسال شد!")
    
    elif call.data == "hide_link":
        try:
            bot.edit_message_text("🔗 لینک شما مخفی شد. برای دریافت مجدد لینک، از پنل اصلی اقدام کنید.", chat_id, call.message.message_id)
        except:
            pass
        threading.Timer(2.0, lambda: show_panel(chat_id)).start()
    
    elif call.data.startswith("msg_"):
        target_id = int(call.data.split("_")[1])
        bot.send_message(chat_id, "✍️ **پیام ناشناس خود را بنویسید:**\n(فقط متن قابل ارسال است)", parse_mode='Markdown')
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
            bot.send_message(sender_id, f"❌ خطا در ارسال پیام: {e}")
    else:
        bot.send_message(sender_id, "❌ لطفاً فقط متن ارسال کنید.")

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
