"""Build the Marswalk site: reproject NASA rasters, derive slope/hazards, plan the walking route,
compute sun + radiation, and write web layers, site.json and Unreal inputs.

Run: .venv/bin/python -I tools/build_site.py   (needs GDAL CLI on PATH and data/raw/* downloaded)
"""
import json, math, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.graph import route_through_array

sys.path.insert(0, str(Path(__file__).parent))
from mars24 import sun

ROOT = Path(__file__).resolve().parents[1]
RAW, WORK = ROOT / "data/raw", ROOT / "data/work"
WEB = ROOT / "web/data"
UE_IN = ROOT / "data/ue"
for d in (WORK, WEB / "layers", UE_IN):
    d.mkdir(parents=True, exist_ok=True)

# Site: 2048 m square centred on Curiosity's 2025 boxwork traverse, Gale crater
LAT0, LON0 = -4.8077, 137.3818
HALF = 1024
R_MARS = 3396190.0
SRS = f"+proj=eqc +lat_ts={LAT0} +lat_0={LAT0} +lon_0={LON0} +R={R_MARS} +units=m +no_defs"
K = math.cos(math.radians(LAT0))


def ll_to_xy(lat, lon):
    return math.radians(lon - LON0) * R_MARS * K, math.radians(lat - LAT0) * R_MARS


def xy_to_ll(x, y):
    return LAT0 + math.degrees(y / R_MARS), LON0 + math.degrees(x / (R_MARS * K))


def warp(src, dst, res, resample, half=HALF, extra=()):
    if Path(dst).exists():
        return
    subprocess.run(["gdalwarp", "-q", "-overwrite", "-t_srs", SRS, "-te", str(-half), str(-half),
                    str(half), str(half), "-tr", str(res), str(res), "-r", resample, *extra,
                    "-of", "GTiff", str(src), str(dst)], check=True)


def read_float(tif):
    """Read a single-band GTiff via an ENVI raw copy (no GDAL python bindings needed)."""
    raw = Path(str(tif) + ".f32")
    if not raw.exists():
        subprocess.run(["gdal_translate", "-q", "-of", "ENVI", "-ot", "Float32", str(tif), str(raw)], check=True)
    hdr = Path(str(raw) + ".hdr") if Path(str(raw) + ".hdr").exists() else raw.with_suffix(".hdr")
    h = {k.strip(): v.strip() for k, v in (l.split("=", 1) for l in hdr.read_text().splitlines() if "=" in l)}
    a = np.fromfile(raw, dtype="<f4").reshape(int(h["lines"]), int(h["samples"]))
    return a


# ---------------------------------------------------------------- rasters
hi = RAW / "hirise"
DTM_SRC = hi / "DTEEC_019698_1750_019988_1750_U01.IMG"
ORTHO_SRC = hi / "ESP_019698_1750_RED_A_01_ORTHO.JP2"
# DTM: pixel centres on whole metres -> 2049 x 2049 vertices
warp(DTM_SRC, WORK / "dtm_1m.tif", 1, "bilinear", half=HALF + 0.5)
warp(ORTHO_SRC, WORK / "ortho_025.tif", 0.25, "cubic", extra=("-wm", "2048"))

dem = read_float(WORK / "dtm_1m.tif").astype(np.float64)
assert dem.shape == (2049, 2049) and np.isfinite(dem).all() and dem.min() > -9000, "DTM gap in site"
ortho = np.asarray(Image.open(WORK / "ortho_025.tif"))
assert ortho.shape == (8192, 8192)

# ---------------------------------------------------------------- derived terrain layers
# slope over a ~3 m baseline: HiRISE DTM noise (~0.2 m) makes 1 m slopes meaningless for walking
gy, gx = np.gradient(ndimage.gaussian_filter(dem, 1.5), 1.0)   # rows run north->south
slope = np.degrees(np.arctan(np.hypot(gx, gy)))
detr = dem - ndimage.gaussian_filter(dem, 3)
rough = np.sqrt(ndimage.uniform_filter(detr ** 2, 5))   # m, local relief (rocks / ledges)
tpi = dem - ndimage.uniform_filter(dem, 21)              # + ridge, - hollow (21 m window)
SLOPE_MAX, ROUGH_MAX = 20.0, 0.50
# ponytail: obstacle = DTM slope/roughness at 1 m; boulders < ~1 m are below DTM resolution
obstacle = (slope > SLOPE_MAX) | (rough > ROUGH_MAX)
obstacle = ndimage.binary_dilation(obstacle, iterations=2)  # 2 m clearance for a suited walker
lab, _ = ndimage.label(~obstacle)
obstacle |= lab != np.argmax(np.bincount(lab[lab > 0].ravel(), minlength=lab.max() + 1))  # unreachable pockets


