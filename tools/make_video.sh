#!/bin/bash
# Assemble the demo video from frames captured by tools/unreal/record_demo.py.
#   tools/make_video.sh <first-frame-number>      -> media/marswalk_demo.mp4 (30 fps, 28 s)
set -e
cd "$(dirname "$0")/.."
SRC=Marswalk/Saved/Screenshots/MacEditor
FIRST=${1:?first ScreenShot number of the demo capture}
mkdir -p media .scratch
# Title strip (this ffmpeg has no drawtext, so render it with Pillow)
python3 - <<'EOF'
from PIL import Image, ImageDraw, ImageFont
im = Image.new("RGBA", (1600, 900), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
d.rectangle([0, 750, 1600, 900], fill=(0, 0, 0, 150))
f1 = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 46)
f2 = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 26)
d.text((40, 768), "MARSWALK  -  a hyperlocal Mars EVA planner", font=f1, fill=(255, 255, 255, 255))
d.text((40, 838), "Boxwork ridges, Mount Sharp, Gale crater  |  HiRISE DTM + ortho, THEMIS, Curiosity RAD, REMS, Navcam",
       font=f2, fill=(255, 200, 144, 255))
im.save(".scratch/title.png")
EOF
ffmpeg -y -loglevel error -framerate 30 -start_number "$FIRST" -i "$SRC/ScreenShot%05d.png" -i .scratch/title.png \
  -filter_complex "[0:v][1:v]overlay=0:0:enable='lt(t,3.5)'" -frames:v 840 \
  -c:v libx264 -pix_fmt yuv420p -crf 22 -preset slow -movflags +faststart media/marswalk_demo.mp4
ffprobe -v error -show_entries format=duration -of csv=p=0 media/marswalk_demo.mp4
