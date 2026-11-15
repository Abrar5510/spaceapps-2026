"""Write the route as draped ribbon meshes (binary glTF) for the walk view and the plan view.

Run from the repo root after plan_route.py:  python3 tools/route_mesh.py
"""
import csv
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from glb import write_glb  # noqa: E402
from terrain_mesh import to_gltf  # noqa: E402

SITE = Path(__file__).resolve().parents[1] / "data" / "site"


def ribbon(pts, width, lift, path):
    verts = []
    for i, (x, y, z) in enumerate(pts):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L * width / 2, dx / L * width / 2
        verts += [(x + nx, y + ny, z + lift), (x - nx, y - ny, z + lift)]
    v = np.array(verts)
    tris = []
    for i in range(len(pts) - 1):
        a, b, c, d = 2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 3
        tris += [(a, c, b), (b, c, d)]
    pos = to_gltf(v[:, 0], v[:, 1], v[:, 2])
    nrm = to_gltf(np.zeros(len(v)), np.zeros(len(v)), np.full(len(v), 100.0))
    along = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(pts, pts[1:])])]) / 100.0
    uv = np.stack([np.repeat(along, 2), np.tile([0, 1], len(pts))], -1)   # U = metres along the route
    write_glb(path, pos, nrm, uv, np.array(tris))


def main():
    rows = list(csv.DictReader(open(SITE / "route.csv")))
    pts = [(float(r["X"]), float(r["Y"]), float(r["Z"])) for r in rows]
    ribbon(pts, 22, 8, SITE / "route_walk.glb")         # 0.22 m line, 8 cm above ground
    ribbon(pts[::3] + [pts[-1]], 700, 150, SITE / "route_plan.glb")  # 7 m line for the overhead view
    print(len(pts), "route samples -> route_walk.glb, route_plan.glb")


if __name__ == "__main__":
    main()
