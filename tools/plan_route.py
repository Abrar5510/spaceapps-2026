"""Plan the Marswalk route over the baked site grids and check it.

Run from the repo root after prep_site.py:  python3 tools/plan_route.py
Writes data/site/route.csv, data/site/stops.csv and data/site/route_stats.json, then runs check().
"""
import csv
import heapq
import json
import math
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "data" / "site"

# --- Suit assumptions (change here; cited in README) -------------------------------------------
PACE_FLAT = 0.7          # m/s on flat firm ground in a pressurised suit (Apollo EVA traverses ~0.7-1 m/s)
SLOPE_LIMIT = 20.0       # deg; steeper cells are no-go (Apollo crews found >15-20 deg hard going)
ROUGH_LIMIT = 0.5        # m height spread in 3 m window; above = blocky rock / ledge, no-go
SAND_TI = 350.0          # thermal inertia (SI) below which footing is treated as loose sand
SAND_PENALTY = 0.3       # up to 30% slower on the loosest ground in the box
STOP_MINUTES = 30        # time on task at each science stop
# Radiation: Curiosity RAD, Gale surface, quiet Sun (Hassler et al. 2014, Science 343)
DOSE_QUIET_MGY_PER_DAY = 0.21
DOSE_QUIET_MSV_PER_DAY = 0.64
# Solar storm: RAD recorded 8.1 mGy during the 20 May 2024 solar energetic particle event (NASA/JPL, June 2024)
DOSE_STORM_MGY_PER_DAY = 8.1

# Habitat and stops: Curiosity's own positions on these sols (MSL localization, MSL_waypoints.json).
POINTS = [
    ("Habitat", 4541, "Flat, firm ground north of the boxwork; Curiosity parked here on sol 4541."),
    ("Ridge stop", 4628, "Boxwork ridge crest: cemented ridge rock where groundwater once flowed through fractures."),
    ("Monte Grande hollow", 4693, "Hollow between ridges; Curiosity drilled 'Valle de la Luna' here (sol 4693)."),
    ("Nevado Sajama ridge", 4718, "Ridge beside the hollow; Curiosity drilled 'Nevado Sajama' here (sol 4718). Pair it with the hollow sample."),
    ("South boxwork margin", 4855, "Where the boxwork network fades; sample the edge to bracket how far the groundwater reached."),
]
# ------------------------------------------------------------------------------------------------

DIRS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def load():
    site = json.loads((SITE / "site.json").read_text())
    g = np.load(SITE / "grids.npz")
    return site, g["z"], g["slope"], g["rough"], g["ti"]


def lonlat_to_rc(site, lon, lat):
    nw, se = site["corners_lonlat"]["nw"], site["corners_lonlat"]["se"]
    n = site["samples"]
    return (lat - nw[1]) / (se[1] - nw[1]) * n - 0.5, (lon - nw[0]) / (se[0] - nw[0]) * n - 0.5


def rover_position(sol):
    feats = json.loads((ROOT / "data" / "raw" / "MSL_waypoints.json").read_text())["features"]
    best = min(feats, key=lambda f: (abs(f["properties"]["sol"] - sol), -f["properties"]["drive"]))
    lon, lat = best["geometry"]["coordinates"][:2]
    return lon, lat


def speed(grade, sand):
    """Walking speed (m/s): Tobler's hiking function scaled to suit pace, slowed on sand."""
    tobler = math.exp(-3.5 * abs(grade + 0.05)) / math.exp(-3.5 * 0.05)
    return PACE_FLAT * tobler / (1 + SAND_PENALTY * sand)


