#!/usr/bin/env bash
# 把 team/assets/*.svg 导成 1920×1080 PNG（放 team/assets/png/），供 PPT/Keynote 直接拖入。
# 用无头 Chrome 渲染 —— 所见即所得。qlmanage 会把 16:9 填充成正方形再裁歪，别用。
set -euo pipefail
cd "$(dirname "$0")/../.."
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
mkdir -p team/assets/png
for svg in team/assets/*.svg; do
  name=$(basename "$svg" .svg)
  "$CHROME" --headless --disable-gpu \
    --screenshot="team/assets/png/$name.png" \
    --window-size=1920,1080 "file://$PWD/$svg" >/dev/null 2>&1
  echo "  $name.png"
done
echo "→ team/assets/png/"
