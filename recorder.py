import subprocess
import time
import os

from camera_config import CAMERA_URL

RECORDINGS_DIR = "recordings"

_recording_process = None


def start_recording():
    """Demarre l'enregistrement de l'incident en cours. Ne fait rien si deja en cours."""
    global _recording_process
    if _recording_process is not None:
        return  # deja en train d'enregistrer

    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{RECORDINGS_DIR}/alerte_{timestamp}.mkv"

    cmd = ["ffmpeg", "-i", CAMERA_URL, "-c", "copy", filename]
    _recording_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[RECORDER] Enregistrement demarre: {filename}")


def stop_recording():
    """Arrete proprement l'enregistrement en cours, s'il y en a un."""
    global _recording_process
    if _recording_process is None:
        return

    _recording_process.terminate()
    _recording_process.wait(timeout=5)
    _recording_process = None
    print("[RECORDER] Enregistrement arrete")
