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
    cancelled BOOLEAN DEFAULT FALSE,
    paid BOOLEAN DEFAULT FALSE
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
    
    # چک کن که آیا پرداخت شده یا لغو شده
    c.execute("SELECT cancelled, paid FROM pending_reports WHERE clicker_id = ? ORDER BY id DESC LIMIT 1", (clicker_id,))
    result = c.fetchone()
    
    if result and (result[0] == True or result[1] == True):
        return  # اگه لغو شده یا پرداخت شده، پیام نفرست
    
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
    
    c.execute("SELECT cancelled, paid FROM pending_reports WHERE link_code = ? AND clicker_id = ? AND owner_id = ? ORDER BY id DESC LIMIT 1", 
              (link_code, clicker_id, owner_id))
    result = c.fetchone()
    
    # اگه لغو نشده و پرداخت نشده، گزارش بفرست
    if result and result[0] == False and result[1] == False:
        clicker_name = get_clicker_name(clicker_id)
        report_msg = f"🎯 **یک فضول در تله افتاد!**\n\n👤 نام: {clicker_name}\n⏰ زمان: {datetime.now().strftime('%H:%M:%S')}"
        try:
            bot.send_message(owner_id, report_msg, parse_mode='Markdown')
        except:
            pass

# ---------- صفحه پرداخت ----------
def show_payment_page(chat_id, link_code, clicker_id, owner_id, message_id):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("💳 پرداخت با کارت بانکی", callback_data=f"pay_{link_code}_{clicker_id}"),
        InlineKeyboardButton("🔙 انصراف", callback_data=f"cancel_pay_{link_code}_{clicker_id}")
    )
    
    payment_text = (
        f"💰 **درخواست پول**\n\n"
        f"با پرداخت فقط **6,500 تومان**، گزارش فضولی شما برای صاحب لینک ارسال نخواهد شد.\n\n"
        f"📊 **جزئیات:**\n"
        f"• لغو گزارش: 65,000 ریال\n"
        f"• مبلغ: 65,000 ریال\n\n"
        f"⬇️ برای پرداخت روی دکمه زیر کلیک کنید."
    )
    
    bot.send_message(chat_id, payment_text, reply_markup=keyboard, parse_mode='Markdown')

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
            keyboard.add(InlineKeyboardButton("❌ عدم ارسال گزارش فضولی 😊", callback_data=f"show_pay_{code}_{clicker_id}_{owner_id}"))
            
            trap_message = (
                f"⚠️ **نبايد اين فضولی رو ميکردی!** 🥰\n\n"
                f"الان اين فضوليت برای {owner_name} ارسال شد، "
                f"بهتره قبل از اينکه بياد ببينه، خودت بهش بگی داشتی فضولی ميکردی 😊\n\n"
                f"🕐 **زمان باقی‌مانده: ۱:۱۵**\n\n"
                f"برای عدم ارسال دکمه زیر را فشار دهید:\n\n"
                f"❌ عدم ارسال گزارش فضولی 😊"
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
        bot.send_message(user_id, "👋 به ربات خوش آمدی.\nبرای دریافت لینک /link رو بفرست.")

# ---------- دریافت لینک ----------
@bot.message_handler(commands=['link'])
def get_link(message):
    user_id = message.from_user.id
    link = generate_link(user_id)
    bot.send_message(user_id, f"🔗 لینک اختصاصی تو:\n`{link}`\n\nاین لینک رو تو بیوگرافیت بذار.", parse_mode='Markdown')

# ---------- هندلر دکمه‌ها ----------
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    data = call.data
    user_id = call.from_user.id
    
    # نمایش صفحه پرداخت
    if data.startswith("show_pay_"):
        _, _, link_code, clicker_id, owner_id = data.split("_")
        clicker_id = int(clicker_id)
        owner_id = int(owner_id)
        
        if user_id != clicker_id:
            bot.answer_callback_query(call.id, "این دکمه مال تو نیست!", show_alert=True)
            return
        
        # پیدا کردن message_id برای حذف پیام قبلی
        c.execute("SELECT message_id FROM pending_reports WHERE link_code = ? AND clicker_id = ? ORDER BY id DESC LIMIT 1", 
                  (link_code, clicker_id))
        result = c.fetchone()
        
        if result:
            try:
                bot.delete_message(call.message.chat.id, result[0])
            except:
                pass
        
        show_payment_page(call.message.chat.id, link_code, clicker_id, owner_id, result[0] if result else None)
        bot.answer_callback_query(call.id)
    
    # پرداخت انجام شد
    elif data.startswith("pay_"):
        _, _, link_code, clicker_id = data.split("_")
        clicker_id = int(clicker_id)
        
        if user_id != clicker_id:
            bot.answer_callback_query(call.id, "این دکمه مال تو نیست!", show_alert=True)
            return
        
        # ثبت پرداخت در دیتابیس
        c.execute("UPDATE pending_reports SET paid = TRUE, cancelled = TRUE WHERE link_code = ? AND clicker_id = ?", 
                  (link_code, clicker_id))
        conn.commit()
        
        # حذف پیام پرداخت
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        # پیام تأیید پرداخت
        confirm_message = (
            "✅ **پرداخت با موفقیت انجام شد!**\n\n"
            "گزارش فضولی شما ارسال نشد.\n"
            "اين فرصت رو غنيمت بدون و ديگه فضولی نکن 😊"
        )
        bot.send_message(call.message.chat.id, confirm_message, parse_mode='Markdown')
        bot.answer_callback_query(call.id, "پرداخت موفق!")
    
    # انصراف از پرداخت
    elif data.startswith("cancel_pay_"):
        _, _, _, link_code, clicker_id = data.split("_")
        clicker_id = int(clicker_id)
        
        if user_id != clicker_id:
            bot.answer_callback_query(call.id, "این دکمه مال تو نیست!", show_alert=True)
            return
        
        # حذف پیام پرداخت
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        # برگردوندن پیام قبلی یا پیام انصراف
        bot.send_message(call.message.chat.id, "❌ از پرداخت انصراف دادید. گزارش فضولی ارسال خواهد شد.")
        bot.answer_callback_query(call.id, "انصراف از پرداخت")

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
