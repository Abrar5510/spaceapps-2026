"""Crop NASA rasters to the Marswalk site box and bake the layers Unreal and the route planner use.

Run from the repo root:  python3 tools/prep_site.py
Needs GDAL command-line tools (gdalwarp) plus numpy, scipy and Pillow.
Raw files live in data/raw/ (git-ignored); see DATA.md for where each one comes from.
Outputs go to data/site/.
"""
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "site"

DTM = RAW / "DTEEC_019698_1750_019988_1750_U01.IMG"
ORTHO = RAW / "ESP_019698_1750_RED_A_01_ORTHO.JP2"
THERMAL = RAW / "themis_ti_gale_crop.tif"

# Site box: boxwork ridges crossed by Curiosity, sols ~4570-4930 (2025-26), Mount Sharp, Gale crater.
CENTER_LON, CENTER_LAT = 137.3815, -4.8080
N = 2017                 # heightmap samples per side (valid Landscape size), 1 m apart
ORTHO_PX = 8192          # ~25 cm per pixel over the same box
LAYER_PX = 2048          # colour layer textures for the Unreal layer material

R_MARS = 3396190.0       # sphere used by the HiRISE DTM and THEMIS products
LON0 = 137.38            # DTM's equirectangular centre longitude
SRS = f"+proj=eqc +lat_ts=0 +lat_0=0 +lon_0={LON0} +x_0=0 +y_0=0 +R={R_MARS} +units=m +no_defs"


def lonlat_to_xy(lon, lat):
    return R_MARS * math.radians(lon - LON0), R_MARS * math.radians(lat)


def xy_to_lonlat(x, y):
    return LON0 + math.degrees(x / R_MARS), math.degrees(y / R_MARS)


cx, cy = lonlat_to_xy(CENTER_LON, CENTER_LAT)
# Pixel-is-area box of N x N one-metre cells; cell centres are the Landscape vertices.
X0, Y1 = round(cx - N / 2), round(cy + N / 2)
X1, Y0 = X0 + N, Y1 - N


def warp(src, dst, size, resample, nodata_out=-32768):
    """Warp src onto the site box at size x size pixels; return float32 array (row 0 = north)."""
    dst = Path(dst)
    cmd = ["gdalwarp", "-q", "-overwrite", "-t_srs", SRS, "-te", str(X0), str(Y0), str(X1), str(Y1),
           "-ts", str(size), str(size), "-r", resample, "-ot", "Float32", "-of", "ENVI",
           "-dstnodata", str(nodata_out), "-wo", "NUM_THREADS=ALL_CPUS", str(src), str(dst)]
    subprocess.run(cmd, check=True)
    a = np.fromfile(dst, dtype="<f4").reshape(size, size)
    for p in (dst, dst.with_suffix(".hdr"), Path(str(dst) + ".aux.xml")):
        p.unlink(missing_ok=True)
    return np.where(a == nodata_out, np.nan, a)


def ramp(t, stops):
    """Map t in [0,1] through colour stops [(pos, (r,g,b)), ...] -> uint8 RGB."""
    t = np.clip(np.nan_to_num(t), 0, 1)
    pos = np.array([s[0] for s in stops])
    cols = np.array([s[1] for s in stops], dtype=float)
    rgb = np.stack([np.interp(t, pos, cols[:, k]) for k in range(3)], axis=-1)
    return rgb.astype(np.uint8)


def save_layer(rgb, name):
    Image.fromarray(rgb).resize((LAYER_PX, LAYER_PX), Image.BILINEAR).save(OUT / name)


