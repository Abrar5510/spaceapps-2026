"""Download the Curiosity raw images used as 'what to expect' photos at each stop.

Run from the repo root:  python3 tools/get_photos.py
Images: NASA/JPL-Caltech, Mars Science Laboratory raw images (https://mars.nasa.gov/msl/multimedia/raw-images/).
"""
import csv
import io
import urllib.request
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "data" / "site" / "photos"
BASE = "https://mars.nasa.gov/msl-raw-images/proj/{vol}/redops/ods/surface/sol/{sol:05d}/opgs/edr/ncam/{id}.JPG"

# stop index, sol, image id (Navcam left, B-side computer), archive volume
PHOTOS = [
    (0, 4541, "NLB_800624472EDR_F1160414NCAM00289M_", "msl"),
    (1, 4628, "NLB_808344735EDR_F1180924NCAM00293M_", "msl"),
    (2, 4693, "NLB_814107368EDR_F1191722NCAM00309M_", "msl"),
    (3, 4718, "NLB_816331121EDR_F1200082NCAM00309M_", "msl-red-vol2"),
    (4, 4855, "NLB_828493687EDR_F1212004NCAM00284M_", "msl"),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for stop, sol, img, vol in PHOTOS:
        url = BASE.format(vol=vol, sol=sol, id=img)
        data = urllib.request.urlopen(url, timeout=60).read()
        Image.open(io.BytesIO(data)).convert("RGB").save(OUT / f"stop{stop}.jpg", quality=92)
        rows.append([stop, sol, "Navcam (left)", img, url])
        print(stop, sol, img)
    with open(OUT / "photos.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Name", "Sol", "Camera", "ImageId", "Url"])
        w.writerows(rows)


if __name__ == "__main__":
    main()
