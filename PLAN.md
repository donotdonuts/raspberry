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
- `momo.lan` at 192.168.86.35 on the network is a **different device**, not the Pi.
- For stable power, use a USB supply in **PWR IN** rather than the PiSugar battery, especially with a webcam attached.
- The old card's Raspberry Pi Connect auth key was exposed in a chat — revoke it in the Connect account if not already done.

## Architecture
```
[Logi cam] → [Pi Zero 2 W] --RTSP over Wi-Fi--> [Mac] → cat detection + activity rules → log / alerts
```
The Pi Zero is too weak for real-time AI, so it only streams. Detection runs on the Mac.

- Pi: **MediaMTX** RTSP stream, ~720p @ 15 fps
- Mac: pretrained detector (e.g. YOLO, "cat" class) + zones + motion rules

| Activity | Detection rule | Difficulty |
|---|---|---|
| Poop / pee | Cat in litter-box zone ≥ ~30 s, mostly still, digging motion around it | Easy–medium |
| Sleep | Cat present, minimal motion ≥ 5 min (esp. in bed zone) | Easy |
| Running / play | Fast change in cat position between frames | Easy |
| Eating / drinking | Cat's head in food/water bowl zone | Easy |
| Vomiting, scratching… | Custom model trained on own labelled clips | Harder (later) |

### Constraints
- One camera = one view (litter box view is the most useful for health tracking)
- No night vision on the Logitech cam → IR camera or night light for night detection
- Keep the Pi reasonably close to the router
- Detection only runs while the Mac is on (could move to a mini PC / Pi 5 later)

## Roadmap
- [ ] **Step 1 — Camera + streaming**
  - [ ] Plug in webcam via OTG adapter
  - [ ] Verify: `lsusb` (shows Logitech), `sudo apt install -y v4l-utils fswebcam`, `v4l2-ctl --list-devices` (shows /dev/video0)
  - [ ] Test photo: `fswebcam -r 1280x720 --no-banner test.jpg`, then on Mac: `scp momo@pizero.local:test.jpg ~/Desktop/`
  - [ ] Install MediaMTX, stream RTSP, watch it on the Mac
- [ ] **Step 2 — Detection**: cat detection + zones (litter box, bed, bowls), log events like "poop 14:32, 45 s"
- [ ] **Step 3 — Reporting**: daily summary / phone alerts (e.g. "no litter box visit in 24 h")
- [ ] **Step 4 — Custom model**: record clips, label, train for harder activities

## Optional housekeeping
- Password-less SSH (lets Claude run commands on the Pi): on Mac `ssh-copy-id momo@pizero.local`
- Update the Pi: `sudo apt update && sudo apt full-upgrade -y`
- PiSugar battery tools: `curl http://cdn.pisugar.com/release/pisugar-power-manager.sh | sudo bash`
