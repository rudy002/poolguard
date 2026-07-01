import requests
from telegram_config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID


def send_telegram_alert(message):
    """Envoie un message Telegram, sans bloquer le pipeline en cas d'echec."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=5)
    except Exception as e:
        print(f"[TELEGRAM] Echec envoi: {e}")