def build_graph(z, slope, rough, ti):
    n = z.shape[0]
    nogo = (slope > SLOPE_LIMIT) | (rough > ROUGH_LIMIT)
    sand = np.clip((SAND_TI - ti) / (SAND_TI - ti.min() + 1e-6), 0, 1)
    idx = np.arange(n * n).reshape(n, n)
    rows, cols, w = [], [], []
    for dr, dc in DIRS:
        r0, r1 = max(0, -dr), n - max(0, dr)
        c0, c1 = max(0, -dc), n - max(0, dc)
        a = (slice(r0, r1), slice(c0, c1))
        b = (slice(r0 + dr, r1 + dr), slice(c0 + dc, c1 + dc))
        dist = math.hypot(dr, dc)
        grade = (z[b] - z[a]) / dist
        tobler = np.exp(-3.5 * np.abs(grade + 0.05)) / math.exp(-3.5 * 0.05)
        sp = PACE_FLAT * tobler / (1 + SAND_PENALTY * 0.5 * (sand[a] + sand[b]))
        ok = ~(nogo[a] | nogo[b])
        if dr and dc:  # no corner-cutting past a no-go cell on a diagonal step
            ok &= ~(nogo[r0 + dr:r1 + dr, c0:c1] | nogo[r0:r1, c0 + dc:c1 + dc])
        rows.append(idx[a][ok]); cols.append(idx[b][ok]); w.append((dist / sp)[ok])
    g = csr_matrix((np.concatenate(w), (np.concatenate(rows), np.concatenate(cols))), shape=(n * n, n * n))
    return g, nogo, sand


def snap(rc, nogo):
    """Nearest walkable cell to a (row, col) point."""
    r, c = int(round(rc[0])), int(round(rc[1]))
    if not nogo[r, c]:
        return r, c
    pq = [(0, r, c)]
    seen = {(r, c)}
    while pq:
        d, i, j = heapq.heappop(pq)
        if not nogo[i, j]:
            return i, j
        for di, dj in DIRS:
            k = (i + di, j + dj)
            if k not in seen and 0 <= k[0] < nogo.shape[0] and 0 <= k[1] < nogo.shape[1]:
                seen.add(k)
                heapq.heappush(pq, ((k[0] - r) ** 2 + (k[1] - c) ** 2, *k))
    raise RuntimeError("no walkable cell")


def line_cells(a, b):
    """Grid cells under the straight segment a->b (sampled every 0.25 m)."""
    steps = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) * 4))
    t = np.linspace(0, 1, steps + 1)
    return np.round(a[0] + (b[0] - a[0]) * t).astype(int), np.round(a[1] + (b[1] - a[1]) * t).astype(int)


def straighten(path, nogo):
    """String-pull: skip ahead to the farthest point whose straight line stays 1 m clear of no-go cells."""
    nogo = ndimage.binary_dilation(nogo, np.ones((3, 3), bool))
    out, i = [path[0]], 0
    while i < len(path) - 1:
        j = len(path) - 1
        while j > i + 1:
            rr, cc = line_cells(path[i], path[j])
            if not nogo[rr, cc].any():
                break
            j -= 1
        out.append(path[j])
        i = j
    return out


def bilinear(a, r, c):
    r0, c0 = int(np.clip(math.floor(r), 0, a.shape[0] - 2)), int(np.clip(math.floor(c), 0, a.shape[1] - 2))
    fr, fc = r - r0, c - c0
    return float(a[r0, c0] * (1 - fr) * (1 - fc) + a[r0 + 1, c0] * fr * (1 - fc)
                 + a[r0, c0 + 1] * (1 - fr) * fc + a[r0 + 1, c0 + 1] * fr * fc)


