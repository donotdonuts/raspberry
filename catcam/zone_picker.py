"""Click the 4 corners of the litter tray. Run on the Mac.

    python3 -m catcam.zone_picker --push ubuntu@catcam-vm      # grab a frame from the stream, send zone to the VM
    python3 -m catcam.zone_picker --image test.jpg             # use a saved photo instead

Click = add corner · z = undo · Enter = save · Esc = quit
"""
import argparse
import json
import os
import subprocess

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from .common import ZONE_FILE, load_config  # noqa: E402


def grab_frame(url):
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    frame = None
    for _ in range(30):   # skip the first frames, like fswebcam -S
        ok, f = cap.read()
        if ok:
            frame = f
    cap.release()
    if frame is None:
        raise SystemExit(f"Couldn't read from {url}. Is Tailscale on and the Pi streaming?")
    return frame


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image")
    p.add_argument("--url")
    p.add_argument("--push", metavar="USER@HOST", help="copy zone.json to the VM after saving")
    args = p.parse_args()

    frame = cv2.imread(args.image) if args.image else grab_frame(args.url or load_config()["stream_url"])
    pts = []

    def on_click(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN:
            pts.append([x, y])

    win = "Click the tray corners - Enter to save"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_click)
    while True:
        view = frame.copy()
        if pts:
            cv2.polylines(view, [np.array(pts, np.int32)], len(pts) > 2, (0, 255, 0), 2)
            for x, y in pts:
                cv2.circle(view, (x, y), 4, (0, 0, 255), -1)
        cv2.imshow(win, view)
        key = cv2.waitKey(30) & 0xFF
        if key == 27:
            return
        if key == ord("z") and pts:
            pts.pop()
        if key in (13, 10) and len(pts) >= 3:
            break
    cv2.destroyAllWindows()

    h, w = frame.shape[:2]
    ZONE_FILE.write_text(json.dumps({"points": pts, "frame_size": [w, h]}))
    cv2.imwrite(str(ZONE_FILE.with_suffix(".jpg")), view)
    print(f"Saved {ZONE_FILE} ({len(pts)} corners)")
    if args.push:
        subprocess.run(["scp", str(ZONE_FILE), f"{args.push}:catcam/catcam/zone.json"], check=True)
        print("Sent to the VM. The detector picks it up within a few seconds.")


if __name__ == "__main__":
    main()
