"""Shared GLB scene helpers for the scan->rebuild bake and measurement tools.

Everything is numpy; positions come back in WORLD space (full node TRS / matrix applied)
so the scan and the rebuild can be compared directly.
"""
import io
import numpy as np
from PIL import Image
from glbio import read_glb, accessor, image_bytes


# ---------------------------------------------------------------- transforms
def _quat_mat(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def node_local(n):
    if "matrix" in n:
        return np.array(n["matrix"], dtype=np.float64).reshape(4, 4).T  # glTF is column-major
    m = np.eye(4)
    r = _quat_mat(n.get("rotation", [0, 0, 0, 1]))
    s = np.array(n.get("scale", [1, 1, 1]))
    m[:3, :3] = r * s
    m[:3, 3] = n.get("translation", [0, 0, 0])
    return m


def walk(j):
    """Yield (node_index, node, world_matrix) for every node in the default scene."""
    scene = j["scenes"][j.get("scene", 0)]
    stack = [(ni, np.eye(4)) for ni in scene["nodes"]]
    while stack:
        ni, parent = stack.pop()
        n = j["nodes"][ni]
        w = parent @ node_local(n)
        yield ni, n, w
        for c in n.get("children", []):
            stack.append((c, w))


def xform(m, pos, nrm):
    p = pos @ m[:3, :3].T + m[:3, 3]
    nm = np.linalg.inv(m[:3, :3]).T
    n = nrm @ nm.T
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    return p, n


def mat_class(name, digits=True):
    """'wood2' -> 'wood' (Godot appends digits when the same material is reused)."""
    return name.rstrip("0123456789") if digits else name


# ---------------------------------------------------------------- loaders
def load_rebuild(path):
    """Every primitive of the rebuilt model: world + local attributes and material name."""
    j, b = read_glb(path)
    prims = []
    for ni, n, w in walk(j):
        if "mesh" not in n:
            continue
        for pi, p in enumerate(j["meshes"][n["mesh"]]["primitives"]):
            a = p["attributes"]
            pos = accessor(j, b, a["POSITION"]).astype(np.float64)
            nrm = accessor(j, b, a["NORMAL"]).astype(np.float64) if "NORMAL" in a else np.tile([0.0, 1.0, 0.0], (len(pos), 1))
            idx = (accessor(j, b, p["indices"]).astype(np.int64) if "indices" in p else np.arange(len(pos))).reshape(-1, 3)
            wp, wn = xform(w, pos, nrm)
            mname = j["materials"][p["material"]].get("name", f"mat{p['material']}") if "material" in p else "none"
            prims.append(dict(node=ni, node_name=n.get("name", f"node{ni}"), mesh=n["mesh"], prim=pi, mat=mat_class(mname),
                              material_index=p.get("material"), world=w, pos=pos, nrm=nrm, wpos=wp, wnrm=wn, idx=idx,
                              extra={k: accessor(j, b, v) for k, v in a.items() if k not in ("POSITION", "NORMAL")}))
    return j, b, prims


def load_scan(path):
    """The AI scan (Meshy/Tripo/etc.): merged world-space triangles + UVs + PBR textures.
    Returns pos, nrm, uv, idx, base (HxWx3 uint8), mr (HxWx3 uint8 or None; G=rough, B=metal)."""
    j, b = read_glb(path)
    P, N, U, I = [], [], [], []
    base = mr = None
    off = 0
    for ni, n, w in walk(j):
        if "mesh" not in n:
            continue
        for p in j["meshes"][n["mesh"]]["primitives"]:
            a = p["attributes"]
            if "TEXCOORD_0" not in a:
                continue
            pos = accessor(j, b, a["POSITION"]).astype(np.float64)
            nrm = accessor(j, b, a["NORMAL"]).astype(np.float64)
            wp, wn = xform(w, pos, nrm)
            P.append(wp); N.append(wn); U.append(accessor(j, b, a["TEXCOORD_0"]).astype(np.float64))
            I.append(accessor(j, b, p["indices"]).astype(np.int64).reshape(-1, 3) + off)
            off += len(pos)
            if base is None and "material" in p:
                pbr = j["materials"][p["material"]].get("pbrMetallicRoughness", {})
                tex = lambda ti: np.asarray(Image.open(io.BytesIO(image_bytes(j, b, j["textures"][ti]["source"]))).convert("RGB"))
                if "baseColorTexture" in pbr:
                    base = tex(pbr["baseColorTexture"]["index"])
                if "metallicRoughnessTexture" in pbr:
                    mr = tex(pbr["metallicRoughnessTexture"]["index"])
    if base is None:
        raise SystemExit("scan has no baseColorTexture; nothing to bake")
    return np.concatenate(P), np.concatenate(N), np.concatenate(U), np.concatenate(I), base, mr


# ---------------------------------------------------------------- sampling
def sample_tex(img, uv):
    """Bilinear sample, uv in glTF convention (origin top-left). Returns float 0..1."""
    h, w = img.shape[:2]
    x = np.clip(uv[:, 0] % 1.0 * w - 0.5, 0, w - 1.001)
    y = np.clip(uv[:, 1] % 1.0 * h - 0.5, 0, h - 1.001)
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int)
    fx = (x - x0)[:, None]; fy = (y - y0)[:, None]
    im = img.astype(np.float32) / 255.0
    return (im[y0, x0] * (1 - fx) * (1 - fy) + im[y0, x0 + 1] * fx * (1 - fy)
            + im[y0 + 1, x0] * (1 - fx) * fy + im[y0 + 1, x0 + 1] * fx * fy)


def sample_surface(pos, nrm, uv, idx, n, rng):
    """Area-weighted random points on the mesh, with interpolated normal and UV."""
    tri = pos[idx]
    area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    f = rng.choice(len(idx), size=n, p=area / area.sum())
    r1 = np.sqrt(rng.random(n)); r2 = rng.random(n)
    w = np.stack([1 - r1, r1 * (1 - r2), r1 * r2], 1)
    P = (pos[idx[f]] * w[:, :, None]).sum(1)
    N = (nrm[idx[f]] * w[:, :, None]).sum(1)
    N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-9
    UV = (uv[idx[f]] * w[:, :, None]).sum(1)
    return P, N, UV


# ---------------------------------------------------------------- alignment
def align_scan(pos, ref_min, ref_max, axis="x", scale=None, offset=(0, 0, 0)):
    """Uniformly scale the scan so its extent on `axis` matches the rebuild, sit it on the
    rebuild's floor and center it in X/Z. `scale` overrides the auto scale."""
    ax = "xyz".index(axis)
    lo, hi = pos.min(0), pos.max(0)
    s = scale if scale else (ref_max[ax] - ref_min[ax]) / (hi[ax] - lo[ax])
    p = (pos - lo) * s
    size = (hi - lo) * s
    p[:, 0] += (ref_min[0] + ref_max[0]) / 2 - size[0] / 2
    p[:, 1] += ref_min[1]
    p[:, 2] += (ref_min[2] + ref_max[2]) / 2 - size[2] / 2
    return p + np.asarray(offset), s
