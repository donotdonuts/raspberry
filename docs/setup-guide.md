# Molly Toilet Cam: setup guide

Do these in order. `Mac $` = Mac Terminal, `Pi $` = logged in to the Pi, `VM $` = logged in to the cloud VM.

---

## 1. Tailscale account (5 min)
Tailscale is a free private network that lets the Pi, the VM and your Mac talk to each other safely from anywhere.

1. Go to https://tailscale.com, click **Get started**, and sign in with Google.
2. Install the Tailscale app on your **Mac** (Mac App Store, search for "Tailscale"), open it and log in.
3. Optional: install it on your **phone** too, so you can open the label page anywhere.

## 2. Pi: start streaming (10 min)
```bash
Mac $ scp -r ~/Documents/raspberry/pi momo@pizero.local:
Mac $ ssh momo@pizero.local
Pi  $ bash ~/pi/setup_pi.sh
Pi  $ sudo tailscale up            # open the link it prints, log in, then come back
Pi  $ sudo systemctl status mediamtx   # should say "active (running)"; press q to exit
```
Test it from the Mac. Install VLC (https://videolan.org), then **File → Open Network** → `rtsp://pizero:8554/litter`.

If the video doesn't work, the Pi's hardware encoder may be the problem:
```bash
Pi  $ sudo nano /usr/local/bin/catcam-stream     # change ENCODER="h264_v4l2m2m" to ENCODER="libx264"
Pi  $ sudo systemctl restart mediamtx
```

## 3. Oracle Cloud free VM (20–30 min)
1. Sign up at https://www.oracle.com/cloud/free. A card is needed for identity checks, but you won't be charged.
2. Recommended: in **Billing → Upgrade and Manage Payment**, upgrade to **Pay As You Go**. Free-tier resources stay $0, and Oracle won't reclaim the VM.
3. Make an SSH key on the Mac, if you don't already have one:
   ```bash
   Mac $ ls ~/.ssh/id_ed25519.pub || ssh-keygen -t ed25519      # press Enter for all questions
   Mac $ cat ~/.ssh/id_ed25519.pub                              # copy this line
   ```
4. In the Oracle console, go to **Compute → Instances → Create instance**:
   - **Image:** Canonical **Ubuntu 24.04**
   - **Shape:** Change shape → **Ampere** → `VM.Standard.A1.Flex`, **4 OCPU, 24 GB** (free). If it says "out of capacity", try 2 OCPU / 12 GB or another availability domain.
   - **SSH keys:** "Paste public keys" → paste the line from step 3.
   - Click **Create**. Wait until it shows **Running**, then copy the **Public IP**.
5. Log in and join Tailscale:
   ```bash
   Mac $ ssh ubuntu@<PUBLIC-IP>
   VM  $ curl -fsSL https://tailscale.com/install.sh | sh
   VM  $ sudo tailscale up --hostname catcam-vm     # open the link, log in
   VM  $ ping -c 3 pizero                           # should get replies from the Pi
   VM  $ exit
   ```
   From now on you can use `ssh ubuntu@catcam-vm`, with no public IP needed.

## 4. Install the detector on the VM (10 min)
```bash
Mac $ cd ~/Documents/raspberry
Mac $ ssh ubuntu@catcam-vm 'mkdir -p catcam'
Mac $ deploy/push.sh                                         # copies the code
Mac $ ssh ubuntu@catcam-vm 'bash ~/catcam/deploy/setup_vm.sh America/New_York'
```

## 5. Mark the litter tray (2 min)
```bash
Mac $ cd ~/Documents/raspberry
Mac $ /usr/local/bin/python3 -m venv .venv-mac               # once; use a native (arm64) Python, not conda
Mac $ .venv-mac/bin/pip install -r catcam/requirements-mac.txt
Mac $ .venv-mac/bin/python -m catcam.zone_picker --push ubuntu@catcam-vm
```
Conda's OpenCV (and the x86 Anaconda pip wheel) has no FFmpeg and can't open the RTSP stream, hence the separate venv.

Click the 4 corners of the litter (inside the tray walls), then press **Enter**. Redo this any time the camera or tray moves.

## 6. Check it works
```bash
Mac $ ssh ubuntu@catcam-vm 'journalctl -u catcam-detector -f'     # live log, Ctrl+C to stop
```
- When Molly uses the tray you'll see `Cat in tray zone` → `Visit started` → `Visit …: poop/pee`.
- **Label page:** open **http://catcam-vm:8000** on the Mac or phone (Tailscale must be on).
- **Fake poop test:** drop a brown paper ball into the empty tray, hold a cat photo on your phone over the tray for about 15 s, then take it away. After about 20 s the log should say `poop`.

## Everyday use
| What | How |
|---|---|
| See today + label visits | http://catcam-vm:8000 |
| Daily summary file | written at 21:00. `catcam/pull.sh` on the Mac downloads it to `data/summary/` |
| Change settings | edit `catcam/config.yaml`, then `deploy/push.sh` |
| Tune the colour check | `python3 -m catcam.tray_check before.jpg after.jpg` on photos from `data/clips/` |
| Train v2 (after ~30 pee + 30 poop labels) | `ssh ubuntu@catcam-vm 'cd catcam && .venv/bin/python -m catcam.train'` |

## Tips for the camera
- Mount it **high, looking down at the tray at 45–60°**, so the whole litter surface is visible.
- Leave the room light on at night.
- Use a USB power supply in **PWR IN** for the Pi, not the battery.
