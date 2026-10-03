"""Labelling page: watch each visit and fix the guess (Pee / Poop / Both / Nothing).

Run:  python -m catcam.label_server     then open http://catcam-vm:8000 (Tailscale only)
"""
import os
import re
import subprocess
from datetime import date, datetime

from flask import Flask, abort, redirect, render_template_string, request, send_from_directory

from .common import (CLIPS, CROPS, DATA, LABEL_FIELDS, LABELS, LABELS_CSV, append_row, effective_type,
                     ensure_dirs, load_config, read_labels, read_visits)
from .summary import build_summary

app = Flask(__name__)
ID_RE = re.compile(r"^\d{8}-\d{6}$")

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Molly cam</title>
<style>
:root{--bg:#fafaf7;--fg:#222;--muted:#777;--card:#fff;--line:#e4e2dc;--accent:#c47a12}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--fg:#eee;--muted:#999;--card:#222;--line:#333}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,system-ui,sans-serif}
main{max-width:760px;margin:auto;padding:16px}
a{color:var(--accent)} pre{white-space:pre-wrap;background:var(--card);border:1px solid var(--line);padding:12px;border-radius:8px}
table{width:100%;border-collapse:collapse} td{padding:8px 4px;border-bottom:1px solid var(--line)}
.tag{padding:2px 8px;border-radius:10px;font-size:13px;background:var(--line)}
.poop{background:#8b5a2b;color:#fff}.pee{background:#e6c229;color:#222}.both{background:#b5651d;color:#fff}.unsure{background:#999;color:#fff}
img,video{width:100%;border-radius:8px;margin:6px 0} .crops{display:flex;gap:6px}.crops img{width:32%}
.btns{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0}
button{font-size:18px;padding:14px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--fg)}
.muted{color:var(--muted)}
</style></head><body><main>{{ body|safe }}</main></body></html>"""


def tag(kind):
    return f'<span class="tag {kind}">{kind}</span>'


def toilet_visits():
    return [v for v in read_visits() if v["type"] != "sniff"]


@app.route("/")
def index():
    cfg, labels = load_config(), read_labels()
    visits = toilet_visits()
    todo = [v for v in visits if v["id"] not in labels and effective_type(v, labels, cfg["unsure_below"]) == "unsure"]
    rows = []
    for v in reversed(visits[-150:]):
        k = effective_type(v, labels, cfg["unsure_below"])
        done = " ✓" if v["id"] in labels else ""
        rows.append(f'<tr><td><a href="/v/{v["id"]}">{v["start"][5:16]}</a></td><td>{tag(k)}{done}</td>'
                    f'<td class="muted">{float(v["duration_s"]):.0f} s · {float(v["confidence"] or 0):.0%}</td></tr>')
    body = (f"<h2>🐱 Molly cam</h2><pre>{build_summary(date.today(), read_visits(), labels, cfg)}</pre>"
            + (f'<p><b>{len(todo)} unsure visit(s).</b> <a href="/v/{todo[0]["id"]}">Start labelling →</a></p>' if todo else "")
            + "<h3>Visits</h3><table>" + "".join(rows) + "</table>"
            + ("" if rows else '<p class="muted">No visits yet.</p>'))
    return render_template_string(PAGE, body=body)


@app.route("/v/<vid>")
def visit(vid):
    if not ID_RE.match(vid):
        abort(404)
    cfg, labels = load_config(), read_labels()
    v = next((x for x in read_visits() if x["id"] == vid), None)
    if not v:
        abort(404)
    k = effective_type(v, labels, cfg["unsure_below"])
    media = ""
    if (CLIPS / f"{vid}.mp4").exists():
        media += f'<video controls playsinline preload="metadata" src="/media/clips/{vid}.mp4"></video>'
    if (CLIPS / f"{vid}_tray.jpg").exists():
        media += f'<p class="muted">Before | after: red = dark blob (poop), blue = wet spot (pee)</p><img src="/media/clips/{vid}_tray.jpg">'
    crops = "".join(f'<img src="/media/crops/{vid}_{i}.jpg">' for i in (1, 2, 3) if (CROPS / f"{vid}_{i}.jpg").exists())
    current = f"Your label: <b>{labels[vid]}</b>" if vid in labels else f"Guess: {tag(k)} {float(v['confidence'] or 0):.0%} ({v['source']})"
    buttons = "".join(f'<button name="label" value="{lab}">{lab.title()}</button>' for lab in LABELS)
    body = (f'<p><a href="/">← all visits</a></p><h2>{v["start"]}</h2>'
            f'<p>{current} · {float(v["duration_s"]):.0f} s · poop px {v["poop_px"]} · wet px {v["wet_px"]}</p>'
            f'{media}<div class="crops">{crops}</div>'
            f'<form method="post" action="/v/{vid}/label"><div class="btns">{buttons}</div></form>')
    return render_template_string(PAGE, body=body)


@app.post("/v/<vid>/label")
def label(vid):
    lab = request.form.get("label")
    if not ID_RE.match(vid) or lab not in LABELS:
        abort(400)
    append_row(LABELS_CSV, LABEL_FIELDS, {"id": vid, "label": lab,
                                          "labeled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    cfg, labels = load_config(), read_labels()
    nxt = next((v for v in reversed(toilet_visits()) if v["id"] not in labels
                and effective_type(v, labels, cfg["unsure_below"]) == "unsure"), None)
    return redirect(f"/v/{nxt['id']}" if nxt else "/")


@app.route("/media/<path:p>")
def media(p):
    return send_from_directory(DATA, p)


def tailscale_ip():
    """Only listen on the Tailscale address, so the page is never on the public internet."""
    try:
        return subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True,
                              timeout=5).stdout.split()[0]
    except Exception:
        raise SystemExit("Tailscale isn't up yet (systemd will retry). Set CATCAM_HOST=127.0.0.1 to test locally.")


if __name__ == "__main__":
    ensure_dirs()
    app.run(host=os.environ.get("CATCAM_HOST") or tailscale_ip(), port=8000)
