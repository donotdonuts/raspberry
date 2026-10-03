#!/usr/bin/env bash
# Mac: copy the code to the VM and restart the services (if they're installed).
set -euo pipefail
VM="${CATCAM_VM:-ubuntu@catcam-vm}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
rsync -av --exclude='__pycache__' --exclude='zone.jpg' "$DIR/catcam" "$DIR/deploy" "$VM:catcam/"
ssh "$VM" 'systemctl list-unit-files catcam-detector.service >/dev/null 2>&1 && sudo systemctl restart catcam-detector catcam-label || echo "Services not installed yet: run  bash ~/catcam/deploy/setup_vm.sh"'
