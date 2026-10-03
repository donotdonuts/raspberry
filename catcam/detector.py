"""Watches the litter cam, logs every visit to data/visits.csv and decides pee / poop.

Run:  python -m catcam.detector          (on the VM this runs as the catcam-detector service)
"""
import logging
import os
import subprocess
import threading
import time
from collections import deque
from datetime import datetime

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from ultralytics import YOLO  # noqa: E402

from . import tray_check  # noqa: E402
from .common import (CLIPS, CROPS, POSTURE_MODEL, VISIT_FIELDS, VISITS_CSV, ZONE_FILE,  # noqa: E402
                     append_row, ensure_dirs, load_config, load_zone)

log = logging.getLogger("catcam")
COCO_CAT = 15


class Reader(threading.Thread):
    """Reads the stream nonstop, keeps the newest frame + a short pre-roll buffer, feeds the clip recorder."""

    def __init__(self, url, fps, preroll_s):
        super().__init__(daemon=True)
        self.url = url
        self.lock = threading.Lock()
        self.buffer = deque(maxlen=int(fps * preroll_s))
        self.latest = None
        self.latest_ts = 0.0
        self.recorder = None

    def run(self):
        while True:
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                log.warning("Can't open stream %s, retrying in 5 s", self.url)
                time.sleep(5)
                continue
            log.info("Stream connected")
            fails = 0
            while fails < 50:
                ok, frame = cap.read()
                if not ok:
                    fails += 1
                    time.sleep(0.1)
                    continue
                fails = 0
                with self.lock:
                    self.latest, self.latest_ts = frame, time.time()
                    self.buffer.append(frame)
                    if self.recorder:
                        self.recorder.write(frame)
            log.warning("Stream lost, reconnecting")
            cap.release()
            time.sleep(3)

    def frame(self, max_age=2.0):
        with self.lock:
            if self.latest is None or time.time() - self.latest_ts > max_age:
                return None
            return self.latest

    def start_recording(self, path, fps):
        with self.lock:
            h, w = self.latest.shape[:2]
            rec = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
            for f in self.buffer:
                rec.write(f)
            self.recorder = rec

    def stop_recording(self):
        with self.lock:
            rec, self.recorder = self.recorder, None
        if rec:
            rec.release()


def to_browser_mp4(raw, final):
    """OpenCV's mp4v won't play in browsers; re-encode to H.264 in the background."""
    def work():
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-c:v", "libx264",
                            "-preset", "veryfast", "-crf", "28", "-movflags", "+faststart", str(final)])
        if r.returncode == 0:
            raw.unlink(missing_ok=True)
        else:
            raw.rename(final)
    threading.Thread(target=work, daemon=True).start()


class PostureModel:
    """v2 model (models/posture.pt from train.py). Reloads by itself after retraining."""

    def __init__(self):
        self.model, self.mtime = None, None

    def p_poop(self, crops):
        if not POSTURE_MODEL.exists() or not crops:
            return None
        mtime = POSTURE_MODEL.stat().st_mtime
        if mtime != self.mtime:
            self.model, self.mtime = YOLO(str(POSTURE_MODEL)), mtime
            log.info("Loaded posture model")
        names = {v: k for k, v in self.model.names.items()}
        results = self.model.predict(crops, imgsz=224, verbose=False)
        return float(np.mean([r.probs.data[names["poop"]].item() for r in results]))


def find_cat(model, frame, conf):
    r = model.predict(frame, classes=[COCO_CAT], conf=conf, verbose=False)[0]
    if len(r.boxes) == 0:
        return None
    i = int(r.boxes.conf.argmax())
    return r.boxes.xyxy[i].cpu().numpy().astype(int)


def zone_overlap(box, zone_mask):
    """Share of the cat's box that lies over the tray."""
    if box is None:
        return 0.0
    x1, y1, x2, y2 = np.clip(box, 0, [zone_mask.shape[1], zone_mask.shape[0]] * 2)
    area = max((x2 - x1) * (y2 - y1), 1)
    return float(np.count_nonzero(zone_mask[y1:y2, x1:x2])) / area