def walk_kmh(slope_deg, signed_grade=None):
    """Tobler hiking function x0.5 for a suited astronaut carrying gear."""
    g = np.tan(np.radians(slope_deg)) if signed_grade is None else signed_grade
    return 0.5 * 6.0 * np.exp(-3.5 * np.abs(g + 0.05))


# ---------------------------------------------------------------- stops
wps = json.load(open(RAW / "msl/MSL_waypoints.json"))["features"]


def rover_at(sol):
    best = min(wps, key=lambda f: abs(f["properties"]["sol"] - sol))["properties"]
    return best


def to_px(x, y):
    return int(round(HALF - y)), int(round(x + HALF))


def to_xy(r, c):
    return c - HALF, HALF - r


def pick_cell(r, c, prefer=None, rad=25):
    """Walkable cell within rad m: the highest ('ridge'), lowest ('hollow') or nearest one."""
    best = None
    for dr in range(-rad, rad + 1):
        for dc in range(-rad, rad + 1):
            rr, cc = r + dr, c + dc
            if obstacle[rr, cc] or dr * dr + dc * dc > rad * rad:
                continue
            score = {"ridge": -tpi[rr, cc], "hollow": tpi[rr, cc]}.get(prefer, (dr * dr + dc * dc) / 1e4)
            if best is None or score < best[0]:
                best = (score, rr, cc)
    assert best, "no walkable cell near stop"
    return best[1], best[2]


track = [(f["properties"]["sol"], *ll_to_xy(f["properties"]["lat"], f["properties"]["lon"]))
         for f in wps]
track = [(s, x, y) for s, x, y in track if abs(x) < HALF and abs(y) < HALF]

STOP_DEFS = [   # (rover sol, preferred relief within 25 m, name, why)
    (4603, "ridge", "Ridge crest", "Curiosity reached the top of the first boxwork ridge here (sols 4602-4603). "
           "Ridges are where the rover found clay minerals: sample the ridge cap."),
    (4667, "hollow", "Boxwork hollow", "Curiosity parked here for weeks in mid-2025. Hollows between ridges hold "
           "carbonate minerals, a record of groundwater chemistry: sample the hollow floor."),
    (4837, None, "South network", "Curiosity's exit from the dense ridge network. Image the ridge walls in "
           "cross-section to compare cementation with the ridge cap."),
]
stops = []
for sol, prefer, name, why in STOP_DEFS:
    p = rover_at(sol)
    r, c = pick_cell(*to_px(*ll_to_xy(p["lat"], p["lon"])), prefer)
    stops.append({"id": f"S{len(stops) + 1}", "name": name, "why": why, "rover_sol": p["sol"], "rc": (r, c)})

# Habitat: flattest walkable 40 m patch 300-700 m from the first stop, north of the ridges
r1, c1 = stops[0]["rc"]
smean = ndimage.uniform_filter(slope, 41) + 50 * ndimage.uniform_filter(obstacle.astype(float), 41)
rr, cc = np.mgrid[0:2049, 0:2049]
dist1 = np.hypot(rr - r1, cc - c1)
cand = np.where((dist1 > 300) & (dist1 < 700) & (rr < r1) & (rr > 60) & (cc > 60) & (cc < 1988), smean, np.inf)
hr, hc = np.unravel_index(np.argmin(cand), cand.shape)
hab = {"id": "H", "name": "Habitat airlock", "why": "Start and end of the EVA. Flattest 40 m patch near the "
       "ridges (mean slope {:.1f} deg).".format(ndimage.uniform_filter(slope, 41)[hr, hc]), "rc": (int(hr), int(hc))}

# ---------------------------------------------------------------- route (least time, obstacles blocked)
cost = 1.0 / walk_kmh(slope)
cost[obstacle] = 1e4
legs = [hab] + stops + [hab]
path = []
for a, b in zip(legs, legs[1:]):
    p, _ = route_through_array(cost, a["rc"], b["rc"], fully_connected=True, geometric=True)
    path += p if not path else p[1:]
path = np.array(path)
assert not obstacle[path[:, 0], path[:, 1]].any(), "route crosses an obstacle"


