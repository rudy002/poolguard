import subprocess
import time
import os

from camera_config import CAMERA_URL

RECORDINGS_DIR = "recordings"
MAX_RECORDING_SECONDS = 5 * 60  # plafond par fichier : ffmpeg s'arrete seul (securite disque plein)

_recording_process = None


def start_recording():
    """Demarre l'enregistrement de l'incident en cours. Ne fait rien si deja en cours."""
    global _recording_process
    if _recording_process is not None:
        if _recording_process.poll() is None:
            return  # deja en train d'enregistrer
        _recording_process = None  # ffmpeg s'est arrete seul (plafond de duree atteint)

    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{RECORDINGS_DIR}/alerte_{timestamp}.mkv"

    cmd = ["ffmpeg", "-i", CAMERA_URL, "-t", str(MAX_RECORDING_SECONDS), "-c", "copy", filename]
    _recording_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[RECORDER] Enregistrement demarre: {filename}")


def stop_recording():
    """Arrete proprement l'enregistrement en cours, s'il y en a un."""
    global _recording_process
    if _recording_process is None:
        return

    _recording_process.terminate()
    try:
        _recording_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _recording_process.kill()  # ffmpeg ne repond pas au terminate : arret force
    _recording_process = None
    print("[RECORDER] Enregistrement arrete")
