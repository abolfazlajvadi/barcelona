from flask import Flask, request, redirect
import sqlite3
import requests
from datetime import datetime

app = Flask(__name__)
BOT_TOKEN = "8981742192:AAHC8z6u6GifXgMIafvzv0tn_Q2LV1mM2bQ"  # 🔁 عوض کن
BASE_URL = "https://your-domain.com"  # 🔁 عوض کن (بعد از دیپلوی وب سرویس)

def log_click(link, ip, ua):
    conn = sqlite3.connect("tracker.db")
    c = conn.cursor()
    c.execute("INSERT INTO clicks (link, ip, user_agent) VALUES (?, ?, ?)", (link, ip, ua))
    conn.commit()
    conn.close()

def get_telegram_id_by_link(link):
    conn = sqlite3.connect("tracker.db")
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users WHERE link = ?", (link,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def send_message_to_telegram(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text})
    except:
        pass

@app.route('/track/<code>')
def track(code):
    link = f"{BASE_URL}/track/{code}"
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    ua = request.headers.get('User-Agent', 'Unknown')
    log_click(link, ip, ua)
    telegram_id = get_telegram_id_by_link(link)
    if telegram_id:
        msg = f"⚠️ کسی روی لینک شما کلیک کرد!\nآی‌پی: {ip}\nمرورگر: {ua[:100]}"
        send_message_to_telegram(telegram_id, msg)
    return redirect("https://www.google.com")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)