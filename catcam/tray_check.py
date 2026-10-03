"""Before/after colour check of the litter tray.

Yellow litter + new dark brown/black blob after a visit  -> poop.
Yellow litter + new darker-yellow (wet) blob             -> pee.

Tune thresholds on saved photos:
    python -m catcam.tray_check data/clips/<id>_before.jpg data/clips/<id>_after.jpg -o debug.jpg
"""
import argparse

import cv2
import numpy as np

from .common import load_config, load_zone

KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))


def _blobs(mask, min_px):
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, KERNEL)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, KERNEL)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) >= min_px]
    return contours, int(sum(cv2.contourArea(c) for c in contours))


def analyze(before, after, zone, c):
    """Compare two empty-tray frames. Returns pixel counts, blobs and a debug picture."""
    x, y, w, h = cv2.boundingRect(zone)
    b = cv2.GaussianBlur(before[y:y + h, x:x + w], (5, 5), 0)
    a = cv2.GaussianBlur(after[y:y + h, x:x + w], (5, 5), 0)

    mask = np.zeros((h, w), np.uint8)
    cv2.fillPoly(mask, [zone - [x, y]], 255)
    if c["rim_px"] > 0:
        mask = cv2.erode(mask, np.ones((c["rim_px"] * 2 + 1,) * 2, np.uint8))
    inside = mask > 0

    hb = cv2.cvtColor(b, cv2.COLOR_BGR2HSV)
    ha = cv2.cvtColor(a, cv2.COLOR_BGR2HSV)
    vb = hb[..., 2].astype(np.float32)
    va = ha[..., 2].astype(np.float32)

    # Even out small overall brightness changes (camera auto-exposure) before comparing.
    litter_v = float(np.median(vb[inside]))
    va = np.clip(va * litter_v / max(float(np.median(va[inside])), 1.0), 0, 255)

    newly_dark = (vb - va) >= c["min_darkening"]
    dark_before = cv2.dilate((vb < litter_v * c["poop_v_ratio"]).astype(np.uint8), KERNEL, iterations=2) > 0
    dark_after = va < litter_v * c["poop_v_ratio"]
    poop_mask = inside & newly_dark & dark_after & ~dark_before

    litter_h = float(np.median(hb[..., 0][inside]))
    hue_diff = np.abs(ha[..., 0].astype(np.float32) - litter_h)
    hue_diff = np.minimum(hue_diff, 180 - hue_diff)
    wet_mask = (inside & newly_dark & ~dark_after & (va < litter_v * c["wet_v_ratio"])
                & (hue_diff <= c["wet_hue_tol"]))

    poop_blobs, poop_px = _blobs(poop_mask.astype(np.uint8) * 255, c["blob_min_px"])
    wet_blobs, wet_px = _blobs(wet_mask.astype(np.uint8) * 255, c["blob_min_px"])

    return {
        "poop_px": poop_px,
        "wet_px": wet_px,
        "poop": poop_px >= c["min_poop_px"],
        "wet": wet_px >= c["min_wet_px"],
        "debug": _debug_image(b, a, mask, poop_blobs, wet_blobs, poop_px, wet_px),
    }


def _debug_image(b, a, mask, poop_blobs, wet_blobs, poop_px, wet_px):
    rim, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    left, right = b.copy(), a.copy()
    for img in (left, right):
        cv2.drawContours(img, rim, -1, (0, 255, 0), 1)
    cv2.drawContours(right, wet_blobs, -1, (255, 128, 0), 2)   # blue-ish = wet / pee
    cv2.drawContours(right, poop_blobs, -1, (0, 0, 255), 2)    # red = poop
    out = np.hstack([left, right])
    scale = max(1.0, 480 / out.shape[1])
    out = cv2.resize(out, None, fx=scale, fy=scale)
    bar = np.full((28, out.shape[1], 3), 32, np.uint8)
    cv2.putText(bar, f"before | after   poop px: {poop_px}   wet px: {wet_px}", (6, 19),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return np.vstack([bar, out])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("-o", "--out", default="tray_debug.jpg")
    args = p.parse_args()
    before, after = cv2.imread(args.before), cv2.imread(args.after)
    zone = load_zone(before.shape)
    if zone is None:  # no tray zone yet: use the whole picture
        h, w = before.shape[:2]
        zone = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], np.int32)
    r = analyze(before, after, zone, load_config()["tray_check"])
    cv2.imwrite(args.out, r["debug"])
    verdict = "poop" if r["poop"] else "pee (wet spot)" if r["wet"] else "nothing new seen"
    print(f"poop px={r['poop_px']}  wet px={r['wet_px']}  ->  {verdict}   (debug picture: {args.out})")


if __name__ == "__main__":
    main()