def simplify(pts, tol):
    """Douglas-Peucker on (row, col)."""
    if len(pts) < 3:
        return pts
    a, b = pts[0].astype(float), pts[-1].astype(float)
    v, w = b - a, pts - a
    d = np.abs(v[0] * w[:, 1] - v[1] * w[:, 0]) / (np.linalg.norm(v) + 1e-9)
    i = int(np.argmax(d))
    if d[i] > tol:
        return np.vstack([simplify(pts[:i + 1], tol)[:-1], simplify(pts[i:], tol)])
    return np.vstack([pts[0], pts[-1]])


# keep stop vertices: simplify each leg separately
leg_idx = [0]
for s in legs[1:]:
    leg_idx.append(next(i for i in range(leg_idx[-1] + 1, len(path)) if tuple(path[i]) == tuple(s["rc"])))
spath = np.vstack([simplify(path[i:j + 1], 0.7)[:-1] for i, j in zip(leg_idx, leg_idx[1:])] + [path[-1:]])

# timing along the full-resolution path, direction-aware Tobler
z = dem[path[:, 0], path[:, 1]]
dxy = np.hypot(*np.diff(path, axis=0).T)
dz = np.diff(z)
grade = dz / dxy
hours = np.concatenate([[0], np.cumsum(dxy / 1000 / walk_kmh(None, grade))])
metres = np.concatenate([[0], np.cumsum(np.hypot(dxy, dz))])
STOP_MIN = 30  # minutes of science work at each stop

# ---------------------------------------------------------------- EVA timing: sun, radiation
lat_s, lon_s = xy_to_ll(*to_xy(hr, hc))
EVA_DATE = datetime(2026, 11, 20, tzinfo=timezone.utc)   # planning sol (first sol starting after this UTC date)
t = EVA_DATE
while not (9.0 <= sun(t, lat_s, lon_s)["ltst"] < 9.02):   # EVA starts 09:00 local true solar time
    t += timedelta(seconds=60)
eva_start = t
total_h = hours[-1] + STOP_MIN * len(stops) / 60
RAD_MSV_DAY, RAD_MGY_DAY = 0.64, 0.21   # Curiosity RAD, Gale surface average (Hassler et al. 2014)
sun_track = []
for k in range(0, int(total_h * 60) + 31, 15):
    s = sun(eva_start + timedelta(minutes=k * 1.0274912517), lat_s, lon_s)   # sol minutes
    sun_track.append({"t_min": k, "ltst": round(s["ltst"], 3), "el": round(s["elevation"], 2), "az": round(s["azimuth"], 2)})
s0 = sun(eva_start, lat_s, lon_s)

# ---------------------------------------------------------------- other layers (CRISM, THEMIS)
def warp_rgb(src, name, res):
    dst = WORK / f"{name}.tif"
    warp(src, dst, res, "near")
    png = dst.with_suffix(".png")
    if not png.exists():
        subprocess.run(["gdal_translate", "-q", "-of", "PNG", str(dst), str(png)], check=True)
    rgb = np.asarray(Image.open(png).convert("RGB"))
    # browse products are 0 where the parameter is weak: show strength as opacity
    alpha = np.clip((rgb.max(-1).astype(int) - 20) * 3, 0, 255).astype(np.uint8)
    return np.dstack([rgb, alpha])


# Viviano-Beck et al. (2014) CRISM browse products: R/G/B channel meanings
crism = {}
for key, label in (("phy", "Clays: R Fe/Mg-clay (D2300), G Al-clay (D2200), B water (BD1900)"),
                   ("car", "Carbonates: R Mg-carbonate (D2300), G carbonate (BD2500), B water (BD1900)"),
                   ("hyd", "Hydrated: R polyhydrated sulfate (SINDEX2), G monohydrated sulfate (BD2100), B water"),
                   ("maf", "Mafic: R olivine, G low-Ca pyroxene, B high-Ca pyroxene")):
    a = warp_rgb(RAW / f"crism/frt000058a3_07_br{key}j_mtr3.lbl", f"crism_{key}", 4)
    crism[key] = (a, label)

th_dir = RAW / "themis"
tiles = sorted(th_dir.glob("n_9_*.png"))
rows = sorted({int(p.stem.split("_")[2]) for p in tiles}); cols = sorted({int(p.stem.split("_")[3]) for p in tiles})
mos = np.zeros((256 * len(rows), 256 * len(cols)), np.uint8)
for p in tiles:
    _, _, r, c = p.stem.split("_")
    mos[(int(r) - rows[0]) * 256:(int(r) - rows[0] + 1) * 256, (int(c) - cols[0]) * 256:(int(c) - cols[0] + 1) * 256] = \
        np.asarray(Image.open(p).convert("L"))
