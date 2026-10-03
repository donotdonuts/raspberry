#!/usr/bin/env bash
# Mac: download the visit log, labels and daily summaries from the VM into ./data
set -euo pipefail
VM="${CATCAM_VM:-ubuntu@catcam-vm}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$DIR/data"
rsync -av --include='visits.csv' --include='labels.csv' --include='summary/***' --exclude='*' \
  "$VM:catcam/data/" "$DIR/data/"
latest=$(ls -1 "$DIR/data/summary/"*.txt 2>/dev/null | tail -1 || true)
[ -n "$latest" ] && { echo; cat "$latest"; }
