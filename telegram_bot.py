import requests
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_alert(message: str) -> bool:
    if not TOKEN or not CHAT_ID:
        print("[TG] Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID", flush=True)
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=12,
        )
        ok = r.status_code == 200
        if not ok:
            print(f"[TG] HTTP {r.status_code}: {r.text[:200]}", flush=True)
        return ok
    except Exception as e:
        print(f"[TG] Error: {e}", flush=True)
        return False
