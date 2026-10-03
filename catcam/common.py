"""Shared paths, config and CSV helpers."""
import csv
import json
from pathlib import Path

import numpy as np
import yaml

PKG = Path(__file__).resolve().parent
ROOT = PKG.parent
DATA = ROOT / "data"
CLIPS = DATA / "clips"
CROPS = DATA / "crops"
SUMMARY = DATA / "summary"
MODELS = ROOT / "models"
VISITS_CSV = DATA / "visits.csv"
LABELS_CSV = DATA / "labels.csv"
ZONE_FILE = PKG / "zone.json"
POSTURE_MODEL = MODELS / "posture.pt"

VISIT_FIELDS = [
    "id", "start", "end", "duration_s", "type", "confidence", "source", "rules_type",
    "poop_px", "wet_px", "aspect", "stillness", "p_poop_model", "clip",
]
LABEL_FIELDS = ["id", "label", "labeled_at"]
LABELS = ["pee", "poop", "both", "nothing"]


def load_config():
    return yaml.safe_load((PKG / "config.yaml").read_text())


def load_zone(frame_shape=None):
    """Tray polygon as int32 Nx2 array, scaled to frame_shape (h, w) if given. None if not set yet."""
    if not ZONE_FILE.exists():
        return None
    z = json.loads(ZONE_FILE.read_text())
    pts = np.array(z["points"], dtype=np.float32)
    if frame_shape is not None and "frame_size" in z:
        zw, zh = z["frame_size"]
        h, w = frame_shape[:2]
        pts *= [w / zw, h / zh]
    return pts.astype(np.int32)


def ensure_dirs():
    for d in (DATA, CLIPS, CROPS, SUMMARY, MODELS):
        d.mkdir(parents=True, exist_ok=True)


def append_row(path, fields, row):
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerow(row)


def read_visits():
    if not VISITS_CSV.exists():
        return []
    with VISITS_CSV.open(newline="") as f:
        return list(csv.DictReader(f))


def read_labels():
    """visit id -> latest label."""
    if not LABELS_CSV.exists():
        return {}
    with LABELS_CSV.open(newline="") as f:
        return {r["id"]: r["label"] for r in csv.DictReader(f)}


def effective_type(visit, labels, unsure_below=0.5):
    """Your label wins; otherwise the detector's guess, or 'unsure' if it wasn't confident."""
    if visit["id"] in labels:
        return labels[visit["id"]]
    if visit["type"] in ("pee", "poop", "both") and float(visit["confidence"] or 0) < unsure_below:
        return "unsure"
    return visit["type"]
