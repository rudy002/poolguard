"""API de monitoring PoolGuard (FastAPI).

Tourne en service separe du pipeline : les deux ne communiquent que par fichiers
(status.json, events.log, arm.flag/disarm.flag). Si l'un plante, l'autre continue.

Lancement : uvicorn monitor_api:app --host 0.0.0.0 --port 8000
"""
import json
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

BASE_DIR = Path(__file__).resolve().parent
STATUS_FILE = BASE_DIR / "status.json"
EVENTS_FILE = BASE_DIR / "events.log"
ARM_FLAG = BASE_DIR / "arm.flag"
DISARM_FLAG = BASE_DIR / "disarm.flag"

# Au-dela de 10s sans mise a jour du status (ecrit toutes les 2s), le pipeline est considere mort
PIPELINE_STALE_SECONDS = 10

app = FastAPI(title="PoolGuard Monitor")


@app.get("/api/status")
def get_status():
    """Etat courant du systeme, lu depuis status.json ecrit par le pipeline."""
    try:
        status = json.loads(STATUS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"online": False, "armed": None, "alert": None}
    online = (time.time() - status.get("updated_at", 0)) < PIPELINE_STALE_SECONDS
    return {"online": online, "armed": status.get("armed"), "alert": status.get("alert")}


@app.get("/api/events")
def get_events(limit: int = 20):
    """Les derniers evenements (alertes, armements...), du plus recent au plus ancien."""
    try:
        lines = EVENTS_FILE.read_text().splitlines()
    except FileNotFoundError:
        return []
    events = [json.loads(line) for line in lines if line.strip()]
    return list(reversed(events[-limit:]))


@app.post("/api/arm")
def arm():
    """Demande l'armement : pose arm.flag, ramasse par le pipeline a la frame suivante."""
    ARM_FLAG.touch()
    return {"ok": True}


@app.post("/api/disarm")
def disarm():
    """Demande le desarmement : pose disarm.flag."""
    DISARM_FLAG.touch()
    return {"ok": True}


@app.get("/")
def index():
    """Sert la page de monitoring."""
    return FileResponse(BASE_DIR / "monitor.html")
