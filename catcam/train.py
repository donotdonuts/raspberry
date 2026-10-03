"""v2: train a pee-vs-poop posture classifier on your labelled visits.

    python -m catcam.train            # needs >= 30 labelled pee and 30 poop visits
    python -m catcam.train --force    # train anyway with fewer

The detector picks up the new models/posture.pt by itself, no restart needed.
"""
import argparse
import hashlib
import json
import shutil

from ultralytics import YOLO

from .common import CROPS, DATA, MODELS, POSTURE_MODEL, ensure_dirs, read_labels, read_visits

CLASS_OF = {"pee": "pee", "poop": "poop", "both": "poop"}  # "both" looks like a poop squat


def is_val(vid):
    return int(hashlib.md5(vid.encode()).hexdigest(), 16) % 5 == 0   # stable 20% hold-out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true")
    p.add_argument("--min", type=int, default=30)
    p.add_argument("--epochs", type=int, default=30)
    args = p.parse_args()
    ensure_dirs()

    labels = {k: CLASS_OF[v] for k, v in read_labels().items() if v in CLASS_OF}
    visits = {v["id"]: v for v in read_visits()}
    have = {c: [i for i, l in labels.items() if l == c and (CROPS / f"{i}_1.jpg").exists()] for c in ("pee", "poop")}
    print(f"Labelled visits with photos: pee {len(have['pee'])}, poop {len(have['poop'])}")
    if min(map(len, have.values())) < args.min and not args.force:
        raise SystemExit(f"Need at least {args.min} of each. Keep labelling (or use --force).")

    ds = DATA / "train_set"
    shutil.rmtree(ds, ignore_errors=True)
    for cls, ids in have.items():
        for vid in ids:
            split = "val" if is_val(vid) else "train"
            (ds / split / cls).mkdir(parents=True, exist_ok=True)
            for crop in CROPS.glob(f"{vid}_*.jpg"):
                shutil.copy(crop, ds / split / cls / crop.name)
    for split in ("train", "val"):
        for cls in ("pee", "poop"):
            (ds / split / cls).mkdir(parents=True, exist_ok=True)

    model = YOLO("yolo11n-cls.pt")
    model.train(data=str(ds), epochs=args.epochs, imgsz=224, device="cpu",
                project=str(MODELS / "runs"), name="posture", exist_ok=True, verbose=False)
    best = MODELS / "runs" / "posture" / "weights" / "best.pt"
    top1 = float(YOLO(str(best)).val(data=str(ds), imgsz=224, device="cpu", verbose=False).top1)

    # How did the v1 colour rules do on the same held-out visits?
    val_ids = [i for ids in have.values() for i in ids if is_val(i)]
    rules_ok = [CLASS_OF.get(visits[i]["rules_type"]) == labels[i] for i in val_ids if i in visits]
    rules_acc = sum(rules_ok) / len(rules_ok) if rules_ok else float("nan")

    print(f"\nPosture model accuracy (held-out photos): {top1:.0%}")
    print(f"Colour rules accuracy (held-out visits):  {rules_acc:.0%}  ({len(rules_ok)} visits)")
    shutil.copy(best, POSTURE_MODEL)
    (MODELS / "posture_metrics.json").write_text(json.dumps(
        {"model_top1": top1, "rules_acc": rules_acc, "pee": len(have["pee"]), "poop": len(have["poop"])}, indent=2))
    print(f"Saved {POSTURE_MODEL}. The detector will start using it on the next visit.")


if __name__ == "__main__":
    main()
