import json
import os
import time

STATUS_FILE = "status.json"
EVENTS_FILE = "events.log"
MAX_EVENTS_LINES = 500  # garde le fichier petit (rotation simple)


def write_status(armed, alert_active):
    """Ecrit l'etat courant dans status.json (lu par l'API de monitoring).
    Ecriture atomique : fichier temporaire puis renommage, pour qu'un lecteur
    ne tombe jamais sur un fichier a moitie ecrit."""
    status = {
        "armed": armed,
        "alert": alert_active,
        "updated_at": time.time(),
    }
    try:
        with open(STATUS_FILE + ".tmp", "w") as f:
            json.dump(status, f)
        os.replace(STATUS_FILE + ".tmp", STATUS_FILE)
    except Exception as e:
        print(f"[MONITOR] Echec ecriture status: {e}")


def log_event(kind, message):
    """Ajoute un evenement (une ligne JSON) dans events.log.
    kind: alert / alert_end / arm / disarm / terrace"""
    event = {"ts": time.time(), "kind": kind, "message": message}
    try:
        with open(EVENTS_FILE, "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        _rotate_events_if_needed()
    except Exception as e:
        print(f"[MONITOR] Echec ecriture evenement: {e}")


def _rotate_events_if_needed():
    """Si events.log depasse MAX_EVENTS_LINES, ne garde que la moitie recente."""
    with open(EVENTS_FILE) as f:
        lines = f.readlines()
    if len(lines) > MAX_EVENTS_LINES:
        with open(EVENTS_FILE + ".tmp", "w") as f:
            f.writelines(lines[-MAX_EVENTS_LINES // 2:])
        os.replace(EVENTS_FILE + ".tmp", EVENTS_FILE)
