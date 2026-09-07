"""Alerte "quelqu'un s'approche de la piscine" : capture, analyse d'age, Telegram.

Pourquoi ce module existe separement :
- l'analyse d'age a besoin du venv paddle, incompatible avec pyds/DeepStream
  -> elle tourne en SOUS-PROCESSUS (age_check.py), jamais dans le process video ;
- tout se passe dans un THREAD DAEMON : le pipeline video n'attend jamais.
  Meme si la camera, le modele ou Telegram sont lents ou plantent, la surveillance
  continue a 25 fps. Meme principe que notifications.py.

Chaine complete mesuree : ~4,4 s (0,4 s capture + 2,5 s analyse + Telegram).
"""
import os
import subprocess
import threading
import time

from camera_config import CAMERA_URL
from notifications import send_telegram_alert, send_telegram_photo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.expanduser('~/pytorch-env/bin/python3')
AGE_CHECK = os.path.join(BASE_DIR, 'age_check.py')
SNAPSHOT = '/tmp/poolguard_terrace.jpg'
ALERT_IMAGE = '/tmp/poolguard_terrace_alert.jpg'

CAPTURE_TIMEOUT = 15      # s : ffmpeg ne doit jamais rester bloque sur la camera
ANALYSE_TIMEOUT = 60      # s : chargement du modele + inference, large marge

_en_cours = threading.Lock()   # une seule analyse a la fois (evite d'empiler les process)


def _capture_frame(path):
    """Prend une image de la camera via une 2e connexion RTSP (comme recorder.py)."""
    r = subprocess.run(
        ['ffmpeg', '-y', '-rtsp_transport', 'tcp', '-i', CAMERA_URL,
         '-frames:v', '1', '-q:v', '2', path],
        capture_output=True, timeout=CAPTURE_TIMEOUT,
    )
    return r.returncode == 0 and os.path.exists(path)


def _analyser(box):
    """Lance age_check.py dans le venv. Retourne (score, verdict, hauteur) ou None."""
    cmd = [VENV_PYTHON, AGE_CHECK, SNAPSHOT,
           *[str(int(v)) for v in box], ALERT_IMAGE]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=ANALYSE_TIMEOUT)
    for ligne in reversed(r.stdout.strip().splitlines()):
        parties = ligne.split()
        if len(parties) == 3:
            try:
                return float(parties[0]), parties[1], int(parties[2])
            except ValueError:
                continue
    return None


def _worker(box):
    try:
        t0 = time.time()
        if not _capture_frame(SNAPSHOT):
            send_telegram_alert("⚠️ PoolGuard: person near the pool (snapshot failed)")
            return

        resultat = _analyser(box)
        if resultat is None:
            # L'analyse a echoue : on previent QUAND MEME avec la photo.
            # Une alerte sans verdict vaut mieux qu'une alerte perdue.
            send_telegram_photo(SNAPSHOT, "⚠️ PoolGuard: person near the pool")
            return

        score, verdict, hauteur = resultat
        if verdict == "MINEUR":
            legende = (f"🚨 PoolGuard: possible CHILD near the pool\n"
                       f"Confidence {score:.0%} — check the photo.")
        elif verdict == "INDETERMINE":
            legende = (f"⚠️ PoolGuard: person near the pool\n"
                       f"Too far to estimate age ({hauteur}px) — check the photo.")
        else:
            legende = (f"⚠️ PoolGuard: person near the pool\n"
                       f"Looks like an adult ({score:.0%} child) — check the photo.")

        image = ALERT_IMAGE if os.path.exists(ALERT_IMAGE) else SNAPSHOT
        send_telegram_photo(image, legende)
        print(f"[TERRACE] {verdict} score={score:.2f} h={hauteur}px "
              f"({time.time() - t0:.1f}s)")
    except subprocess.TimeoutExpired:
        print("[TERRACE] delai depasse (camera ou modele trop lent)")
        send_telegram_alert("⚠️ PoolGuard: person near the pool (analysis timed out)")
    except Exception as e:
        # Ne JAMAIS laisser une exception de ce thread affecter la surveillance.
        print(f"[TERRACE] echec: {e}")
    finally:
        if _en_cours.locked():
            _en_cours.release()


def declencher_alerte_terrasse(box):
    """Point d'entree, appele depuis le pipeline. Retourne immediatement.

    box = [x1, y1, x2, y2] en coordonnees de l'image 1920x1080.
    Si une analyse est deja en cours, celle-ci est ignoree (pas d'empilement).
    """
    if not _en_cours.acquire(blocking=False):
        print("[TERRACE] analyse deja en cours, alerte ignoree")
        return
    threading.Thread(target=_worker, args=(box,), daemon=True).start()
