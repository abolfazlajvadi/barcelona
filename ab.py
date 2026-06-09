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

# زرین‌پال (برای پرداخت لغو گزارش)
ZP_MERCHANT_ID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # 🔁 بعداً جایگزین کن
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

# جدول برای پیگیری پرداخت‌های لغو گزارش
c.execute("""CREATE TABLE IF NOT EXISTS cancel_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER,
    user_id INTEGER,
    authority TEXT UNIQUE,
    amount INTEGER,
    status TEXT DEFAULT 'pending',
    created_at DATETIME
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

def create_cancel_payment(user_id, report_id, amount=65000):
    """ایجاد لینک پرداخت برای لغو گزارش"""
    authority = str(uuid.uuid4()).replace("-", "")[:20]
    callback_url = f"{BASE_URL}/verify_cancel?user_id={user_id}&report_id={report_id}"
    
    data = {
        "merchant_id": ZP_MERCHANT_ID,
        "amount": amount,
        "callback_url": callback_url,
        "description": f"لغو ارسال گزارش فضولی - ربات تله",
        "metadata": {"mobile": "", "email": ""}
    }
    
    try:
        response = requests.post(ZP_REQUEST_URL, json=data)
        result = response.json()
        
        if result.get("data", {}).get("code") == 100:
            authority = result["data"]["authority"]
            
            c.execute("INSERT INTO cancel_payments (report_id, user_id, authority, amount, created_at) VALUES (?, ?, ?, ?, ?)",
                      (report_id, user_id, authority, amount, datetime.now().isoformat()))
            conn.commit()
            
            pay_link = f"{ZP_START_PAY}{authority}"
            return pay_link, None
        else:
            return None, "خطا در اتصال به درگاه پرداخت"
    except Exception as e:
        return None, str(e)

def delete_message_later(chat_id, message_id, delay, clicker_id, owner_name, report_id, link_code, owner_id):
    time.sleep(delay)
    
    # بررسی اینکه آیا پرداخت لغو انجام شده یا نه
    c.execute("SELECT status FROM cancel_payments WHERE report_id = ? AND status = 'paid'", (report_id,))
    paid = c.fetchone()
    
    if paid:
        # قبلاً لغو شده با پرداخت
        return
    
    # حذف پیام تله
    try:
        bot.delete_message(chat_id, message_id)
    except:
        pass
    
    # بررسی اینکه آیا کاربر روی دکمه لغو زده (بدون پرداخت)
    c.execute("SELECT cancelled FROM pending_reports WHERE id = ?", (report_id,))
    result = c.fetchone()
    
    if result and result[0] == False:
        # ارسال گزارش به صاحب لینک
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
        
        # پیام اتمام زمان به فضول
        final_message = f"⏰ **زمان شما تمام شد!**\n\nگزارش فضولی شما به {owner_name} ارسال گردید.\n\nآگه توام میخوای مجبقییه رو بگیری، از پنل زیر پیام..."
        try:
            bot.send_message(clicker_id, final_message, parse_mode='Markdown')
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
            
            # دکمه جدید برای لغو گزارش با پرداخت
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("💳 لغو گزارش با پرداخت ۶,۵۰۰ تومان", callback_data=f"pay_cancel_{code}_{clicker_id}"))
            
            trap_message = (
                f"⚠️ **نبايد اين فضولی رو ميکردی!** 🥰\n\n"
                f"اگه نمیخوای {owner_name} بفهمه که به پروفایلش سر زدی، "
                f"می‌تونی با پرداخت فقط ۶,۵۰۰ تومان گزارش رو لغو کنی.\n\n"
                f"👇 روی دکمه زیر بزن و پرداخت رو انجام بده"
            )
            
            msg = bot.send_message(clicker_id, trap_message, reply_markup=keyboard, parse_mode='Markdown')
            
            # ذخیره در دیتابیس با آیدی گزارش
            c.execute("INSERT INTO pending_reports (link_code, owner_id, clicker_id, message_id, expires_at) VALUES (?, ?, ?, ?, ?)",
                      (code, owner_id, clicker_id, msg.message_id, datetime.now() + timedelta(seconds=75)))
            conn.commit()
            
            report_id = c.lastrowid
            
            threading.Thread(target=delete_message_later, args=(clicker_id, msg.message_id, 75, clicker_id, owner_name, report_id, code, owner_id)).start()
            
        elif owner_id == clicker_id:
            bot.send_message(clicker_id, "⚠️ این لینک مال خودته!")
        else:
            bot.send_message(clicker_id, "❌ لینک نامعتبر!")
    else:
        bot.send_message(user_id, "👋 به ربات خوش آمدی.\nبرای دریافت لینک /link رو بفرست.")

# ---------- دریافت لینک ----------
@bot.message_handler(commands=['link'])
def get_link(message):
    user_id = message.from_user.id
    link = generate_link(user_id)
    bot.send_message(user_id, f"🔗 لینک اختصاصی تو:\n`{link}`\n\nاین لینک رو تو بیوگرافیت بذار.", parse_mode='Markdown')

# ---------- دکمه پرداخت برای لغو گزارش ----------
@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_cancel_"))
def pay_cancel_report(call):
    _, code, clicker_id = call.data.split("_")
    clicker_id = int(clicker_id)
    
    if call.from_user.id != clicker_id:
        bot.answer_callback_query(call.id, "این دکمه مال تو نیست!", show_alert=True)
        return
    
    # پیدا کردن report_id
    c.execute("SELECT id FROM pending_reports WHERE link_code = ? AND clicker_id = ? AND cancelled = FALSE ORDER BY id DESC LIMIT 1", 
              (code, clicker_id))
    row = c.fetchone()
    
    if not row:
        bot.answer_callback_query(call.id, "گزارشی یافت نشد!", show_alert=True)
        return
    
    report_id = row[0]
    
    # ساخت لینک پرداخت
    pay_link, error = create_cancel_payment(clicker_id, report_id, 65000)
    
    if pay_link:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("💳 پرداخت ۶,۵۰۰ تومان", url=pay_link))
        keyboard.add(InlineKeyboardButton("🔄 بررسی پس از پرداخت", callback_data=f"check_cancel_{report_id}"))
        
        # حذف پیام قبلی
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        bot.send_message(
            call.message.chat.id,
            f"💳 **لغو گزارش فضولی**\n\n"
            f"💰 مبلغ: ۶,۵۰۰ تومان (۶۵,۰۰۰ ریال)\n\n"
            f"✅ پس از پرداخت موفق، گزارش شما ارسال نخواهد شد.\n"
            f"🔗 روی دکمه زیر بزن تا وارد درگاه پرداخت بشی:\n\n"
            f"_در صورت بروز مشکل، دوباره تلاش کن._",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    else:
        bot.send_message(call.message.chat.id, f"❌ خطا در اتصال به درگاه پرداخت. لطفاً چند دقیقه بعد تلاش کن.\nخطا: {error}")

# ---------- بررسی وضعیت پرداخت ----------
@bot.callback_query_handler(func=lambda call: call.data.startswith("check_cancel_"))
def check_cancel_status(call):
    _, report_id = call.data.split("_")
    report_id = int(report_id)
    
    c.execute("SELECT status FROM cancel_payments WHERE report_id = ? ORDER BY id DESC LIMIT 1", (report_id,))
    row = c.fetchone()
    
    if row and row[0] == "paid":
        bot.answer_callback_query(call.id, "✅ پرداخت شما تایید شده! گزارش لغو شد.")
        bot.send_message(call.message.chat.id, "✅ **پرداخت شما قبلاً تایید شده!**\n\nگزارش فضولی ارسال نخواهد شد.")
    else:
        bot.answer_callback_query(call.id, "هنوز پرداختی ثبت نشده. لطفاً ابتدا پرداخت کن.")
        bot.send_message(call.message.chat.id, "⏳ هنوز پرداختی ثبت نشده.\nلطفاً ابتدا پرداخت رو انجام بده و بعد این دکمه رو بزن.")

# ---------- وب‌هوک تایید پرداخت (لغو گزارش) ----------
@app.route('/verify_cancel', methods=['GET'])
def verify_cancel_payment():
    user_id = request.args.get('user_id')
    report_id = request.args.get('report_id')
    authority = request.args.get('Authority')
    status = request.args.get('Status')
    
    if not user_id or not report_id or not authority:
        return "پارامترهای ناقص", 400
    
    user_id = int(user_id)
    report_id = int(report_id)
    
    if status != "OK":
        return "پرداخت ناموفق یا توسط کاربر لغو شده است", 400
    
    # پیدا کردن مبلغ
    c.execute("SELECT amount FROM cancel_payments WHERE authority = ? AND user_id = ? AND report_id = ?", 
              (authority, user_id, report_id))
    row = c.fetchone()
    if not row:
        return "تراکنش یافت نشد", 404
    
    amount = row[0]
    
    # تایید پرداخت با زرین‌پال
    data = {
        "merchant_id": ZP_MERCHANT_ID,
        "amount": amount,
        "authority": authority
    }
    
    try:
        response = requests.post(ZP_VERIFY_URL, json=data)
        result = response.json()
        
        if result.get("data", {}).get("code") == 100:
            # پرداخت موفق
            c.execute("UPDATE cancel_payments SET status = 'paid' WHERE authority = ?", (authority,))
            
            # علامت زدن گزارش به عنوان cancelled
            c.execute("UPDATE pending_reports SET cancelled = TRUE WHERE id = ?", (report_id,))
            conn.commit()
            
            # اطلاع به کاربر
            try:
                bot.send_message(
                    user_id,
                    f"✅ **پرداخت شما با موفقیت تایید شد!**\n\n"
                    f"گزارش فضولی شما لغو گردید و برای صاحب لینک ارسال نخواهد شد.\n\n"
                    f"🙏 از شما متشکریم.",
                    parse_mode='Markdown'
                )
            except:
                pass
            
            return f"✅ پرداخت موفق. گزارش لغو شد. کد رهگیری: {result['data']['ref_id']}", 200
        else:
            return f"❌ پرداخت تایید نشد. کد خطا: {result.get('errors', {}).get('code', 'unknown')}", 400
    except Exception as e:
        return f"خطا: {e}", 500

# ---------- ۴ دکمه برای کاربر اول (بدون اشتراک - رایگان) ----------
@bot.callback_query_handler(func=lambda call: call.data.startswith("anon_"))
def anonymous_message(call):
    _, clicker_id, owner_id = call.data.split("_")
    bot.answer_callback_query(call.id, "در حال ارسال پیام ناشناس...")
    bot.send_message(call.message.chat.id, "🔧 قابلیت پیام ناشناس به زودی اضافه می‌شه.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("bio_"))
def show_bio(call):
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
