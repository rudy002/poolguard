#!/usr/bin/env python3
"""Enregistrement de demo isole, INDEPENDANT du pipeline de production "poolguard".

Ouvre sa propre 2e connexion RTSP a la camera (deja valide : la camera accepte
plusieurs connexions simultanees, cf. recorder.py) et fait tourner un mini-pipeline
DeepStream separe qui ecrit directement dans un fichier MKV les images DEJA dessinees
(boxes rouge/vert + bandeau WARNING), sans jamais passer par un ecran ni une capture X11.

Pourquoi un script a part plutot qu'une modification de poolguard_alert.py :
un essai precedent qui divisait le flux GPU en 2 (ecran + fichier via un "tee") a fait
planter le pipeline (bug memoire GPU). Ici il n'y a qu'UNE seule branche de sortie
(comme en production), donc le meme risque n'existe pas. Et meme si CE script plante,
le vrai service de surveillance n'est pas touche.

Usage :
    sudo systemctl stop poolguard   # libere le GPU pour cette prise de demo
    python3 demo_record.py          # Ctrl+C pour arreter, fichier dans demo_recordings/
    sudo systemctl start poolguard  # remet la vraie surveillance en route
"""
import sys
sys.path.append('.')
import os
import time
import signal
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst
import pyds

from common.bus_call import bus_call
from poolguard_alert import (
    create_source_bin, PlatformInfo, TILED_OUTPUT_WIDTH, TILED_OUTPUT_HEIGHT,
    MUXER_OUTPUT_WIDTH, MUXER_OUTPUT_HEIGHT, MUXER_BATCH_TIMEOUT_USEC,
    PGIE_CLASS_ID_PERSON, NVDS_USER_META_OBJ_ANALYTICS, NVDS_USER_META_FRAME_ANALYTICS,
    OSD_PROCESS_MODE, OSD_DISPLAY_TEXT,
)
from notifications import send_telegram_alert
from camera_config import CAMERA_URL

ALERT_AFTER_SECONDS = 3
GRACE_PERIOD_SECONDS = 1.5

entry_time = None
last_seen_time = 0
alert_sent = False
display_warning_text = None


def probe(pad, info, u_data):
    global entry_time, last_seen_time, alert_sent, display_warning_text
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        return Gst.PadProbeReturn.OK

    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    while l_frame:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        l_obj = frame_meta.obj_meta_list
        while l_obj:
            try:
                obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
            except StopIteration:
                break
            l_user_meta = obj_meta.obj_user_meta_list
            while l_user_meta:
                try:
                    user_meta = pyds.NvDsUserMeta.cast(l_user_meta.data)
                    if user_meta.base_meta.meta_type == NVDS_USER_META_OBJ_ANALYTICS:
                        obj_info = pyds.NvDsAnalyticsObjInfo.cast(user_meta.user_meta_data)
                        if obj_info.roiStatus:
                            obj_meta.rect_params.border_color.set(1.0, 0.0, 0.0, 1.0)
                            obj_meta.rect_params.border_width = 4
                        else:
                            obj_meta.rect_params.border_color.set(0.0, 1.0, 0.0, 1.0)
                except StopIteration:
                    break
                try:
                    l_user_meta = l_user_meta.next
                except StopIteration:
                    break
            try:
                l_obj = l_obj.next
            except StopIteration:
                break

        now = time.time()
        l_user = frame_meta.frame_user_meta_list
        while l_user:
            try:
                user_meta = pyds.NvDsUserMeta.cast(l_user.data)
                if user_meta.base_meta.meta_type == NVDS_USER_META_FRAME_ANALYTICS:
                    frame_info = pyds.NvDsAnalyticsFrameMeta.cast(user_meta.user_meta_data)
                    person_in_pool = bool(frame_info.objInROIcnt) and frame_info.objInROIcnt.get('POOL', 0) > 0
                    if person_in_pool:
                        last_seen_time = now
                        if entry_time is None:
                            entry_time = now
                        if not alert_sent and (now - entry_time) >= ALERT_AFTER_SECONDS:
                            alert_sent = True
                            display_warning_text = "⚠️ WARNING - POOL"
                            print(">>> DEMO: person detected in the pool <<<")
                            send_telegram_alert("🚨 PoolGuard: person detected in the pool!")
                    else:
                        if entry_time is not None and (now - last_seen_time) > GRACE_PERIOD_SECONDS:
                            entry_time = None
                        if alert_sent and (now - last_seen_time) > GRACE_PERIOD_SECONDS:
                            alert_sent = False
                            display_warning_text = None
                            print(">>> DEMO: pool empty <<<")
            except StopIteration:
                break
            try:
                l_user = l_user.next
            except StopIteration:
                break

        if display_warning_text:
            display_meta = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
            display_meta.num_labels = 1
            text_params = display_meta.text_params[0]
            text_params.display_text = display_warning_text
            text_params.x_offset = 50
            text_params.y_offset = 50
            text_params.font_params.font_name = "Serif"
            text_params.font_params.font_size = 30
            text_params.font_params.font_color.set(1.0, 0.0, 0.0, 1.0)
            text_params.set_bg_clr = 1
            text_params.text_bg_clr.set(0.0, 0.0, 0.0, 1.0)
            pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)

        try:
            l_frame = l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK


def main():
    os.makedirs("demo_recordings", exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    out_file = os.path.abspath(f"demo_recordings/demo_{timestamp}.mkv")

    Gst.init(None)
    pipeline = Gst.Pipeline()

    streammux = Gst.ElementFactory.make("nvstreammux", "stream-muxer")
    pipeline.add(streammux)

    source_bin = create_source_bin(0, CAMERA_URL)
    pipeline.add(source_bin)
    sinkpad = streammux.request_pad_simple("sink_0")
    source_bin.get_static_pad("src").link(sinkpad)

    def make(kind, name):
        el = Gst.ElementFactory.make(kind, name)
        if not el:
            sys.stderr.write(f"Unable to create {kind}\n")
            sys.exit(1)
        pipeline.add(el)
        return el

    q1, q2, q3, q4, q5, q6, q7 = (make("queue", f"q{i}") for i in range(1, 8))
    pgie = make("nvinfer", "pgie")
    tracker = make("nvtracker", "tracker")
    analytics = make("nvdsanalytics", "analytics")
    tiler = make("nvmultistreamtiler", "tiler")
    nvvidconv = make("nvvideoconvert", "nvvidconv")
    nvosd = make("nvdsosd", "nvosd")
    convert2 = make("nvvideoconvert", "convert2")
    caps = make("capsfilter", "caps")
    encoder = make("x264enc", "encoder")
    parser = make("h264parse", "parser")
    mux = make("matroskamux", "mux")
    filesink = make("filesink", "filesink")

    streammux.set_property('width', MUXER_OUTPUT_WIDTH)
    streammux.set_property('height', MUXER_OUTPUT_HEIGHT)
    streammux.set_property('batch-size', 1)
    streammux.set_property('batched-push-timeout', MUXER_BATCH_TIMEOUT_USEC)
    streammux.set_property('live-source', 1)

    pgie.set_property('config-file-path', "configs/config_infer_peoplenet.txt")
    analytics.set_property("config-file", "configs/config_nvdsanalytics.txt")
    tiler.set_property("rows", 1)
    tiler.set_property("columns", 1)
    tiler.set_property("width", TILED_OUTPUT_WIDTH)
    tiler.set_property("height", TILED_OUTPUT_HEIGHT)
    nvosd.set_property('process-mode', OSD_PROCESS_MODE)
    nvosd.set_property('display-text', OSD_DISPLAY_TEXT)

    import configparser
    config = configparser.ConfigParser()
    config.read('configs/dsnvanalytics_tracker_config.txt')
    tconf = config['tracker']
    tracker.set_property('tracker-width', config.getint('tracker', 'tracker-width'))
    tracker.set_property('tracker-height', config.getint('tracker', 'tracker-height'))
    tracker.set_property('gpu_id', config.getint('tracker', 'gpu-id'))
    tracker.set_property('ll-lib-file', config.get('tracker', 'll-lib-file'))
    tracker.set_property('ll-config-file', config.get('tracker', 'll-config-file'))

    caps.set_property("caps", Gst.Caps.from_string("video/x-raw,format=I420"))
    encoder.set_property("speed-preset", "ultrafast")
    encoder.set_property("tune", "zerolatency")
    encoder.set_property("bitrate", 6000)
    filesink.set_property("location", out_file)

    streammux.link(q1); q1.link(pgie); pgie.link(q2); q2.link(tracker)
    tracker.link(q3); q3.link(analytics); analytics.link(q4); q4.link(tiler)
    tiler.link(q5); q5.link(nvvidconv); nvvidconv.link(q6); q6.link(nvosd)
    nvosd.link(q7); q7.link(convert2); convert2.link(caps)
    caps.link(encoder); encoder.link(parser); parser.link(mux); mux.link(filesink)

    analytics.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, probe, 0)

    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", bus_call, loop)

    def quit_on_signal():
        print("\nStopping, finalizing the file...")
        loop.quit()
        return GLib.SOURCE_REMOVE
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, quit_on_signal)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, quit_on_signal)

    print(f"Recording to {out_file} — Ctrl+C to stop")
    pipeline.set_state(Gst.State.PLAYING)
    try:
        loop.run()
    except Exception:
        pass
    pipeline.set_state(Gst.State.NULL)
    print(f"Saved: {out_file}")


if __name__ == '__main__':
    main()
