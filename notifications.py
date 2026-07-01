import requests
from telegram_config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

_last_update_id = None


def send_telegram_alert(message):
    """Envoie un message Telegram, sans bloquer le pipeline en cas d'echec."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=5)
    except Exception as e:
        print(f"[TELEGRAM] Echec envoi: {e}")


def get_telegram_command():
    """Verifie s'il y a une nouvelle commande Telegram (/arm, /disarm, /status).
    Retourne la commande (str) ou None s'il n'y en a pas."""
    global _last_update_id
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 0}
    if _last_update_id is not None:
        params["offset"] = _last_update_id + 1

    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
    except Exception as e:
        print(f"[TELEGRAM] Echec lecture commandes: {e}")
        return None

    if not data.get("ok") or not data.get("result"):
        return None

    command = None
    for update in data["result"]:
        _last_update_id = update["update_id"]
        message = update.get("message", {})
        text = message.get("text", "")
        if text.startswith("/"):
            command = text.strip()

    return command