def decide(tray, duration, stillness, p_poop, cfg):
    """Combine the colour check (v1) with the posture model (v2, if trained). Returns type, confidence, source, rules_type."""
    if tray["poop"] and tray["wet"]:
        rules = ("both", 0.75)
    elif tray["poop"]:
        rules = ("poop", min(0.95, 0.6 + tray["poop_px"] / (cfg["tray_check"]["min_poop_px"] * 10)))
    elif tray["wet"]:
        rules = ("pee", 0.7)
    elif duration >= cfg["long_visit_s"] and stillness > 0.5:
        rules = ("poop", 0.35)   # nothing visible, long still visit: maybe buried poop
    else:
        rules = ("pee", 0.4)     # nothing visible: usually pee, could be buried poop

    if p_poop is None or tray["poop"]:
        return rules[0], rules[1], "rules", rules[0]
    if tray["wet"]:
        if p_poop > 0.85:
            return "both", 0.6, "rules+model", rules[0]
        return rules[0], rules[1], "rules", rules[0]
    kind = "poop" if p_poop >= 0.5 else "pee"
    return kind, max(p_poop, 1 - p_poop), "model", rules[0]


class Visit:
    def __init__(self, t_enter, before, vid):
        self.id = vid
        self.t_enter = t_enter
        self.last_in = t_enter
        self.t_left = None
        self.before = before
        self.boxes = []      # (aspect, cx, cy) while in the tray
        self.crops = []

    def sample(self, frame, box, now):
        self.last_in = now
        x1, y1, x2, y2 = box
        self.boxes.append(((y2 - y1) / max(x2 - x1, 1), (x1 + x2) / 2, (y1 + y2) / 2))
        pad = int(0.1 * max(x2 - x1, y2 - y1))
        h, w = frame.shape[:2]
        self.crops.append(frame[max(0, y1 - pad):min(h, y2 + pad), max(0, x1 - pad):min(w, x2 + pad)].copy())
        if len(self.crops) > 600:  # long visit: thin out to save memory
            self.crops = self.crops[::2]

    def posture(self, frame_w):
        if not self.boxes:
            return 0.0, 0.0
        b = np.array(self.boxes)
        moves = np.hypot(np.diff(b[:, 1]), np.diff(b[:, 2]))
        still = float(np.mean(moves < 0.02 * frame_w)) if len(moves) else 1.0
        return float(np.median(b[:, 0])), still

    def middle_crops(self):
        n = len(self.crops)
        return [self.crops[int(n * f)] for f in (0.25, 0.5, 0.75)] if n else []


def finish(visit, after, zone, frame_w, cfg, posture_model):
    duration = visit.t_left - visit.t_enter
    raw = CLIPS / f"{visit.id}_raw.mp4"
    row = {"id": visit.id, "start": fmt(visit.t_enter), "end": fmt(visit.t_left),
           "duration_s": round(duration, 1), "clip": ""}

    if duration < cfg["sniff_s"]:
        raw.unlink(missing_ok=True)
        row.update(type="sniff", confidence=1.0, source="rules", rules_type="sniff")
        append_row(VISITS_CSV, VISIT_FIELDS, row)
        log.info("Sniff (%.0f s), not a toilet visit", duration)
        return

    tray = tray_check.analyze(visit.before, after, zone, cfg["tray_check"])
    aspect, stillness = visit.posture(frame_w)
    crops = visit.middle_crops()
    p_poop = posture_model.p_poop(crops)
    kind, conf, source, rules_type = decide(tray, duration, stillness, p_poop, cfg)

    cv2.imwrite(str(CLIPS / f"{visit.id}_before.jpg"), visit.before)
    cv2.imwrite(str(CLIPS / f"{visit.id}_after.jpg"), after)
    cv2.imwrite(str(CLIPS / f"{visit.id}_tray.jpg"), tray["debug"])
    for i, c in enumerate(crops, 1):
        cv2.imwrite(str(CROPS / f"{visit.id}_{i}.jpg"), c)
    to_browser_mp4(raw, CLIPS / f"{visit.id}.mp4")

    row.update(type=kind, confidence=round(conf, 2), source=source, rules_type=rules_type,
               poop_px=tray["poop_px"], wet_px=tray["wet_px"], aspect=round(aspect, 2),
               stillness=round(stillness, 2), p_poop_model="" if p_poop is None else round(p_poop, 2),
               clip=f"{visit.id}.mp4")
    append_row(VISITS_CSV, VISIT_FIELDS, row)
    log.info("Visit %s: %s (%.0f%%, %s), %.0f s, poop px %d, wet px %d",
             visit.id, kind, conf * 100, source, duration, tray["poop_px"], tray["wet_px"])


