"""Daily summary of Molly's litter visits + health flags.

    python -m catcam.summary --date today            # writes data/summary/YYYY-MM-DD.txt and prints it
    python -m catcam.summary --date 2026-10-02 --cleanup
"""
import argparse
from datetime import date, datetime, timedelta

from .common import (CLIPS, CROPS, SUMMARY, effective_type, ensure_dirs, load_config, read_labels,
                     read_visits)


def _ts(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def build_summary(day, visits, labels, cfg, now=None):
    now = now or min(datetime.now(), datetime.combine(day + timedelta(days=1), datetime.min.time()))
    ub = cfg["unsure_below"]
    toilet = []
    for v in visits:
        kind = effective_type(v, labels, ub)
        if kind in ("pee", "poop", "both", "unsure") and _ts(v["start"]) <= now:
            toilet.append((v, kind))

    def counts(d):
        kinds = [k for v, k in toilet if _ts(v["start"]).date() == d]
        return (sum(k in ("pee", "both") for k in kinds), sum(k in ("poop", "both") for k in kinds),
                sum(k == "unsure" for k in kinds), len(kinds))

    pee, poop, unsure, total = counts(day)
    today = sorted((v for v, _ in toilet if _ts(v["start"]).date() == day), key=lambda v: v["start"])
    longest = max((float(v["duration_s"]) for v in today), default=0)

    lines = [f"Molly's litter box: {day:%A %d %b %Y}", "",
             f"Pee: {pee} · Poop: {poop} · Unsure: {unsure} · Visits: {total}"]
    if today:
        lines.append(f"Longest visit: {int(longest // 60)}m{int(longest % 60):02d}s")

    prev = [day - timedelta(days=i) for i in range(1, 8)]
    first = min((_ts(v["start"]).date() for v, _ in toilet), default=day)
    prev = [d for d in prev if d >= first]
    if prev:
        avg = [sum(counts(d)[i] for d in prev) / len(prev) for i in (0, 1)]
        lines.append(f"Last {len(prev)} day avg: pee {avg[0]:.1f} · poop {avg[1]:.1f}")

    flags = []
    if toilet and now - _ts(toilet[0][0]["start"]) > timedelta(hours=48):
        poops = [_ts(v["start"]) for v, k in toilet if k in ("poop", "both")]
        if not poops or now - max(poops) > timedelta(hours=48):
            flags.append("No poop in 48 h. Keep an eye on constipation.")
    if len(prev) >= 3 and pee >= max(avg[0] * 1.5, avg[0] + 2):
        flags.append(f"Many more pee visits than usual ({pee} vs avg {avg[0]:.1f}). Possible bladder issue.")
    long_ones = [v for v in today if float(v["duration_s"]) > cfg["long_visit_flag_s"]]
    if long_ones:
        flags.append(f"{len(long_ones)} visit(s) over {cfg['long_visit_flag_s'] // 60} min. Possible straining.")
    if toilet and now - max(_ts(v["start"]) for v, _ in toilet) > timedelta(hours=24):
        flags.append("No litter box visits in 24 h.")
    if unsure:
        flags.append(f"{unsure} unsure visit(s): label them on the label page to improve accuracy.")

    lines += ["", "Flags:" if flags else "Flags: none, all looks normal."] + [f"  ⚠ {f}" for f in flags]
    if today:
        lines += ["", "Visits:"]
        for v in today:
            k = effective_type(v, labels, ub)
            mark = " ✓" if v["id"] in labels else ""
            lines.append(f"  {v['start'][11:16]}  {k:<6}{mark}  {float(v['duration_s']):.0f} s")
    return "\n".join(lines) + "\n"


def cleanup(visits, labels, keep_days):
    cutoff = datetime.now() - timedelta(days=keep_days)
    removed = 0
    for v in visits:
        if v["id"] in labels or _ts(v["start"]) > cutoff:
            continue
        for p in list(CLIPS.glob(f"{v['id']}*")) + list(CROPS.glob(f"{v['id']}_*")):
            p.unlink(missing_ok=True)
            removed += 1
    return removed


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", default="today")
    p.add_argument("--cleanup", action="store_true", help="delete old unlabelled clips")
    args = p.parse_args()
    cfg = load_config()
    ensure_dirs()
    day = date.today() if args.date == "today" else date.fromisoformat(args.date)
    visits, labels = read_visits(), read_labels()
    text = build_summary(day, visits, labels, cfg)
    (SUMMARY / f"{day.isoformat()}.txt").write_text(text)
    print(text)
    if args.cleanup:
        print(f"Cleanup: removed {cleanup(visits, labels, cfg['keep_days'])} old files")


if __name__ == "__main__":
    main()
