import requests
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_alert(message: str):
    if not TOKEN or not CHAT_ID:
        print("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            print("Telegram alert sent successfully")
            return True
        else:
            print("Telegram error:", r.text)
            return False
    except Exception as e:
        print("Telegram exception:", e)
        return False
