#!/usr/bin/env bash
# Run ON THE VM once:  bash ~/catcam/deploy/setup_vm.sh America/New_York
set -euo pipefail
TZ_NAME="${1:-America/New_York}"
APP="$(cd "$(dirname "$0")/.." && pwd)"

echo "== System packages"
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip ffmpeg rsync libgl1 libglib2.0-0
sudo timedatectl set-timezone "$TZ_NAME"

echo "== Tailscale"
if ! command -v tailscale >/dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

echo "== Python packages (this takes a few minutes)"
python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install --upgrade pip
"$APP/.venv/bin/pip" install torch torchvision --index-url https://download.pytorch.org/whl/cpu
"$APP/.venv/bin/pip" install -r "$APP/catcam/requirements.txt"
mkdir -p "$APP/data" "$APP/models"

echo "== Services"
for s in catcam-detector catcam-label; do
  sed "s|__USER__|$USER|g; s|__APP__|$APP|g" "$APP/deploy/$s.service" | sudo tee /etc/systemd/system/$s.service >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable --now catcam-detector catcam-label

echo "== Nightly summary at 21:00"
( crontab -l 2>/dev/null | grep -v 'catcam.summary' || true
  echo "0 21 * * * cd $APP && .venv/bin/python -m catcam.summary --date today --cleanup >> data/summary.log 2>&1" ) | crontab -

echo
echo "Done. If you haven't yet:  sudo tailscale up --hostname catcam-vm"
echo "Watch the detector:        journalctl -u catcam-detector -f"
