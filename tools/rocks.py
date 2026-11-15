"""Scatter the scanned rocks (data/assets/polyhaven, see tools/get_assets.py) from the DTM roughness.

Run from the repo root after plan_route.py:  python3 tools/rocks.py
Writes data/site/rocks.csv: mesh name, x, y, ground z (Unreal cm), yaw, size (longest horizontal side, m).
Boulders go where the 1 m DTM is blocky; small clasts line the route for close-up detail (HiRISE cannot see
rocks under ~1 m, so those are placed for scale, not mapped).
"""
import csv
import json
from pathlib import Path

import numpy as np

SITE = Path(__file__).resolve().parents[1] / "data" / "site"
SMALL = ["moon_rock_01_LOD0", "moon_rock_03", "moon_rock_04", "moon_rock_05", "moon_rock_07",
         "namaqualand_rocks_02_a", "namaqualand_rocks_02_b", "namaqualand_rocks_02_c", "namaqualand_rocks_02_d",
         "namaqualand_stones_01_a", "namaqualand_stones_01_b", "namaqualand_stones_01_c", "namaqualand_stones_01_d",
         "namaqualand_stones_01_e"]
BOULDERS = ["namaqualand_boulder_03", "namaqualand_boulder_04", "namaqualand_boulder_05"]
BOULDER_M = 0.9            # rocks this size or larger use the boulder scans (and block the walker)
ROUGH_ROCK_M = 0.25        # roughness above this gets boulders (no-go starts at 0.5 m)
NEAR_ROUTE_M = 60          # small clasts within this distance of the route, for close-up detail
rng = np.random.default_rng(42)


def bilinear(a, r, c):
    r0 = np.clip(np.floor(r).astype(int), 0, a.shape[0] - 2)
    c0 = np.clip(np.floor(c).astype(int), 0, a.shape[1] - 2)
    fr, fc = r - r0, c - c0
    return (a[r0, c0] * (1 - fr) * (1 - fc) + a[r0 + 1, c0] * fr * (1 - fc)
            + a[r0, c0 + 1] * (1 - fr) * fc + a[r0 + 1, c0 + 1] * fr * fc)


def main():
    site = json.loads((SITE / "site.json").read_text())
    g = np.load(SITE / "grids.npz")
    z, rough, slope = g["z"], g["rough"], g["slope"]
    nogo = np.load(SITE / "nogo.npy")
    zmid = (site["elev_min_m"] + site["elev_max_m"]) / 2
    n = z.shape[0]
    route = np.array([[float(r["X"]) / 100, float(r["Y"]) / 100] for r in csv.DictReader(open(SITE / "route.csv"))])

    # Boulders: density follows roughness above the threshold, across the whole site.
    rr, cc = np.nonzero(rough > ROUGH_ROCK_M)
    keep = rng.random(len(rr)) < np.clip((rough[rr, cc] - ROUGH_ROCK_M) * 0.25, 0, 0.08)
    br, bc = rr[keep] + rng.random(keep.sum()), cc[keep] + rng.random(keep.sum())
    bs = rng.uniform(0.35, 1.4, len(br)) * (1 + rough[rr[keep], cc[keep]])

    # Small clasts near the route (but never on it): what a walker sees at their feet.
    m = 70000
    i = rng.integers(0, len(route), m)
    ang, dist = rng.uniform(0, 2 * np.pi, m), rng.uniform(1.2, NEAR_ROUTE_M, m) ** 1.0
    sr, sc = route[i, 1] + np.sin(ang) * dist, route[i, 0] + np.cos(ang) * dist
    inside = (sr > 1) & (sr < n - 2) & (sc > 1) & (sc < n - 2)
    sr, sc = sr[inside], sc[inside]
    ss = rng.lognormal(np.log(0.22), 0.6, len(sr)).clip(0.05, 1.1)

    # Keep the walking line clear: drop anything within ~1.5 m of the route (plus its own radius).
    clear = np.zeros((n, n), bool)
    for a, b in zip(route, route[1:]):
        t = np.linspace(0, 1, 8)
        clear[np.round(a[1] + (b[1] - a[1]) * t).astype(int), np.round(a[0] + (b[0] - a[0]) * t).astype(int)] = True
    from scipy import ndimage
    clear = ndimage.binary_dilation(clear, iterations=2)
    def off_route(r_, c_, s_):
        ok = ~clear[np.clip(np.round(r_).astype(int), 0, n - 1), np.clip(np.round(c_).astype(int), 0, n - 1)] & (s_ < 1.0)
        big = s_ >= 1.0  # large boulders: stay 3 m clear
        far = ~ndimage.binary_dilation(clear, iterations=3)[np.clip(np.round(r_).astype(int), 0, n - 1), np.clip(np.round(c_).astype(int), 0, n - 1)]
        k = ok | (big & far)
        return r_[k], c_[k], s_[k]
    br, bc, bs = off_route(br, bc, bs)
    sr, sc, ss = off_route(sr, sc, ss)

    rows = []
    for r_, c_, s_ in ((br, bc, bs), (sr, sc, ss)):
        zz = bilinear(z, r_, c_)
        for a, b, h, s in zip(r_, c_, zz, s_):
            mesh = BOULDERS[rng.integers(len(BOULDERS))] if s >= BOULDER_M else SMALL[rng.integers(len(SMALL))]
            rows.append((mesh, b * 100, a * 100, (h - zmid) * 100, rng.uniform(0, 360), s))
    with open(SITE / "rocks.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Mesh", "X", "Y", "Z", "Yaw", "SizeM"])
        for row in rows:
            w.writerow([row[0]] + [f"{v:.1f}" if j < 4 else f"{v:.3f}" for j, v in enumerate(row[1:])])
    # check: no clast sits on the walking line itself
    for r_, c_ in ((sr[:3000], sc[:3000]), (br[:3000], bc[:3000])):
        d = np.min(np.hypot(route[None, :, 1] - r_[:, None], route[None, :, 0] - c_[:, None]), axis=1)
        assert (d > 1.0).all(), f"a rock landed on the route ({d.min():.2f} m)"
    print(f"{len(br)} rocks on blocky ground, {len(sr)} clasts by the route, {sum(r[5] >= BOULDER_M for r in rows)} boulder-size -> rocks.csv")


if __name__ == "__main__":
    main()
