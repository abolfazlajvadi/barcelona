import sqlite3
import threading
import time
import requests
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ---------- تنظیمات ----------
TOKEN = "8981742192:AAHC8z6u6GifXgMIafvzv0tn_Q2LV1mM2bQ"
BOT_USERNAME = "nevergivup_bot"
BASE_URL = "https://barcelona-l5tu.onrender.com"

# زرین‌پال
ZP_MERCHANT_ID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # 🔁 این رو از زرین‌پال بگیر
ZP_REQUEST_URL = "https://api.zarinpal.com/pg/v4/payment/request.json"
ZP_VERIFY_URL = "https://api.zarinpal.com/pg/v4/payment/verify.json"
ZP_START_PAY = "https://www.zarinpal.com/pg/StartPay/"

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

c.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
    user_id INTEGER PRIMARY KEY,
    expires_at DATETIME
)""")

c.execute("""CREATE TABLE IF NOT EXISTS pending_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    authority TEXT UNIQUE,
    amount INTEGER,
    days INTEGER,
    created_at DATETIME
)""")

conn.commit()

# ---------- توابع اشتراک ----------
def has_active_subscription(user_id):
    c.execute("SELECT expires_at FROM subscriptions WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row:
        expires_at = datetime.fromisoformat(row[0])
        if expires_at > datetime.now():
            return True
        else:
            c.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
            conn.commit()
    return False

def add_subscription(user_id, days):
    current = datetime.now()
    c.execute("SELECT expires_at FROM subscriptions WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row:
        old_expires = datetime.fromisoformat(row[0])
        if old_expires > current:
            new_expires = old_expires + timedelta(days=days)
        else:
            new_expires = current + timedelta(days=days)
    else:
        new_expires = current + timedelta(days=days)
    
    c.execute("INSERT OR REPLACE INTO subscriptions (user_id, expires_at) VALUES (?, ?)",
              (user_id, new_expires.isoformat()))
    conn.commit()
    return new_expires

def get_subscription_info(user_id):
    c.execute("SELECT expires_at FROM subscriptions WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row:
        expires_at = datetime.fromisoformat(row[0])
        return expires_at
    return None

# ---------- توابع پرداخت ----------
def create_payment_link(user_id, amount, days):
    """ایجاد لینک پرداخت زرین‌پال و ذخیره در pending_payments"""
    authority = str(uuid.uuid4()).replace("-", "")[:20]
    callback_url = f"{BASE_URL}/verify?user_id={user_id}&days={days}"
    
    data = {
        "merchant_id": ZP_MERCHANT_ID,
        "amount": amount,
        "callback_url": callback_url,
        "description": f"خرید اشتراک {days} روزه ربات تله",
        "metadata": {"mobile": "", "email": ""}
    }
    
    try:
        response = requests.post(ZP_REQUEST_URL, json=data)
        result = response.json()
        
        if result.get("data", {}).get("code") == 100:
            authority = result["data"]["authority"]
            
            # ذخیره در دیتابیس
            c.execute("INSERT INTO pending_payments (user_id, authority, amount, days, created_at) VALUES (?, ?, ?, ?, ?)",
                      (user_id, authority, amount, days, datetime.now().isoformat()))
            conn.commit()
            
            pay_link = f"{ZP_START_PAY}{authority}"
            return pay_link, None
        else:
            return None, "خطا در اتصال به درگاه پرداخت"
    except Exception as e:
        return None, str(e)

def verify_payment(authority, amount):
    """تایید تراکنش زرین‌پال"""
    data = {
        "merchant_id": ZP_MERCHANT_ID,
        "amount": amount,
        "authority": authority
    }
    
    try:
        response = requests.post(ZP_VERIFY_URL, json=data)
        result = response.json()
        
        if result.get("data", {}).get("code") == 100:
            return True, result["data"]["ref_id"]
        else:
            return False, result.get("errors", {}).get("code", "خطا")
    except Exception as e:
        return False, str(e)

# ---------- توابع اصلی ----------
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
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("💬 پیام ناشناس", callback_data=f"anon_{clicker_id}_{owner_id}"),
            InlineKeyboardButton("📝 بیوگرافی", callback_data=f"bio_{clicker_id}_{owner_id}"),
            InlineKeyboardButton("📨 پیوی", callback_data=f"pv_{clicker_id}_{owner_id}"),
            InlineKeyboardButton("🖼 عکس پروفایل", callback_data=f"photo_{clicker_id}_{owner_id}")
        )
        
        report_msg = f"🎯 **یک فضول در تله افتاد!**\n\n👤 نام: {clicker_name}\n⏰ زمان: {datetime.now().strftime('%H:%M:%S')}"
        try:
            bot.send_message(owner_id, report_msg, parse_mode='Markdown', reply_markup=keyboard)
        except:
            pass

# ---------- هندلر استارت ----------
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
        bot.send_message(user_id, "👋 به ربات خوش آمدی.\nبرای دریافت لینک /link رو بفرست.\nبرای خرید اشتراک: /buy")

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

# ========== ۴ دکمه اصلی + بررسی اشتراک ==========
def check_subscription_and_forward(call, feature_name):
    user_id = call.from_user.id
    if not has_active_subscription(user_id):
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("💰 خرید اشتراک", callback_data="buy_subscription"))
        bot.send_message(
            user_id,
            f"❌ **دسترسی غیرفعال**\n\nشما برای استفاده از قابلیت «{feature_name}» باید اشتراک تهیه کنید.\n\n"
            f"برای خرید اشتراک دکمه زیر رو بزن 👇",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id, "ابتدا اشتراک بخرید!")
        return False
    return True

@bot.callback_query_handler(func=lambda call: call.data.startswith("anon_"))
def anonymous_message(call):
    if not check_subscription_and_forward(call, "پیام ناشناس"):
        return
    _, clicker_id, owner_id = call.data.split("_")
    bot.answer_callback_query(call.id, "در حال ارسال پیام ناشناس...")
    bot.send_message(call.message.chat.id, "🔧 قابلیت پیام ناشناس به زودی اضافه می‌شه.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("bio_"))
def show_bio(call):
    if not check_subscription_and_forward(call, "مشاهده بیوگرافی"):
        return
    _, clicker_id, owner_id = call.data.split("_")
    bot.answer_callback_query(call.id)
    try:
        chat = bot.get_chat(int(clicker_id))
        bio = getattr(chat, 'bio', None)
        if bio:
            bot.send_message(call.message.chat.id, f"📝 **بیوگرافی کاربر:**\n\n{bio}", parse_mode='Markdown')
        else:
            bot.send_message(call.message.chat.id, "❌ این کاربر بیوگرافی تنظیم نکرده است.")
    except:
        bot.send_message(call.message.chat.id, "❌ امکان نمایش بیوگرافی وجود ندارد.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("pv_"))
def send_pv(call):
    if not check_subscription_and_forward(call, "ارسال پیوی"):
        return
    _, clicker_id, owner_id = call.data.split("_")
    bot.answer_callback_query(call.id)
    try:
        chat = bot.get_chat(int(clicker_id))
        username = chat.username
        if username:
            link = f"https://t.me/{username}"
        else:
            link = f"https://t.me/{clicker_id}"
        bot.send_message(call.message.chat.id, f"🔗 لینک پیوی:\n`{link}`", parse_mode='Markdown')
    except:
        bot.send_message(call.message.chat.id, "❌ امکان ساخت لینک پیوی وجود ندارد.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("photo_"))
def show_photo(call):
    if not check_subscription_and_forward(call, "مشاهده عکس پروفایل"):
        return
    _, clicker_id, owner_id = call.data.split("_")
    bot.answer_callback_query(call.id)
    try:
        photos = bot.get_user_profile_photos(int(clicker_id), limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            bot.send_photo(call.message.chat.id, file_id, caption=f"🖼 عکس پروفایل کاربر")
        else:
            bot.send_message(call.message.chat.id, "❌ عکس پروفایل ندارد")
    except:
        bot.send_message(call.message.chat.id, "❌ امکان نمایش عکس وجود ندارد.")

# ========== خرید اشتراک (زرین‌پال) ==========
@bot.message_handler(commands=['buy', 'subscribe'])
def buy_subscription(message):
    user_id = message.from_user.id
    info = get_subscription_info(user_id)
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("💰 اشتراک ۱ ماهه - ۱۰,۰۰۰ تومان", callback_data="pay_30_10000"),
        InlineKeyboardButton("💰 اشتراک ۳ ماهه - ۲۵,۰۰۰ تومان", callback_data="pay_90_25000"),
        InlineKeyboardButton("💰 اشتراک ۶ ماهه - ۴۵,۰۰۰ تومان", callback_data="pay_180_45000")
    )
    
    if info:
        days_left = (info - datetime.now()).days
        status = f"✅ اشتراک فعال تا {info.strftime('%Y/%m/%d')} ({days_left} روز باقی مونده)"
    else:
        status = "❌ اشتراک فعالی ندارید"
    
    bot.send_message(
        user_id,
        f"💳 **خرید اشتراک**\n\n{status}\n\n"
        f"یکی از گزینه‌های زیر رو انتخاب کن:\n\n"
        f"📌 پرداخت از طریق زرین‌پال (کلیه کارت‌های عضو شتاب)",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def handle_payment(call):
    _, days, amount = call.data.split("_")
    days = int(days)
    amount = int(amount)
    user_id = call.from_user.id
    
    bot.answer_callback_query(call.id, "در حال ساخت لینک پرداخت...")
    
    pay_link, error = create_payment_link(user_id, amount, days)
    if pay_link:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("💳 پرداخت آنلاین", url=pay_link))
        keyboard.add(InlineKeyboardButton("🔄 بررسی وضعیت", callback_data=f"check_pay_{days}_{amount}"))
        
        bot.send_message(
            user_id,
            f"✅ لینک پرداخت ساخته شد.\n\n"
            f"💰 مبلغ: {amount:,} تومان\n"
            f"📅 مدت: {days} روز\n\n"
            f"🔗 روی دکمه زیر بزن تا به درگاه پرداخت بری.\n"
            f"بعد از پرداخت، اشتراکت خودکار فعال میشه.",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    else:
        bot.send_message(user_id, f"❌ خطا در ساخت لینک پرداخت: {error}\nلطفاً بعداً تلاش کن.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_pay_"))
def check_payment_status(call):
    bot.answer_callback_query(call.id, "وضعیت پرداخت بررسی شد")
    buy_subscription(call.message)

# ========== وب‌هوک تایید پرداخت ==========
@app.route('/verify', methods=['GET'])
def verify_payment_route():
    user_id = request.args.get('user_id')
    days = request.args.get('days')
    authority = request.args.get('Authority')
    status = request.args.get('Status')
    
    if not user_id or not days or not authority:
        return "پارامترهای ناقص", 400
    
    user_id = int(user_id)
    days = int(days)
    
    if status != "OK":
        return "پرداخت ناموفق یا توسط کاربر لغو شده است", 400
    
    # پیدا کردن مبلغ از دیتابیس
    c.execute("SELECT amount FROM pending_payments WHERE authority = ? AND user_id = ?", (authority, user_id))
    row = c.fetchone()
    if not row:
        return "تراکنش یافت نشد", 404
    
    amount = row[0]
    
    # تایید پرداخت
    success, ref_id = verify_payment(authority, amount)
    
    if success:
        # افزودن اشتراک
        new_expires = add_subscription(user_id, days)
        
        # حذف از pending_payments
        c.execute("DELETE FROM pending_payments WHERE authority = ?", (authority,))
        conn.commit()
        
        # اطلاع به کاربر
        try:
            bot.send_message(
                user_id,
                f"✅ **پرداخت شما با موفقیت تایید شد!**\n\n"
                f"🎉 اشتراک {days} روزه شما فعال شد.\n"
                f"📅 اعتبار تا {new_expires.strftime('%Y/%m/%d')}\n\n"
                f"حالا می‌تونی از همه دکمه‌ها استفاده کنی.",
                parse_mode='Markdown'
            )
        except:
            pass
        
        return f"پرداخت با موفقیت تایید شد. کد رهگیری: {ref_id}", 200
    else:
        return f"پرداخت تایید نشد. کد خطا: {ref_id}", 400

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
