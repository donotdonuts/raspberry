# Cat Activity Detection — Pi Zero 2 W + Logitech Webcam

Goal: stream video of the cat and automatically detect activities (poop, sleep, running, eating…).

## Hardware
- Raspberry Pi Zero 2 W (with PiSugar2 battery board)
- Logitech USB webcam — needs a **micro-USB OTG adapter**, plugged into the Pi's **USB** port (not PWR IN)
- Mac (runs the AI / detection)

## Current setup (done)
- OS: Raspberry Pi OS **Lite (64-bit)** — no desktop, command line only
- Hostname: `pizero` · user: `momo` · SSH enabled
- Login from Mac Terminal: `ssh momo@pizero.local`
- Wi-Fi: "Sweet!" (Zero 2 W only supports 2.4 GHz)

### Lessons learned
- First SD card flash was bad (Pi never finished first boot, rootfs stayed 2.5 GB). Re-flashing with Raspberry Pi Imager (with verify) fixed it.
- 192.168.86.35 turned out to be the Pi itself (`pizero.local` resolves to it).
- `fswebcam` gives a black photo unless you skip the first frames: `fswebcam -r 1280x720 --no-banner -S 30 test.jpg`.
- Run `scp` from the **Mac** prompt, not inside the Pi (`momo@pizero:~ $` means you're on the Pi; type `exit` to leave).
- For stable power, use a USB supply in **PWR IN** rather than the PiSugar battery, especially with a webcam attached.
- The old card's Raspberry Pi Connect auth key was exposed in a chat — revoke it in the Connect account if not already done.

## Architecture (updated 2026-10-02: detection moved to the cloud)
```
[Logi cam] → [Pi Zero 2 W] --Tailscale--> [Oracle free ARM VM] → YOLO + before/after colour check → visits.csv, clips
                                                               → label page http://catcam-vm:8000, daily summary 21:00
```
- Pi: MediaMTX RTSP `rtsp://pizero:8554/litter`, 640x480 @ 10 fps (files in `pi/`)
- VM: `catcam/detector.py` (visits), `catcam/tray_check.py` (poop = new dark blob, pee = new darker-yellow wet spot),
  `catcam/label_server.py` (label/fix visits), `catcam/summary.py` (daily summary + health flags), `catcam/train.py` (v2 posture model)
- Full step-by-step setup: **docs/setup-guide.md**

### Constraints
- One camera = one view (litter box view is the most useful for health tracking)
- No night vision on the Logitech cam → IR camera or night light for night detection
- Keep the Pi reasonably close to the router
- Detection runs 24/7 on the Oracle VM; the Mac is only needed for the zone picker (the label page also works on the phone)

## Roadmap
- [ ] **Step 1 — Camera + streaming**
  - [x] Plug in webcam via OTG adapter
  - [x] Verify with `lsusb` / `v4l2-ctl --list-devices`
  - [x] Test photo works (needs `-S 30`)
  - [ ] Pi: run `pi/setup_pi.sh` + `sudo tailscale up`, watch stream in VLC (guide §1–2)
- [ ] **Step 2 — Toilet cam on the cloud VM** (code written 2026-10-02, tested with simulated data)
  - [ ] Oracle VM + Tailscale (guide §3)
  - [ ] Install detector: `deploy/push.sh` + `deploy/setup_vm.sh` (guide §4)
  - [ ] Mark tray: `zone_picker.py` (guide §5)
  - [ ] Fake-poop test + tune `config.yaml` thresholds on real photos (guide §6)
- [ ] **Step 3 — Daily use**: label visits on the label page for ~2 weeks; daily summary at 21:00
- [ ] **Step 4 — v2 model**: after ~30 pee + 30 poop labels run `catcam.train`; compare against the colour rules
- [ ] Later: phone alerts for health flags, other activities (sleep/eating) with a second camera

## Optional housekeeping
- Password-less SSH (lets Claude run commands on the Pi): on Mac `ssh-copy-id momo@pizero.local`
- Update the Pi: `sudo apt update && sudo apt full-upgrade -y`
- PiSugar battery tools: `curl http://cdn.pisugar.com/release/pisugar-power-manager.sh | sudo bash`
