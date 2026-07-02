# PoolGuard 🏊 — AI Pool Surveillance on the Edge

**Real-time drowning-risk prevention system** running 24/7 on an NVIDIA Jetson Orin Nano. It watches a swimming pool through an IP camera, detects people entering a danger zone with a GPU-accelerated neural network, and reacts in seconds: Telegram alert, on-screen warning, automatic video recording of the incident.

![Python](https://img.shields.io/badge/Python-3.10-blue?logo=python&logoColor=white)
![DeepStream](https://img.shields.io/badge/NVIDIA-DeepStream%207.1-76B900?logo=nvidia&logoColor=white)
![TensorRT](https://img.shields.io/badge/TensorRT-INT8-76B900?logo=nvidia&logoColor=white)
![Platform](https://img.shields.io/badge/Jetson-Orin%20Nano%208GB-76B900?logo=nvidia&logoColor=white)
![Status](https://img.shields.io/badge/status-in%20production%2024%2F7-success)

> 🎬 **Demo video coming soon** — live detection, alert flow and incident replay.

---

## The 30-second pitch

Home pool alarms are either intrusive (physical barriers) or dumb (water-surface sensors full of false positives). PoolGuard takes a different approach: **computer vision on an edge device**. No cloud, no subscription, no images leaving the house — a $250 Jetson board turns an existing security camera into an intelligent lifeguard.

- ⚡ **25 FPS sustained** end-to-end (1080p H.265 RTSP → inference → tracking → zone analytics → display)
- 🧠 **PeopleNet** (NVIDIA TAO) quantized to **INT8**, running on the Jetson's GPU via TensorRT
- 📱 **Telegram bot** for alerts and remote control (`/arm`, `/disarm`, `/status`)
- 🎥 **Automatic incident recording** (stream copy, zero re-encoding cost)
- 🔁 **Self-healing**: runs as a hardened systemd service — survives crashes, camera outages and reboots

## How it works

```mermaid
flowchart LR
    CAM[IP Camera<br/>RTSP H.265 1080p] --> DEC[NVDEC<br/>HW decoding]
    DEC --> INF[PeopleNet INT8<br/>TensorRT inference]
    INF --> TRK[NvDCF<br/>multi-object tracking]
    TRK --> ROI[nvdsanalytics<br/>pool polygon ROI]
    ROI --> OSD[On-screen display<br/>boxes + alert banner]
    ROI -. per-frame metadata .-> LOGIC[Alarm state machine<br/>Python]
    LOGIC --> TG[Telegram<br/>alerts + commands]
    LOGIC --> REC[ffmpeg incident<br/>recorder MKV]
```

**Two-level design** — the guiding architecture decision:

| Level | Question | Runs on |
|---|---|---|
| 1 — Geometry | *"Is this person inside the pool polygon?"* | GPU (DeepStream `nvdsanalytics`), 25×/s |
| 2 — Business logic | *"Should an alarm fire? Record? Notify?"* | Python state machine reading GPU metadata |

The alarm logic is deliberately simple and testable:

- **Auto-arm** after 30 min without anyone in the pool (or manual `/arm`)
- **Alert** after 3 s of continuous presence while armed → Telegram 🚨 + red banner + recording starts
- **Auto-resolve** after 30 s of empty pool → recording saved, system stays armed for the next event
- **Grace period** (1.5 s) absorbs detector flicker so a blinking bounding box never resets timers

## Engineering highlights

Things that don't show on a screenshot but made the project real:

- **Detection flicker resilience.** Raw tracker output alternates detected/lost every few frames. Requiring "continuous" presence naively would make alerts impossible — solved with a tolerance window in the state machine, validated with an accelerated simulation harness.
- **Non-blocking notifications.** Telegram calls run in daemon threads: a slow network can never freeze the video pipeline (the alert callback runs *inside* the GStreamer streaming thread).
- **Crash-proof recordings.** MKV over MP4, `ffmpeg -c copy` on a second RTSP connection: zero encoding load, and files stay playable even after a hard kill (no MP4 moov-atom corruption). Per-file duration cap protects the disk.
- **Graceful lifecycle.** SIGTERM handling flushes the recorder and tears the pipeline down cleanly, so `systemctl stop/restart` never corrupts an incident file.
- **Security hygiene.** Credentials live in gitignored config modules (nothing in `ps aux`, nothing in the repo), Telegram commands are sender-authenticated, and the git history was scrubbed with `git filter-repo` after an early credential leak — mistakes happen; cleaning them up properly is part of the job.
- **Real-world debugging.** Favorite war story: FPS mysteriously stuck at 7 instead of 25 with CPU/GPU/network all healthy. Root cause? The desktop's **screen auto-sleep** was throttling the display sink. One `gsettings` line after hours of profiling.

## Tech stack

| Layer | Choice |
|---|---|
| Hardware | NVIDIA Jetson Orin Nano Super 8 GB + 1 TB NVMe |
| Video pipeline | DeepStream 7.1 / GStreamer, Python bindings (`pyds` 1.2.0) |
| Detection | PeopleNet v2.3.4 (NVIDIA TAO), pruned + INT8 quantized |
| Tracking | NvDCF multi-object tracker |
| Zone analytics | `nvdsanalytics` ROI polygon |
| Notifications | Telegram Bot API (long-polling, threaded sends) |
| Recording | ffmpeg stream copy → MKV |
| Ops | systemd service (auto-start, auto-restart), journald logging |

## Repo structure

```
poolguard_alert.py     # main pipeline + alarm state machine
notifications.py       # Telegram: threaded alerts, authenticated commands
recorder.py            # incident recorder (capped duration, auto-restart)
poolguard.service      # systemd unit (24/7 operation)
configs/               # inference, tracker and ROI-polygon configs
common/                # GStreamer helpers (from NVIDIA samples)
```

Credentials (`camera_config.py`, `telegram_config.py`) and recordings are gitignored by design.

## Running it

```bash
# 1. Download PeopleNet from NGC (nvidia/tao/peoplenet:pruned_quantized_decrypted_v2.3.4)
# 2. Create the two gitignored config files:
#      camera_config.py    -> CAMERA_URL = "rtsp://user:pass@camera/..."
#      telegram_config.py  -> TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
# 3. Adjust the pool polygon in configs/config_nvdsanalytics.txt for your camera angle

# Manual run (verbose debug mode)
DEBUG_LOGS=1 python3 poolguard_alert.py

# Production: install as a service
sudo cp poolguard.service /etc/systemd/system/
sudo systemctl enable --now poolguard
journalctl -u poolguard -f
```

## Possible extensions

GPIO siren, Bluetooth speaker announcements, NVENC annotated re-encoding, TAO fine-tuning on pool-specific footage.

---

*Personal project — built to learn edge AI, embedded Linux and video pipelines from scratch, coming from a web development background. Every bug in the "engineering highlights" section was hit, diagnosed and fixed on real hardware.*
