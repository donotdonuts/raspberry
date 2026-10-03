#!/usr/bin/env bash
# Run ON THE PI:  bash ~/pi/setup_pi.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "== Installing ffmpeg + camera tools"
sudo apt-get update
sudo apt-get install -y ffmpeg v4l-utils curl

echo "== Installing MediaMTX"
VER=$(curl -fsSL https://api.github.com/repos/bluenviron/mediamtx/releases/latest | grep -m1 '"tag_name"' | cut -d'"' -f4)
TMP=$(mktemp -d)
for arch in arm64 arm64v8; do
  URL="https://github.com/bluenviron/mediamtx/releases/download/${VER}/mediamtx_${VER}_linux_${arch}.tar.gz"
  if curl -fsSLo "$TMP/mediamtx.tar.gz" "$URL"; then break; fi
done
tar -xzf "$TMP/mediamtx.tar.gz" -C "$TMP" mediamtx
sudo install -m 755 "$TMP/mediamtx" /usr/local/bin/mediamtx
sudo install -m 755 "$DIR/catcam-stream.sh" /usr/local/bin/catcam-stream
sudo mkdir -p /etc/mediamtx
sudo cp "$DIR/mediamtx.yml" /etc/mediamtx/mediamtx.yml
sudo cp "$DIR/mediamtx.service" /etc/systemd/system/mediamtx.service
sudo systemctl daemon-reload
sudo systemctl enable --now mediamtx
sudo systemctl restart mediamtx

echo "== Installing Tailscale"
if ! command -v tailscale >/dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

echo
echo "Done. MediaMTX ${VER} is running. Check it with:  sudo systemctl status mediamtx"
echo "Next: run  sudo tailscale up  and open the link it prints to log in."
