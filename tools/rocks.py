"""Procedural rock meshes + a scatter driven by the DTM roughness (rocks where the terrain is blocky).

Run from the repo root after plan_route.py:  python3 tools/rocks.py
Writes data/site/rocks/rock_<k>.glb and data/site/rocks.csv (type, x, y, z, yaw, scale in Unreal units).
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from glb import write_glb  # noqa: E402
from terrain_mesh import to_gltf  # noqa: E402

SITE = Path(__file__).resolve().parents[1] / "data" / "site"
OUT = SITE / "rocks"
TYPES = 6
ROUGH_ROCK_M = 0.25        # roughness above this gets boulders (no-go starts at 0.5 m)
NEAR_ROUTE_M = 60          # small clasts within this distance of the route, for close-up detail
rng = np.random.default_rng(42)


def icosphere(sub=3):
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
         (8, 6, 7), (9, 8, 1)]
    v = [np.array(p, float) / np.linalg.norm(p) for p in v]
    for _ in range(sub):
        cache, nf = {}, []
        def mid(a, b):
            k = (min(a, b), max(a, b))
            if k not in cache:
                m = (v[a] + v[b]) / 2
                v.append(m / np.linalg.norm(m))
                cache[k] = len(v) - 1
            return cache[k]
        for a, b, c in f:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        f = nf
    return np.array(v), np.array(f)


def rock_mesh(seed):
    r = np.random.default_rng(seed)
    v, f = icosphere(3)
    disp = np.zeros(len(v))
    for octave in range(5):  # fractal noise from random plane waves
        for _ in range(6):
            d = r.normal(size=3); d /= np.linalg.norm(d)
            disp += np.sin(v @ d * (2.5 * 2 ** octave) + r.uniform(0, 6.3)) * 0.35 / 2 ** octave / 6
    for _ in range(3):  # a few flat fracture faces
        d = r.normal(size=3); d /= np.linalg.norm(d)
        cut = r.uniform(0.55, 0.8)
        h = v @ d
        disp = np.where(h * (1 + disp) > cut, cut / np.maximum(h, 1e-3) - 1, disp)
    p = v * (1 + disp)[:, None] * np.array([1.0, r.uniform(0.6, 0.95), r.uniform(0.45, 0.75)])
    p[:, 2] = np.maximum(p[:, 2], -0.25)  # flat-ish base that sits in the regolith
    p *= 50.0  # 1 m nominal size, in cm
    n = np.zeros_like(p)
    tri = p[f]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    for k in range(3):
        np.add.at(n, f[:, k], fn)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    return p, n, f


def bilinear(a, r, c):
    r0 = np.clip(np.floor(r).astype(int), 0, a.shape[0] - 2)
    c0 = np.clip(np.floor(c).astype(int), 0, a.shape[1] - 2)
    fr, fc = r - r0, c - c0
    return (a[r0, c0] * (1 - fr) * (1 - fc) + a[r0 + 1, c0] * fr * (1 - fc)
            + a[r0, c0 + 1] * (1 - fr) * fc + a[r0 + 1, c0 + 1] * fr * fc)


def main():
    OUT.mkdir(exist_ok=True)
    for k in range(TYPES):
        p, n, f = rock_mesh(100 + k)
        # glTF winding: our mesh is outward-CCW in a right-handed frame; to_gltf swaps Y/Z (a mirror), so flip.
        write_glb(OUT / f"rock_{k}.glb", to_gltf(p[:, 0], p[:, 1], p[:, 2]), to_gltf(n[:, 0], n[:, 1], n[:, 2]),
                  np.zeros((len(p), 2)), f[:, ::-1])

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
            rows.append((int(rng.integers(TYPES)), b * 100, a * 100, (h - zmid) * 100 - 15 * s, rng.uniform(0, 360), s))
    with open(SITE / "rocks.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Type", "X", "Y", "Z", "Yaw", "Scale"])
        for row in rows:
            w.writerow([row[0]] + [f"{v:.1f}" if j < 4 else f"{v:.3f}" for j, v in enumerate(row[1:])])
    # check: no clast sits on the walking line itself
    for r_, c_ in ((sr[:3000], sc[:3000]), (br[:3000], bc[:3000])):
        d = np.min(np.hypot(route[None, :, 1] - r_[:, None], route[None, :, 0] - c_[:, None]), axis=1)
        assert (d > 1.0).all(), f"a rock landed on the route ({d.min():.2f} m)"
    print(f"{TYPES} rock meshes, {len(br)} boulders, {len(sr)} clasts -> rocks.csv")


if __name__ == "__main__":
    main()