Image.fromarray(mos).save(WORK / "themis_mos.png")
deg = 360 / (2 ** 10 * 256)
ulx, uly = -180 + cols[0] * 256 * deg, 90 - rows[0] * 256 * deg
if not (WORK / "themis_geo.tif").exists():
    subprocess.run(["gdal_translate", "-q", "-a_srs", f"+proj=longlat +R={R_MARS} +no_defs", "-a_ullr", str(ulx), str(uly),
                    str(ulx + mos.shape[1] * deg), str(uly - mos.shape[0] * deg), str(WORK / "themis_mos.png"),
                    str(WORK / "themis_geo.tif")], check=True)
warp(WORK / "themis_geo.tif", WORK / "themis.tif", 8, "bilinear")
themis = np.asarray(Image.open(WORK / "themis.tif").convert("L")).astype(float)

# ---------------------------------------------------------------- REMS weather (Curiosity, at this site)
import csv, collections
REMS = RAW / "rems/RME_811756626RMD46670000000_______P1.TAB"   # MODRDR, sol 4667
acc = collections.defaultdict(lambda: collections.defaultdict(list))
for r in csv.reader(open(REMS), skipinitialspace=True):
    h = int(r[2].split()[1][:2])
    for name, i in (("ground_k", 7), ("air_k", 15), ("pressure_pa", 37), ("uv_wm2", 20)):
        v = float(r[i])
        if v > -900:
            acc[h][name].append(v)
rems = [{"ltst_h": h, **{k: round(sum(v) / len(v), 1) for k, v in acc[h].items()}} for h in sorted(acc)]

# ---------------------------------------------------------------- web layers (2048 px = 1 m/px)
def ramp(v, lo, hi, stops_rgb):
    t = np.clip((v - lo) / (hi - lo), 0, 1)
    xs = np.linspace(0, 1, len(stops_rgb))
    return np.stack([np.interp(t, xs, [s[i] for s in stops_rgb]) for i in range(3)], -1).astype(np.uint8)


def save(arr, name, size=2048):
    im = Image.fromarray(arr)
    if im.size[0] != size:
        im = im.resize((size, size), Image.BILINEAR)
    (im.convert("RGB").save(WEB / "layers" / f"{name}.jpg", quality=86) if im.mode == "RGB"
     else im.save(WEB / "layers" / f"{name}.png", optimize=True))


opt2k = np.asarray(Image.fromarray(ortho).resize((2048, 2048), Image.BOX))
save(np.stack([opt2k] * 3, -1), "optical")
light = np.clip(ndimage.convolve(dem, [[-1, 0, 1]] * 3) * -0.6 + ndimage.convolve(dem, [[1, 1, 1], [0, 0, 0], [-1, -1, -1]]) * -0.6, -1, 1)
shade = ((light + 1) * 0.35 + 0.3)[:-1, :-1, None]
save((ramp(dem[:-1, :-1], np.percentile(dem, 1), np.percentile(dem, 99),
           [(40, 40, 120), (40, 140, 160), (120, 190, 90), (230, 200, 80), (200, 80, 50)]) * shade).astype(np.uint8), "elevation")
save(ramp(slope[:-1, :-1], 0, 30, [(30, 120, 60), (230, 210, 60), (220, 90, 30), (150, 20, 20)]), "slope")
hz = np.zeros((2048, 2048, 4), np.uint8)
o = obstacle[:-1, :-1]; steep = (slope > SLOPE_MAX)[:-1, :-1]; rocky = (rough > ROUGH_MAX)[:-1, :-1]
hz[o] = (90, 30, 30, 120)                 # clearance buffer / unreachable
hz[o & rocky] = (255, 150, 30, 190)       # rough: rocks, ledges
hz[o & steep] = (255, 40, 40, 190)        # too steep
save(hz, "hazard")
save(ramp(themis, np.percentile(themis, 2), np.percentile(themis, 98),
          [(10, 10, 60), (90, 20, 120), (200, 60, 60), (250, 180, 40), (255, 255, 200)]), "thermal")
for key, (a, _) in crism.items():
    save(a if a.shape[-1] == 4 else np.dstack([a, np.full(a.shape[:2], 255, np.uint8)]), f"crism_{key}")

# ---------------------------------------------------------------- Unreal inputs
ref_z = float(dem[hr, hc])
np.save(UE_IN / "dem_1m.npy", (dem - ref_z).astype(np.float32))
np.save(UE_IN / "route_px.npy", path)   # full-resolution (row, col) route
# albedo: HiRISE RED (grayscale) tinted with a Mastcam-like Mars palette
pal = ramp(ortho.astype(float), 25, 235, [(38, 22, 14), (120, 70, 42), (178, 116, 72), (222, 170, 120), (245, 214, 176)])
Image.fromarray(pal).save(UE_IN / "albedo_8k.png")