def fmt(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    ensure_dirs()
    model = YOLO(cfg["yolo_model"])
    posture_model = PostureModel()
    reader = Reader(cfg["stream_url"], cfg["stream_fps"], cfg["preroll_s"])
    reader.start()

    zone = zone_mask = None
    zone_mtime = None
    last_empty = None
    visit = None
    state = "idle"   # idle -> entering -> in_visit <-> leaving -> settling -> idle
    period = 1.0 / cfg["detect_hz"]

    while True:
        t0 = time.time()
        frame = reader.frame()
        if frame is None:
            time.sleep(0.5)
            continue

        # Tray zone: reload when zone_picker.py saves a new one.
        mtime = ZONE_FILE.stat().st_mtime if ZONE_FILE.exists() else None
        if mtime != zone_mtime or (zone_mask is not None and zone_mask.shape != frame.shape[:2]):
            zone_mtime = mtime
            zone = load_zone(frame.shape)
            if zone is None:
                log.warning("No tray zone yet. Run zone_picker.py on the Mac.")
            else:
                zone_mask = np.zeros(frame.shape[:2], np.uint8)
                cv2.fillPoly(zone_mask, [zone], 1)
                log.info("Tray zone loaded")
        if zone is None:
            time.sleep(5)
            continue

        now = time.time()
        box = find_cat(model, frame, cfg["cat_conf"])
        overlap = zone_overlap(box, zone_mask)
        in_zone = overlap >= cfg["zone_overlap_min"]
        near = overlap > 0

        if state == "idle":
            if not near:
                last_empty = frame.copy()
            if in_zone and last_empty is not None:
                vid = datetime.fromtimestamp(now).strftime("%Y%m%d-%H%M%S")
                visit = Visit(now, last_empty, vid)
                reader.start_recording(CLIPS / f"{vid}_raw.mp4", cfg["stream_fps"])
                state = "entering"
                log.info("Cat in tray zone")
        elif state == "entering":
            if in_zone:
                visit.sample(frame, box, now)
                if now - visit.t_enter >= cfg["enter_s"]:
                    state = "in_visit"
                    log.info("Visit started")
            elif now - visit.last_in > cfg["miss_grace_s"]:
                reader.stop_recording()
                (CLIPS / f"{visit.id}_raw.mp4").unlink(missing_ok=True)
                visit, state = None, "idle"
        elif state in ("in_visit", "leaving"):
            if in_zone:
                visit.sample(frame, box, now)
                state = "in_visit"
            elif now - visit.last_in > cfg["miss_grace_s"]:
                state = "leaving"
                if now - visit.last_in >= cfg["exit_s"]:
                    visit.t_left = visit.last_in
                    state = "settling"
                    log.info("Cat left, waiting for the litter to settle")
        elif state == "settling":
            if in_zone:   # she came back: same visit
                visit.sample(frame, box, now)
                visit.t_left, state = None, "in_visit"
            else:
                waited = now - visit.t_left
                if (waited >= cfg["settle_s"] and not near) or waited >= cfg["settle_max_s"]:
                    reader.stop_recording()
                    try:
                        finish(visit, frame.copy(), zone, frame.shape[1], cfg, posture_model)
                    except Exception:
                        log.exception("Failed to finish visit %s", visit.id)
                    last_empty = frame.copy() if not near else last_empty
                    visit, state = None, "idle"

        time.sleep(max(0.0, period - (time.time() - t0)))


if __name__ == "__main__":
    main()
