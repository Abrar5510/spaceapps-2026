"""Minimal binary glTF (GLB) writer for one triangle mesh: positions, normals, uv, uint32 indices."""
import json
import struct

import numpy as np


def write_glb(path, pos, nrm, uv, idx):
    pos, nrm, uv = (np.ascontiguousarray(a, np.float32) for a in (pos, nrm, uv))
    idx = np.ascontiguousarray(idx, np.uint32).ravel()
    blobs, views, acc = [], [], []
    off = 0
    for arr, target, typ, comp in ((pos, 34962, "VEC3", 5126), (nrm, 34962, "VEC3", 5126),
                                   (uv, 34962, "VEC2", 5126), (idx, 34963, "SCALAR", 5125)):
        b = arr.tobytes()
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(b), "target": target})
        a = {"bufferView": len(views) - 1, "componentType": comp, "count": len(arr), "type": typ}
        if typ == "VEC3" and target == 34962 and not acc:
            a["min"], a["max"] = pos.min(0).tolist(), pos.max(0).tolist()
        acc.append(a)
        blobs.append(b + b"\0" * ((4 - len(b) % 4) % 4))
        off += len(blobs[-1])
    gltf = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "indices": 3}]}],
            "buffers": [{"byteLength": off}], "bufferViews": views, "accessors": acc}
    js = json.dumps(gltf).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    bin_ = b"".join(blobs)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(bin_)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(bin_), 0x004E4942) + bin_)
