"""Download the third-party surface and rock scans (Poly Haven, CC0) into data/assets/polyhaven.

    python3 tools/get_assets.py

Ground textures at 2k (diffuse, DirectX normal, AO/rough/metal) and rock models as glTF with 2k textures.
"""
import json
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "assets" / "polyhaven"
TEXTURES = ["moon_dusted_02", "gravelly_sand", "dry_riverbed_rock"]
ROCKS = ["moon_rock_01", "moon_rock_03", "moon_rock_04", "moon_rock_05", "moon_rock_07",
         "namaqualand_boulder_03", "namaqualand_boulder_04", "namaqualand_boulder_05",
         "namaqualand_stones_01", "namaqualand_rocks_01"]
UA = {"User-Agent": "asset-fetch/1.0"}


def fetch(url, dest):
    if dest.exists() and dest.stat().st_size:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA)) as r:
        dest.write_bytes(r.read())
    print(f"  {dest.relative_to(OUT)}  {dest.stat().st_size // 1024} KB")


def files(asset):
    with urllib.request.urlopen(urllib.request.Request(f"https://api.polyhaven.com/files/{asset}", headers=UA)) as r:
        return json.load(r)


def main():
    for a in TEXTURES:
        f = files(a)
        for m in ("Diffuse", "nor_dx", "arm"):
            fetch(f[m]["2k"]["jpg"]["url"], OUT / "textures" / f"{a}_{m}.jpg")
    for a in ROCKS:
        g = files(a)["gltf"]["2k"]["gltf"]
        fetch(g["url"], OUT / "rocks" / a / f"{a}.gltf")
        for rel, inc in g["include"].items():
            fetch(inc["url"], OUT / "rocks" / a / rel)
    print("assets in", OUT)


if __name__ == "__main__":
    main()