def detail_normal(size=1024, seed=7):
    """Tileable grit/pebble normal map (spectral noise, wraps at the edges) for close-up ground detail."""
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(size)
    k = np.hypot(*np.meshgrid(f, f))
    k[0, 0] = 1
    h = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((size, size))) / k ** 1.6))
    pebbles = np.zeros((size, size))
    for _ in range(900):  # small rounded clasts, wrapped so the tile repeats cleanly
        r = rng.uniform(2, 10)
        y, x = rng.uniform(0, size, 2)
        a, e = rng.uniform(0, np.pi), rng.uniform(0.4, 1.0)   # random orientation and elongation
        yy, xx = np.ogrid[:size, :size]
        dy = (yy - y + size / 2) % size - size / 2
        dx = (xx - x + size / 2) % size - size / 2
        u, v = dx * np.cos(a) + dy * np.sin(a), (-dx * np.sin(a) + dy * np.cos(a)) / e
        pebbles = np.maximum(pebbles, np.clip(1 - (u ** 2 + v ** 2) / r ** 2, 0, 1) ** 0.7 * r * 0.12)
    h = (h - h.mean()) / h.std() * 3.0 + pebbles + 0.4 * h * pebbles / (pebbles.max() + 1e-6)
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / 2  # wrap-aware gradients keep the tile seamless
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) / 2
    n = np.dstack([-gx, -gy, np.full_like(h, 2.0)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8)).save(OUT / "detail_normal.png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "_tmp.bin"

    print("DTM ...")
    z = warp(DTM, tmp, N, "bilinear")
    if np.isnan(z).any():
        sys.exit(f"DTM has {int(np.isnan(z).sum())} empty cells inside the box; move the box.")
    zmin, zmax = float(z.min()), float(z.max())
    zscale = (zmax - zmin) / 512 * 100  # Landscape Z scale (cm) for a full 0..65535 range
    h16 = np.round((z - zmin) / (zmax - zmin) * 65535).astype(np.uint16)
    Image.fromarray(h16).save(OUT / "heightmap.png")

    print("ortho ...")
    o = warp(ORTHO, tmp, ORTHO_PX, "cubic", nodata_out=0)
    if np.isnan(o).mean() > 0.001:
        sys.exit("orthoimage does not cover the box")
    o = np.nan_to_num(o, nan=np.nanmedian(o))
    lo, hi = np.percentile(o, [0.5, 99.5])
    g = np.clip((o - lo) / (hi - lo), 0, 1)
    # HiRISE RED is greyscale; tint toward Mastcam-like Mount Sharp tones so the ground reads as Mars.
    tint_dark, tint_light = np.array([62, 38, 24]), np.array([226, 178, 132])
    rgb = (tint_dark + g[..., None] * (tint_light - tint_dark)).astype(np.uint8)
    Image.fromarray(rgb).save(OUT / "ortho.png")

    print("slope, roughness ...")
    # HiRISE stereo resolves ~3 m, so take slope over a ~3 m baseline; raw 1 m differences are mostly noise.
    gy, gx = np.gradient(ndimage.gaussian_filter(z, 1.0), 1.0)
    slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)
    # Height spread in a 3 m window after removing the local plane: rocks, ledges, rubble.
    resid = z - ndimage.uniform_filter(z, 3, mode="nearest")
    rough = ndimage.maximum_filter(resid, 3) - ndimage.minimum_filter(resid, 3)
    Image.fromarray(np.clip(slope * 4, 0, 255).astype(np.uint8)).save(OUT / "slope.png")      # 0.25 deg/step
    Image.fromarray(np.clip(rough * 100, 0, 255).astype(np.uint8)).save(OUT / "rough.png")    # 1 cm/step

    print("thermal ...")
    ti = warp(THERMAL, tmp, N, "cubicspline")
    ti = np.where(np.isnan(ti), np.nanmedian(ti), ti).astype(np.float32)
    Image.fromarray(np.clip((ti - 150) / 2, 0, 255).astype(np.uint8)).save(OUT / "thermal.png")  # TI = 150 + 2*v

    # Colour layers for the Unreal layer material.
    save_layer(ramp(slope / 30, [(0, (40, 140, 60)), (0.33, (230, 220, 60)), (0.66, (240, 120, 30)), (1, (200, 20, 20))]),
               "layer_slope.png")
    save_layer(ramp((ti - 200) / 400, [(0, (240, 210, 90)), (0.4, (200, 120, 60)), (1, (60, 40, 120))]),
               "layer_thermal.png")

    detail_normal()
    np.savez_compressed(OUT / "grids.npz", z=z.astype(np.float32), slope=slope, rough=rough.astype(np.float32), ti=ti)

    corners = {k: xy_to_lonlat(x, y) for k, (x, y) in
               {"nw": (X0, Y1), "ne": (X1, Y1), "sw": (X0, Y0), "se": (X1, Y0)}.items()}
    site = {
        "name": "Boxwork ridges, Mount Sharp, Gale crater",
        "srs": SRS, "box_m": [X0, Y0, X1, Y1], "samples": N, "metres_per_sample": 1.0,
        "corners_lonlat": corners,
        "elev_min_m": zmin, "elev_max_m": zmax,
        "landscape": {"scale_xy_cm": 100.0, "scale_z_cm": zscale, "actor_z_cm": 0.0,
                      "note": "world z (m) = elevation - (min+max)/2; UE X = east (col), UE Y = south (row)"},
        "thermal_inertia_range": [float(ti.min()), float(ti.max())],
        "slope_p99_deg": float(np.percentile(slope, 99)),
        "rough_p99_m": float(np.percentile(rough, 99)),
    }
    (OUT / "site.json").write_text(json.dumps(site, indent=2))
    print(json.dumps(site, indent=2))


if __name__ == "__main__":
    main()
