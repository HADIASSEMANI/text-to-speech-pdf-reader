#!/usr/bin/env bash
# Builds assets/app-icon.icns from assets/app-icon.png (macOS only: sips, iconutil).
# The artwork is fitted into 824 px of a 1024 px canvas, Apple's icon grid,
# so it matches the size of other Dock icons.
set -euo pipefail
cd "$(dirname "$0")/.."

src=assets/app-icon.png
out=assets/app-icon.icns
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
set="$work/app-icon.iconset"
mkdir "$set"

sips -Z 824 "$src" --out "$work/fit.png" >/dev/null
sips --padToHeightWidth 1024 1024 "$work/fit.png" --out "$work/master.png" >/dev/null

for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$work/master.png" --out "$set/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$work/master.png" --out "$set/icon_${size}x${size}@2x.png" >/dev/null
done

iconutil -c icns "$set" -o "$out"
echo "Wrote $out"
