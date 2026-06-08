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

def get_clicker_info(clicker_id):
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
        
        # دریافت عکس پروفایل
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
    except:
        return {
            "name": "کاربر ناشناس",
            "username": "نامشخص",
            "bio": "ندارد",
            "photo_id": None,
            "telegram_id": clicker_id
        }

def delete_message_later(chat_id, message_id, delay, clicker_id, owner_name):
    time.sleep(delay)
    
    c.execute("SELECT cancelled, paid FROM pending_reports WHERE clicker_id = ? ORDER BY id DESC LIMIT 1", (clicker_id,))
    result = c.fetchone()
    
    if result and (result[0] == True or result[1] == True):
        return
    
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
    
    if result and result[0] == False and result[1] == False:
        clicker_info = get_clicker_info(clicker_id)
        
        # ========== قالب جدید پیام برای صاحب لینک ==========
        report_text = (
            f"🎯 **یک فضول در تله افتاد!** 😂\n\n"
            f"👤 **نام:** {clicker_info['name']}\n"
            f"🆔 **یوزرنیم:** {clicker_info['username']}\n"
            f"📝 **بیوگرافی:** {clicker_info['bio']}\n"
            f"⏰ **زمان:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        
        # ساخت دکمه‌ها
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📩 پیام ناشناس", callback_data=f"msg_{clicker_id}"),
            InlineKeyboardButton("👤 مشاهده پروفایل", callback_data=f"profile_{clicker_id}")
        )
        
        # ارسال پیام با عکس پروفایل (اگر وجود داشته باشد)
        try:
            if clicker_info['photo_id']:
                bot.send_photo(
                    owner_id, 
                    clicker_info['photo_id'], 
                    caption=report_text, 
                    reply_markup=keyboard, 
                    parse_mode='Markdown'
                )
            else:
                bot.send_message(owner_id, report_text, reply_markup=keyboard, parse_mode='Markdown')
        except Exception as e:
            print(f"Error sending report: {e}")

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
        
        c.execute("UPDATE pending_reports SET paid = TRUE, cancelled = TRUE WHERE link_code = ? AND clicker_id = ?", 
                  (link_code, clicker_id))
        conn.commit()
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
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
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        
        bot.send_message(call.message.chat.id, "❌ از پرداخت انصراف دادید. گزارش فضولی ارسال خواهد شد.")
        bot.answer_callback_query(call.id, "انصراف از پرداخت")
    
    # مشاهده پروفایل
    elif data.startswith("profile_"):
        target_id = int(data.split("_")[1])
        
        try:
            user = bot.get_chat(target_id)
            first_name = user.first_name or ""
            last_name = user.last_name or ""
            name = f"{first_name} {last_name}".strip()
            username = f"@{user.username}" if user.username else "ندارد"
            bio = user.bio if hasattr(user, 'bio') and user.bio else "ندارد"
            
            profile_text = (
                f"👤 **پروفایل کاربر**\n\n"
                f"**نام:** {name}\n"
                f"**یوزرنیم:** {username}\n"
                f"**بیوگرافی:** {bio}"
            )
            
            # دریافت عکس پروفایل
            try:
                photos = bot.get_user_profile_photos(target_id, limit=1)
                if photos.total_count > 0:
                    photo = photos.photos[0][-1].file_id
                    bot.send_photo(call.message.chat.id, photo, caption=profile_text, parse_mode='Markdown')
                else:
                    bot.send_message(call.message.chat.id, profile_text, parse_mode='Markdown')
            except:
                bot.send_message(call.message.chat.id, profile_text, parse_mode='Markdown')
                
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ خطا در دریافت اطلاعات: {e}")
        
        bot.answer_callback_query(call.id)
    
    # ارسال پیام ناشناس
    elif data.startswith("msg_"):
        target_id = int(data.split("_")[1])
        bot.send_message(call.message.chat.id, "✍️ **پیام ناشناس خود را بنویسید:**", parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, lambda m: send_anonymous_message(m, target_id))
        bot.answer_callback_query(call.id)

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