# ---------------------------------------------------------------- site.json
def sample(r, c):
    def px(a, n): return a[min(int(r * n / 2049), n - 1), min(int(c * n / 2049), n - 1)]
    return {
        "elevation_m": round(float(dem[r, c]), 1),
        "slope_deg": round(float(slope[r, c]), 1),
        "relief": "ridge" if tpi[r, c] > 0.3 else "hollow" if tpi[r, c] < -0.3 else "flat",
        "tpi_m": round(float(tpi[r, c]), 2),
        "thermal_dn": int(px(themis, themis.shape[0])),
        "crism": {k: round(int(px(a, a.shape[0])[3]) / 255, 2) for k, (a, _) in crism.items()},
    }


def wp_out(w, i_path):
    r, c = w["rc"]; x, y = to_xy(r, c); la, lo = xy_to_ll(x, y)
    return {k: v for k, v in w.items() if k != "rc"} | {
        "x": x, "y": y, "z": round(float(dem[r, c] - ref_z), 2), "lat": round(la, 6), "lon": round(lo, 6),
        "walk_m": round(float(metres[i_path])), "walk_min": round(float(hours[i_path] * 60)), **sample(r, c)}


site = {
    "name": "Mount Sharp boxwork, Gale crater",
    "center": {"lat": LAT0, "lon": LON0}, "size_m": 2 * HALF, "projection": SRS, "ref_elevation_m": round(ref_z, 1),
    "habitat": wp_out(hab, 0),
    "stops": [wp_out(s, leg_idx[i + 1]) for i, s in enumerate(stops)],
    "route": [[int(c - HALF), int(HALF - r), round(float(dem[r, c] - ref_z), 2)] for r, c in spath],
    "route_stats": {"distance_m": round(float(metres[-1])), "walk_h": round(float(hours[-1]), 2),
                    "eva_h": round(float(total_h), 2), "stop_min": STOP_MIN,
                    "max_slope_deg": round(float(slope[path[:, 0], path[:, 1]].max()), 1),
                    "climb_m": round(float(dz[dz > 0].sum())), "descent_m": round(float(-dz[dz < 0].sum()))},
    "rules": {"slope_max_deg": SLOPE_MAX, "roughness_max_m": ROUGH_MAX, "clearance_m": 2,
              "speed": "Tobler hiking function x0.5 (suit + gear): about 2.5 km/h on flat ground"},
    "eva": {"start_utc": eva_start.isoformat(), "start_ltst": 9.0, "ls": round(s0["ls"], 1),
            "sun": sun_track,
            "radiation": {"dose_equiv_msv_day": RAD_MSV_DAY, "absorbed_mgy_day": RAD_MGY_DAY,
                          "eva_msv": round(RAD_MSV_DAY * total_h / 24, 3),
                          "sep_event_2024_mgy": 8.1,
                          "note": "Background galactic cosmic rays at Gale. A solar particle event can add more "
                                  "in a day than months of background: if a space-weather alert arrives, walk "
                                  "back to the habitat along the planned route."}},
    "weather": {"source": "Curiosity REMS MODRDR, sol 4667 (rover parked inside this site)", "hourly": rems},
    "track": [[round(x), round(y), s] for s, x, y in track],
    "layers": {
        "optical": "HiRISE ESP_019698_1750 RED orthoimage, 25 cm/px",
        "elevation": "HiRISE DTM DTEEC_019698_1750_019988_1750_U01, 1 m/px",
        "slope": "Slope from the HiRISE DTM (degrees)",
        "hazard": f"No-go cells: slope > {SLOPE_MAX:g} deg or local relief > {ROUGH_MAX:g} m, plus 2 m clearance",
        "thermal": "THEMIS night-time IR brightness, 100 m/px (brighter = warmer at night = rockier, less dust)",
        **{f"crism_{k}": f"CRISM FRT000058A3 (2007), 18 m/px. {lbl}" for k, (_, lbl) in crism.items()},
    },
}
(WEB / "site.json").write_text(json.dumps(site, indent=1))
print(json.dumps({k: site[k] for k in ("habitat", "route_stats")}, indent=1))
print("stops", [(s["name"], s["walk_m"], s["relief"]) for s in site["stops"]])
print("eva start", eva_start, "Ls", round(s0["ls"], 1), "sun el", round(s0["elevation"], 1))