def main():
    site, z, slope, rough, ti = load()
    n = z.shape[0]
    print("building graph ...")
    graph, nogo, sand = build_graph(z, slope, rough, ti)

    pts = []
    for name, sol, note in POINTS:
        lon, lat = rover_position(sol)
        r, c = snap(lonlat_to_rc(site, lon, lat), nogo)
        pts.append({"name": name, "sol": sol, "note": note, "lon": lon, "lat": lat, "rc": (r, c)})
        print(f"  {name:22s} sol {sol}  row {r} col {c}")

    order = pts + [pts[0]]  # loop back to the habitat
    full = []
    stop_idx = [0]
    for a, b in zip(order, order[1:]):
        src, dst = a["rc"][0] * n + a["rc"][1], b["rc"][0] * n + b["rc"][1]
        dist, pred = dijkstra(graph, indices=src, return_predecessors=True)
        if not np.isfinite(dist[dst]):
            raise SystemExit(f"no walkable path {a['name']} -> {b['name']}")
        leg, k = [], dst
        while k != src:
            leg.append((k // n, k % n))
            k = pred[k]
        leg.append((src // n, src % n))
        leg = straighten(leg[::-1], nogo)
        full.extend(leg if not full else leg[1:])
        stop_idx.append(len(full) - 1)

    # Resample every ~1 m for the walk, keep vertices at stops.
    samples, stop_at = [], {}
    for i, (a, b) in enumerate(zip(full, full[1:])):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        k = max(1, int(seg))
        for t in range(k):
            samples.append((a[0] + (b[0] - a[0]) * t / k, a[1] + (b[1] - a[1]) * t / k))
        if i + 1 in stop_idx:
            stop_at[len(samples)] = stop_idx.index(i + 1)
    samples.append(full[-1])
    stop_at[0] = 0

    zmid = (site["elev_min_m"] + site["elev_max_m"]) / 2
    rows, cum_d, cum_t, climb, prev = [], 0.0, 0.0, 0.0, None
    for i, (r, c) in enumerate(samples):
        h = bilinear(z, r, c)
        sl = float(slope[int(round(r)), int(round(c))])  # cell value: what the no-go test used
        if prev:
            d = math.hypot(r - prev[0], c - prev[1])
            dz = h - prev[2]
            cum_d += d
            cum_t += d / speed(dz / d if d else 0, bilinear(sand, r, c)) if d else 0
            climb += max(0.0, dz)
        stop = stop_at.get(i, -1)
        rows.append({"x_m": c, "y_m": r, "elev_m": h, "slope_deg": sl,
                     "dist_m": cum_d, "walk_s": cum_t, "stop": stop,
                     "ue_x": c * 100.0, "ue_y": r * 100.0, "ue_z": (h - zmid) * 100.0})
        prev = (r, c, h)
    rows[-1]["stop"] = 0  # back at habitat

    with open(SITE / "route.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Name", "X", "Y", "Z", "SlopeDeg", "DistM", "WalkS", "Stop"])  # first column = DataTable row name
        for i, r in enumerate(rows):
            w.writerow([i, f"{r['ue_x']:.1f}", f"{r['ue_y']:.1f}", f"{r['ue_z']:.1f}",
                        f"{r['slope_deg']:.2f}", f"{r['dist_m']:.2f}", f"{r['walk_s']:.1f}", r["stop"]])

    walk_s = rows[-1]["walk_s"]
    eva_h = (walk_s + STOP_MINUTES * 60 * (len(POINTS) - 1)) / 3600
    stop_rows = {}
    for i, r in enumerate(rows):
        if r["stop"] >= 0 and r["stop"] not in stop_rows:
            stop_rows[r["stop"]] = r
    with open(SITE / "stops.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Name", "Title", "Sol", "Lon", "Lat", "X", "Y", "Z", "DistM", "WalkS", "Note"])
        for k, p in enumerate(pts):
            r = stop_rows[k]
            w.writerow([k, p["name"], p["sol"], f"{p['lon']:.6f}", f"{p['lat']:.6f}",
                        f"{r['ue_x']:.1f}", f"{r['ue_y']:.1f}", f"{r['ue_z']:.1f}",
                        f"{r['dist_m']:.1f}", f"{r['walk_s']:.0f}", p["note"]])

    stats = {
        "distance_m": round(rows[-1]["dist_m"], 1),
        "climb_m": round(climb, 1),
        "steepest_slope_deg": round(max(r["slope_deg"] for r in rows), 1),
        "walk_time_min": round(walk_s / 60, 1),
        "stop_time_min": STOP_MINUTES * (len(POINTS) - 1),
        "eva_time_h": round(eva_h, 2),
        "dose_quiet_mGy": round(DOSE_QUIET_MGY_PER_DAY * eva_h / 24, 4),
        "dose_quiet_mSv": round(DOSE_QUIET_MSV_PER_DAY * eva_h / 24, 4),
        "dose_storm_mGy": round(DOSE_STORM_MGY_PER_DAY * eva_h / 24, 3),
        "dose_rates": {"quiet_mGy_day": DOSE_QUIET_MGY_PER_DAY, "quiet_mSv_day": DOSE_QUIET_MSV_PER_DAY,
                       "storm_mGy_day": DOSE_STORM_MGY_PER_DAY},
        "assumptions": {"pace_flat_m_s": PACE_FLAT, "slope_limit_deg": SLOPE_LIMIT, "rough_limit_m": ROUGH_LIMIT,
                        "sand_ti": SAND_TI, "sand_penalty": SAND_PENALTY, "stop_minutes": STOP_MINUTES},
        "nogo_fraction": round(float(nogo.mean()), 3),
        "stops": [{"name": p["name"], "sol": p["sol"], "dist_m": round(stop_rows[k]["dist_m"], 1)} for k, p in enumerate(pts)],
    }
    (SITE / "route_stats.json").write_text(json.dumps(stats, indent=2))
    np.save(SITE / "nogo.npy", nogo)
    save_images(rows, nogo)
    print(json.dumps(stats, indent=2))
    check(rows, nogo, n)


def save_images(rows, nogo):
    """layer_hazard.png for the Unreal layer material, route_map.png for the README and plan view."""
    from PIL import Image, ImageDraw
    n = nogo.shape[0]
    ortho = np.asarray(Image.open(SITE / "ortho.png").convert("L").resize((n, n)), dtype=float)
    base = np.stack([ortho * 0.55] * 3, axis=-1)
    base[nogo] = base[nogo] * 0.35 + np.array([220, 30, 30]) * 0.65
    Image.fromarray(base.astype(np.uint8)).resize((2048, 2048), Image.BILINEAR).save(SITE / "layer_hazard.png")

    im = Image.open(SITE / "ortho.png").convert("RGB").resize((1024, 1024))
    over = Image.fromarray(np.where(nogo[..., None], np.array([220, 30, 30], np.uint8), 0).astype(np.uint8)).resize((1024, 1024))
    mask = Image.fromarray((nogo * 90).astype(np.uint8)).resize((1024, 1024))
    im.paste(over, (0, 0), mask)
    d = ImageDraw.Draw(im)
    k = 1024 / n
    d.line([(r["x_m"] * k, r["y_m"] * k) for r in rows], fill=(80, 230, 255), width=4)
    for r in rows:
        if r["stop"] >= 0:
            x, y = r["x_m"] * k, r["y_m"] * k
            d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=(255, 255, 255), outline=(0, 0, 0), width=2)
            d.text((x - 3, y - 6), "H" if r["stop"] == 0 else str(r["stop"]), fill=(0, 0, 0))
    im.save(SITE / "route_map.png")


def check(rows, nogo, n):
    """Every step under the slope limit, no step in a no-go cell, loop closes at the habitat."""
    for a, b in zip(rows, rows[1:]):
        rr, cc = line_cells((a["y_m"], a["x_m"]), (b["y_m"], b["x_m"]))
        assert not nogo[rr, cc].any(), f"route crosses no-go near ({a['x_m']:.0f}, {a['y_m']:.0f})"
        assert a["slope_deg"] <= SLOPE_LIMIT, f"slope {a['slope_deg']:.1f} at {a['dist_m']:.0f} m"
    assert math.hypot(rows[0]["x_m"] - rows[-1]["x_m"], rows[0]["y_m"] - rows[-1]["y_m"]) < 1e-6, "loop not closed"
    assert sorted({r["stop"] for r in rows if r["stop"] >= 0}) == list(range(len(POINTS))), "a stop is missing"
    print(f"check passed: {len(rows)} samples, no no-go cells, slope <= {SLOPE_LIMIT} deg, loop closed")


if __name__ == "__main__":
    main()
