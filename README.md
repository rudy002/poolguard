# PoolGuard 🏊

AI-powered pool surveillance system running in real time on an NVIDIA Jetson Orin Nano Super.

## Goal

Automatically detect the presence of people within a defined pool zone, using an existing IP camera feed, as the foundation for an alerting system (fall detection, unsupervised presence).

## Tech stack

- **Hardware**: Jetson Orin Nano Super (8GB) + NVMe SSD for storage
- **Video pipeline**: NVIDIA DeepStream 7.1 (native, GStreamer)
- **Detection model**: PeopleNet (NVIDIA TAO, INT8, via NGC)
- **Tracking**: NvDCF (DeepStream multi-object tracker)
- **Zone analytics**: nvdsanalytics (ROI filtering, based on each person's ground point)
- **Camera**: RTSP H.265 stream, 1920x1080, 25fps (Hikvision)
- **Python bindings**: `pyds` 1.2.0 (NVIDIA-AI-IOT/deepstream_python_apps, compiled for DeepStream 7.1 / Python 3.10)

## Architecture

RTSP camera -> DeepStream (decode, PeopleNet, tracking, pool ROI)
                    |
    Python script (gst-python + pyds) reads roiStatus metadata in real time
                    |
         [Coming next] Alert logic -> Telegram bot / Dashboard

Geometric detection (Level 1, "is the person inside the zone") happens directly in DeepStream/GPU for performance. Business logic (Level 2, "should an alert fire") will be handled in Python, reading the metadata produced by DeepStream.

## Repo structure

configs/
  config_infer_peoplenet.txt            # PeopleNet inference config
  config_nvdsanalytics.txt              # pool zone definition (polygon)
  dsnvanalytics_tracker_config.txt      # tracker config
  deepstream_app_peoplenet.txt.example  # full pipeline (template, no credentials)
common/                                 # GStreamer helper modules (from NVIDIA's deepstream_python_apps)
poolguard_alert.py                      # Python pipeline reading roiStatus in real time

## Setup

1. Download PeopleNet from NGC (nvidia/tao/peoplenet:pruned_quantized_decrypted_v2.3.4)
2. Copy deepstream_app_peoplenet.txt.example to deepstream_app_peoplenet.txt and fill in your camera's RTSP URL
3. Run: deepstream-app -c deepstream_app_peoplenet.txt
4. Run the Python alert-reading script: python3 poolguard_alert.py rtsp://<your-camera-url>

## Progress

- [x] Stable DeepStream pipeline (25 FPS) on a real camera feed
- [x] Person detection + tracking
- [x] Pool zone definition and visualization
- [x] Python script reading roiStatus metadata in real time (validated on live feed)
- [ ] Alert logic (duration tracking, Telegram bot)
- [ ] Next.js dashboard
- [ ] Annotated video recording (NVENC)

## Debugging notes worth sharing

A severe performance bug (FPS stuck around 7 instead of 25) was traced back to the Jetson's screen auto-sleeping, which throttled display rendering independently of CPU/GPU/network (all healthy). Fixed via gsettings set org.gnome.desktop.session idle-delay 0.