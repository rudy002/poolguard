"""API de monitoring et de controle PoolGuard (FastAPI).

Tourne en service separe du pipeline (poolguard-monitor) et reste TOUJOURS allume :
c'est la telecommande du systeme, y compris pour rallumer un pipeline eteint.

- Etat : lit status.json / events.log ecrits par le pipeline (IPC par fichiers)
- Armement : pose arm.flag / disarm.flag, ramasses par le pipeline
- ON/OFF : demarre/arrete le service systemd "poolguard" (regle sudoers dediee)
- Telegram : ecoute les commandes /arm /disarm /status /on /off (thread, 1 seul
  lecteur autorise par bot Telegram -> l'ecoute vit ici, PAS dans le pipeline)

Lancement : uvicorn monitor_api:app --host 0.0.0.0 --port 8000
"""
import json
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from notifications import send_telegram_alert, get_telegram_command

BASE_DIR = Path(__file__).resolve().parent
STATUS_FILE = BASE_DIR / "status.json"
EVENTS_FILE = BASE_DIR / "events.log"
ARM_FLAG = BASE_DIR / "arm.flag"
DISARM_FLAG = BASE_DIR / "disarm.flag"

PIPELINE_SERVICE = "poolguard"
# Au-dela de 10s sans mise a jour du status (ecrit toutes les 2s), le pipeline est considere mort
PIPELINE_STALE_SECONDS = 10

app = FastAPI(title="PoolGuard Monitor")


def pipeline_service_running():
    """Le service systemd du pipeline est-il actif ?"""
    r = subprocess.run(["systemctl", "is-active", "--quiet", PIPELINE_SERVICE])
    return r.returncode == 0


def set_pipeline_power(on):
    """Allume/eteint le service pipeline via systemd.
    Necessite la regle sudoers dediee (NOPASSWD sur ces 2 commandes exactes)."""
    action = "start" if on else "stop"
    r = subprocess.run(
        ["sudo", "-n", "/usr/bin/systemctl", action, PIPELINE_SERVICE],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"[POWER] Echec systemctl {action}: {r.stderr.strip()}")
    return r.returncode == 0


def read_status():
    try:
        return json.loads(STATUS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


@app.get("/api/status")
def get_status():
    """Etat complet : service allume ?, pipeline vivant ?, arme ?, alerte ?"""
    running = pipeline_service_running()
    status = read_status()
    online = (
        running and status is not None
        and (time.time() - status.get("updated_at", 0)) < PIPELINE_STALE_SECONDS
    )
    return {
        "service_running": running,
        "online": online,
        "armed": status.get("armed") if (online and status) else None,
        "alert": status.get("alert") if (online and status) else None,
    }


@app.get("/api/events")
def get_events(limit: int = 20):
    """Les derniers evenements, du plus recent au plus ancien."""
    try:
        lines = EVENTS_FILE.read_text().splitlines()
    except FileNotFoundError:
        return []
    events = [json.loads(line) for line in lines if line.strip()]
    return list(reversed(events[-limit:]))


@app.post("/api/arm")
def arm():
    ARM_FLAG.touch()
    return {"ok": True}


@app.post("/api/disarm")
def disarm():
    DISARM_FLAG.touch()
    return {"ok": True}


@app.post("/api/power/on")
def power_on():
    return {"ok": set_pipeline_power(True)}


@app.post("/api/power/off")
def power_off():
    return {"ok": set_pipeline_power(False)}


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "monitor.html")


# --- Ecoute des commandes Telegram (thread de fond) ---

def _handle_telegram_command(command):
    if command == "/arm":
        if not pipeline_service_running():
            send_telegram_alert("⚠️ PoolGuard est eteint : envoie /on d'abord")
            return
        ARM_FLAG.touch()  # le pipeline confirme lui-meme une fois le flag ramasse
    elif command == "/disarm":
        if not pipeline_service_running():
            send_telegram_alert("⚠️ PoolGuard est eteint (donc deja sans surveillance)")
            return
        DISARM_FLAG.touch()
    elif command == "/on":
        send_telegram_alert("⏻ PoolGuard: demarrage du systeme...")
        set_pipeline_power(True)
    elif command == "/off":
        ok = set_pipeline_power(False)
        send_telegram_alert("⛔ PoolGuard: systeme eteint (plus de surveillance ni d'enregistrement). /on pour rallumer" if ok else "❌ Echec de l'arret")
    elif command == "/status":
        if not pipeline_service_running():
            send_telegram_alert("Statut PoolGuard: ⛔ eteint (/on pour rallumer)")
            return
        status = read_status()
        stale = status is None or (time.time() - status.get("updated_at", 0)) >= PIPELINE_STALE_SECONDS
        if stale:
            send_telegram_alert("Statut PoolGuard: ⏳ demarrage en cours...")
        elif status.get("alert"):
            send_telegram_alert("Statut PoolGuard: 🚨 ALERTE en cours !")
        else:
            send_telegram_alert(f"Statut PoolGuard: {'🔒 Arme' if status.get('armed') else '🔓 Desarme'}")


def _telegram_loop():
    while True:
        try:
            command = get_telegram_command()
            if command:
                print(f"[TELEGRAM] Commande recue: {command}")
                _handle_telegram_command(command)
        except Exception as e:
            print(f"[TELEGRAM] Erreur boucle commandes: {e}")
        time.sleep(3)


threading.Thread(target=_telegram_loop, daemon=True).start()
