"""The view beyond the 2 km site: the rest of the same HiRISE DTM and orthoimage at 10 m per vertex.

    python3 tools/far_terrain.py        -> data/site/far_terrain.glb, data/site/far_ortho.jpg

Without it the walker sees a flat haze line where the site box ends. This is scenery only: no route, layers
or collision out there. Same projection, same height datum and same tint as the site (tools/prep_site.py).
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from glb import write_glb  # noqa: E402
from prep_site import DTM, ORTHO, SRS, X0, Y1, N  # noqa: E402
from terrain_mesh import to_gltf  # noqa: E402

SITE = Path(__file__).resolve().parents[1] / "data" / "site"
STEP = 10.0                                   # metres per vertex
WEST, EAST, SOUTH, NORTH = -4010.0, 3490.0, -298790.0, -280320.0   # DTM footprint in SRS metres, trimmed to STEP
TEX = (3072, 8192)                            # far_ortho.jpg, about 2.4 m per pixel


def warp(src, w, h, resample, nodata):
    tmp = SITE / "_far.bin"
    subprocess.run(["gdalwarp", "-q", "-overwrite", "-t_srs", SRS, "-te", str(WEST), str(SOUTH), str(EAST), str(NORTH),
                    "-ts", str(w), str(h), "-r", resample, "-ot", "Float32", "-of", "ENVI", "-dstnodata", str(nodata),
                    "-wo", "NUM_THREADS=ALL_CPUS", str(src), str(tmp)], check=True)
    a = np.fromfile(tmp, dtype="<f4").reshape(h, w)
    for p in (tmp, tmp.with_suffix(".hdr"), Path(str(tmp) + ".aux.xml")):
        p.unlink(missing_ok=True)
    return np.where(a == nodata, np.nan, a)


def main():
    site = json.loads((SITE / "site.json").read_text())
    zmid = (site["elev_min_m"] + site["elev_max_m"]) / 2
    w, h = int((EAST - WEST) / STEP), int((NORTH - SOUTH) / STEP)
    z = warp(DTM, w, h, "average", -32768)
    rows, cols = np.mgrid[0:h, 0:w]
    xm, ym = WEST + (cols + 0.5) * STEP, NORTH - (rows + 0.5) * STEP
    ux, uy = (xm - X0 - 0.5) * 100.0, (Y1 - ym - 0.5) * 100.0          # Unreal cm, same frame as the site tiles
    inside = (ux > 0) & (ux < (N - 1) * 100.0) & (uy > 0) & (uy < (N - 1) * 100.0)
    deep = (ux > 2500) & (ux < (N - 1) * 100.0 - 2500) & (uy > 2500) & (uy < (N - 1) * 100.0 - 2500)
    zc = (np.nan_to_num(z, nan=zmid) - zmid) * 100.0
    zc[inside] -= 400.0                                                 # tuck under the 1 m tiles where they overlap
    gy, gx = np.gradient(zc, STEP * 100.0)
    nrm = np.dstack([-gx, -gy, np.ones_like(zc)])
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    ok = ~np.isnan(z) & ~deep                                           # no data, or well inside the site: no surface
    i = np.arange(h * w).reshape(h, w)
    a, b, c, d = i[:-1, :-1], i[:-1, 1:], i[1:, :-1], i[1:, 1:]
    quad = (ok[:-1, :-1] & ok[:-1, 1:] & ok[1:, :-1] & ok[1:, 1:]).reshape(-1)
    tris = np.concatenate([np.stack([a, c, b], -1).reshape(-1, 3)[quad], np.stack([b, c, d], -1).reshape(-1, 3)[quad]])
    uv = np.stack([(cols + 0.5) / w, (rows + 0.5) / h], -1).reshape(-1, 2)
    write_glb(SITE / "far_terrain.glb", to_gltf(ux, uy, zc).reshape(-1, 3),
              to_gltf(nrm[..., 0] * 100, nrm[..., 1] * 100, nrm[..., 2] * 100).reshape(-1, 3), uv, tris)

    o = warp(ORTHO, TEX[0], TEX[1], "average", 0)
    lo, hi = np.nanpercentile(o, [0.5, 99.5])
    g = np.clip((np.nan_to_num(o, nan=np.nanmedian(o)) - lo) / (hi - lo), 0, 1)
    tint_dark, tint_light = np.array([62, 38, 24]), np.array([226, 178, 132])   # as prep_site.py
    Image.fromarray((tint_dark + g[..., None] * (tint_light - tint_dark)).astype(np.uint8)).save(SITE / "far_ortho.jpg", quality=90)
    assert len(tris) > 500000 and not np.isnan(zc).any()
    print(f"far terrain: {w} x {h} vertices, {len(tris)} triangles, relief {np.nanmin(z):.0f} to {np.nanmax(z):.0f} m")


if __name__ == "__main__":
    main()
