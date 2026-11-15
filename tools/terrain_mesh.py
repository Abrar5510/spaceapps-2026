"""Turn the 1 m DTM into 4 x 4 terrain tiles (binary glTF) for Unreal Nanite static meshes.

Run from the repo root after prep_site.py:  python3 tools/terrain_mesh.py
Vertex (row, col) sits at Unreal X = col*100, Y = row*100, Z = (elev - mid)*100 cm, exactly where the
heightmap/Landscape convention in site.json puts it, so the route and textures line up.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from glb import write_glb  # noqa: E402

SITE = Path(__file__).resolve().parents[1] / "data" / "site"
OUT = SITE / "terrain"
TILES = 4
OVERLAP_M = 4


def to_gltf(x, y, z):
    """Unreal (X east, Y south, Z up; cm) -> glTF (Y up, metres) as Unreal's glTF importer reads it back."""
    return np.stack([x, z, y], axis=-1) / 100.0


def main():
    OUT.mkdir(exist_ok=True)
    site = json.loads((SITE / "site.json").read_text())
    z = np.load(SITE / "grids.npz")["z"].astype(np.float64)
    n = z.shape[0]
    zc = (z - (site["elev_min_m"] + site["elev_max_m"]) / 2) * 100.0
    gy, gx = np.gradient(zc, 100.0)  # d z / d row, d z / d col (cm per cm)
    nrm = np.dstack([-gx, -gy, np.ones_like(zc)])
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    step = (n - 1) // TILES
    assert step * TILES == n - 1
    for tr in range(TILES):
        for tc in range(TILES):
            # Each tile reaches OVERLAP_M into its neighbours: identical surface twice, so the seams stay closed
            # when Nanite simplifies tile borders (a hanging skirt showed through as dark slivers).
            r0, r1 = max(tr * step - OVERLAP_M, 0), min((tr + 1) * step + OVERLAP_M, n - 1)
            c0, c1 = max(tc * step - OVERLAP_M, 0), min((tc + 1) * step + OVERLAP_M, n - 1)
            rr, cc = np.mgrid[r0:r1 + 1, c0:c1 + 1]
            pos = to_gltf(cc * 100.0, rr * 100.0, zc[rr, cc]).reshape(-1, 3)
            nn = nrm[rr, cc]
            nor = to_gltf(nn[..., 0] * 100, nn[..., 1] * 100, nn[..., 2] * 100).reshape(-1, 3)
            uv = np.stack([cc / (n - 1), rr / (n - 1)], -1).reshape(-1, 2)
            i = np.arange(rr.size).reshape(rr.shape)
            a, b, c, d = i[:-1, :-1], i[:-1, 1:], i[1:, :-1], i[1:, 1:]
            tris = [np.stack([a, c, b], -1).reshape(-1, 3), np.stack([b, c, d], -1).reshape(-1, 3)]
            write_glb(OUT / f"terrain_{tr}_{tc}.glb", pos, nor, uv, np.concatenate(tris))
    print(f"{TILES * TILES} tiles of {step + 1}^2 vertices -> {OUT}")


if __name__ == "__main__":
    main()
