#!/usr/bin/env python3
"""Bake an AI scan's painted textures (Meshy / Tripo / Rodin GLB) onto a clean rebuilt model.

  python3 bake_scan.py --scan scan.glb --rebuild rebuild.glb --out out/ \
      [--map wood=base,brass=metal,iron=metal] [--res 2048] [--tex 2048] \
      [--align-axis x] [--scale S] [--offset X,Y,Z] [--radius R] [--samples 5000000]

How it works
  1. Align: uniform-scale the scan so its extent on --align-axis matches the rebuild's
     bounding box, put it on the rebuild's floor, center X/Z (override with --scale/--offset).
  2. Unwrap: xatlas packs every baked rebuild primitive into one shared atlas -> TEXCOORD_1.
  3. Transfer: each atlas texel finds nearby scan surface samples of the SAME class that face
     the same way, and inverse-distance averages their color / roughness / metal.
     Classes: --map assigns rebuild material names to a scan class:
        base  = scan samples whose metal map < --metal-threshold
        metal = scan samples whose metal map >= --metal-threshold
        all   = every scan sample (default for every material when --map is omitted)
     Rebuild materials not in --map (when --map is given) are left unbaked.
  4. Alpha = confidence (distance + facing). Texels the scan never covered (insides, hidden
     faces, parts the scan fused together) get alpha 0 so the engine shader falls back to its
     procedural look there. Gutters are nearest-filled so mips never bleed black.

Outputs (in --out): baked.glb (same node tree, + TEXCOORD_1), baked_albedo.png (RGB + alpha
confidence), baked_orm.png (R=1 occlusion, G=roughness, B=metal, A=confidence),
debug_atlas.png (magenta = no data), bake_report.json.
Needs: numpy scipy xatlas pillow   (pip install numpy scipy xatlas pillow)
"""
import argparse, json, os, sys, time
import numpy as np
import xatlas
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scene import load_rebuild, load_scan, sample_surface, sample_tex, align_scan  # noqa: E402
from glbio import Writer  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--scan", required=True)
ap.add_argument("--rebuild", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--map", default="", help="rebuild_material=base|metal|all, comma separated")
ap.add_argument("--res", type=int, default=2048, help="atlas resolution used for the transfer")
ap.add_argument("--tex", type=int, default=2048, help="output texture size")
ap.add_argument("--align-axis", default="x", choices=list("xyz"))
ap.add_argument("--scale", type=float, default=None)
ap.add_argument("--offset", default="0,0,0")
ap.add_argument("--radius", type=float, default=None, help="search radius in rebuild units (default 4.5%% of bbox diagonal)")
ap.add_argument("--samples", type=int, default=5_000_000)
ap.add_argument("--metal-threshold", type=float, default=0.35)
ap.add_argument("--padding", type=int, default=6)
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)
t0 = time.time()
log = lambda *a: print(f"[{time.time() - t0:6.1f}s]", *a, flush=True)

# ---------------------------------------------------------------- inputs
src_j, src_b, prims = load_rebuild(args.rebuild)
allpos = np.concatenate([p["wpos"] for p in prims])
rmin, rmax = allpos.min(0), allpos.max(0)
diag = float(np.linalg.norm(rmax - rmin))
R = args.radius or 0.045 * diag

classes = {}
if args.map:
    for kv in args.map.split(","):
        k, v = kv.split("=")
        classes[k.strip()] = v.strip()
else:
    classes = {p["mat"]: "all" for p in prims}
bake_ids = [i for i, p in enumerate(prims) if p["mat"] in classes]
if not bake_ids:
    raise SystemExit(f"no rebuild materials matched --map; rebuild has {sorted({p['mat'] for p in prims})}")
log("rebuild materials:", sorted({p["mat"] for p in prims}), "-> baking", sorted({prims[i]["mat"] for i in bake_ids}))

spos, snrm, suv, sidx, sbase, smr = load_scan(args.scan)
spos, s = align_scan(spos, rmin, rmax, args.align_axis, args.scale, [float(x) for x in args.offset.split(",")])
log(f"scan aligned: scale {s:.4f}, scan bbox {spos.min(0).round(3)} .. {spos.max(0).round(3)}, rebuild {rmin.round(3)} .. {rmax.round(3)}")

rng = np.random.default_rng(7)
P, N, UV = sample_surface(spos, snrm, suv, sidx, args.samples, rng)
COL = sample_tex(sbase, UV)
MR = sample_tex(smr, UV) if smr is not None else np.tile([1.0, 0.7, 0.0], (len(P), 1)).astype(np.float32)
is_metal = MR[:, 2] >= args.metal_threshold
pools = {"all": np.ones(len(P), bool), "base": ~is_metal, "metal": is_metal}
trees, data = {}, {}
for name in set(classes.values()):
    m = pools[name]
    if m.sum() < 100:
        log(f"WARNING: scan class '{name}' has only {m.sum()} samples; falling back to 'all'")
        m = pools["all"]
    trees[name] = cKDTree(P[m])
    data[name] = (N[m], COL[m], MR[m])
log(f"scan samples ready; metal share {is_metal.mean():.2f}")

# ---------------------------------------------------------------- unwrap
atlas = xatlas.Atlas()
for i in bake_ids:
    p = prims[i]
    atlas.add_mesh(p["wpos"].astype(np.float32), p["idx"].astype(np.uint32), p["wnrm"].astype(np.float32))
co = xatlas.ChartOptions(); co.max_iterations = 2
po = xatlas.PackOptions(); po.resolution = args.res; po.padding = args.padding; po.bilinear = True
atlas.generate(co, po)
W, H = atlas.width, atlas.height
log(f"atlas {W}x{H}, {atlas.chart_count} charts")
new = {}
for k, i in enumerate(bake_ids):
    vmap, ind, uvs = atlas[k]
    new[i] = (vmap.astype(np.int64), ind.astype(np.int64), uvs.astype(np.float32))

# ---------------------------------------------------------------- rasterize texel -> surface point
posmap = np.zeros((H, W, 3), np.float32)
nrmmap = np.zeros((H, W, 3), np.float32)
clsmap = np.full((H, W), -1, np.int16)
cls_names = sorted(set(classes.values()))
for i in bake_ids:
    p = prims[i]
    vmap, ind, uvs = new[i]
    V = p["wpos"][vmap]; Nn = p["wnrm"][vmap]
    px = uvs * [W, H]
    code = cls_names.index(classes[p["mat"]])
    for t in ind:
        a, b, c = px[t]
        x0 = int(max(np.floor(min(a[0], b[0], c[0])) - 1, 0)); x1 = int(min(np.ceil(max(a[0], b[0], c[0])) + 1, W - 1))
        y0 = int(max(np.floor(min(a[1], b[1], c[1])) - 1, 0)); y1 = int(min(np.ceil(max(a[1], b[1], c[1])) + 1, H - 1))
        if x1 < x0 or y1 < y0:
            continue
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / den
        w1 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / den
        w2 = 1 - w0 - w1
        inside = (w0 >= -0.02) & (w1 >= -0.02) & (w2 >= -0.02)
        if not inside.any():
            continue
        yy, xx = np.nonzero(inside)
        ww = np.stack([w0[inside], w1[inside], w2[inside]], 1).clip(0, 1)
        ww /= ww.sum(1, keepdims=True)
        posmap[yy + y0, xx + x0] = ww @ V[t]
        nn = ww @ Nn[t]
        nrmmap[yy + y0, xx + x0] = nn / (np.linalg.norm(nn, axis=1, keepdims=True) + 1e-9)
        clsmap[yy + y0, xx + x0] = code
log(f"rasterized {(clsmap >= 0).sum()} texels")

# ---------------------------------------------------------------- transfer
albedo = np.zeros((H, W, 4), np.float32)
orm = np.zeros((H, W, 4), np.float32)
report = {"scale": s, "radius": R, "classes": {}}
for code, name in enumerate(cls_names):
    ys, xs = np.nonzero(clsmap == code)
    if not len(ys):
        continue
    q = posmap[ys, xs]; qn = nrmmap[ys, xs]
    sn, sc, smr_ = data[name]
    d, ii = trees[name].query(q, k=12, distance_upper_bound=R, workers=-1)
    ok = np.isfinite(d)
    iic = np.where(ok, ii, 0)
    dots = np.einsum("nkc,nc->nk", sn[iic], qn)
    strict = ok & (dots > 0.4)
    loose = ok & (dots > -0.2) & (d < R * 0.83)
    use_strict = strict.any(1)
    sel = np.where(use_strict[:, None], strict, loose)
    wts = sel / (d + R * 0.05)
    wsum = wts.sum(1)
    has = wsum > 0
    wn = np.where(has[:, None], wts / np.maximum(wsum, 1e-9)[:, None], 0)
    c = np.einsum("nk,nkc->nc", wn, sc[iic])
    m = np.einsum("nk,nkc->nc", wn, smr_[iic])
    dmin = np.where(sel, d, np.inf).min(1)
    conf = np.where(use_strict, np.clip(1 - (dmin - R * 0.5) / (R * 0.5), 0, 1),
                    np.clip(1 - (dmin - R * 0.42) / (R * 0.41), 0, 1) * 0.9) * has
    albedo[ys, xs, :3] = c; albedo[ys, xs, 3] = conf
    orm[ys, xs, 0] = 1.0; orm[ys, xs, 1] = m[:, 1]; orm[ys, xs, 2] = m[:, 2]; orm[ys, xs, 3] = conf
    report["classes"][name] = {"texels": int(len(ys)), "covered": float(has.mean()), "strict": float(use_strict.mean()),
                               "mean_confidence": float(conf.mean())}
    log(f"{name}: {len(ys)} texels, covered {has.mean():.3f}, strict {use_strict.mean():.3f}, mean conf {conf.mean():.2f}")

# ---------------------------------------------------------------- gutters + low-confidence RGB
cover = clsmap >= 0
_, (iy, ix) = ndimage.distance_transform_edt(~cover, return_indices=True)
for img in (albedo, orm):
    img[~cover] = img[iy[~cover], ix[~cover]]
known = albedo[..., 3] > 0.3
if known.any():
    _, (ky, kx) = ndimage.distance_transform_edt(~known, return_indices=True)
    for img in (albedo, orm):
        img[..., :3] = np.where(known[..., None], img[..., :3], img[ky, kx, :3])

T = args.tex
Image.fromarray((albedo.clip(0, 1) * 255).astype(np.uint8), "RGBA").resize((T, T), Image.LANCZOS).save(os.path.join(args.out, "baked_albedo.png"))
Image.fromarray((orm.clip(0, 1) * 255).astype(np.uint8), "RGBA").resize((T, T), Image.LANCZOS).save(os.path.join(args.out, "baked_orm.png"))
dbg = np.where(~cover[..., None], 30, albedo[..., :3] * albedo[..., 3:] * 255 + (1 - albedo[..., 3:]) * np.array([255, 0, 255])).astype(np.uint8)
Image.fromarray(dbg).resize((1024, 1024)).save(os.path.join(args.out, "debug_atlas.png"))
log("textures saved")

# ---------------------------------------------------------------- write GLB (same tree, + TEXCOORD_1)
w = Writer()
for m in src_j.get("materials", []):
    pbr = {k: v for k, v in m.get("pbrMetallicRoughness", {}).items() if not k.endswith("Texture")}
    w.j["materials"].append({"name": m.get("name", ""), "pbrMetallicRoughness": pbr or {"metallicFactor": 0.0, "roughnessFactor": 0.8}})
keep = lambda k: k.startswith(("TEXCOORD_", "COLOR_", "TANGENT"))
for mi, mesh in enumerate(src_j["meshes"]):
    out_prims = []
    for pi, sp in enumerate(mesh["primitives"]):
        i = next((k for k, p in enumerate(prims) if p["mesh"] == mi and p["prim"] == pi), None)
        p = prims[i]
        if i in new:
            vmap, ind, uv1 = new[i]
        else:
            vmap = np.arange(len(p["pos"])); ind = p["idx"]; uv1 = np.zeros((len(p["pos"]), 2), np.float32)
        kind = lambda a: {1: "SCALAR", 2: "VEC2", 3: "VEC3", 4: "VEC4"}[a.shape[1] if a.ndim > 1 else 1]
        attrs = {"POSITION": w.add_accessor(p["pos"][vmap].astype(np.float32), "VEC3"),
                 "NORMAL": w.add_accessor(p["nrm"][vmap].astype(np.float32), "VEC3")}
        for k, a in p["extra"].items():
            if keep(k) and k != "TEXCOORD_1":
                attrs[k] = w.add_accessor(np.asarray(a, np.float32)[vmap], kind(np.asarray(a)))
        attrs["TEXCOORD_1"] = w.add_accessor(uv1.astype(np.float32), "VEC2")
        prim = {"attributes": attrs, "indices": w.add_accessor(ind.reshape(-1).astype(np.uint32), "SCALAR", index=True)}
        if "material" in sp:
            prim["material"] = sp["material"]
        out_prims.append(prim)
    w.j["meshes"].append({"name": mesh.get("name", f"mesh{mi}"), "primitives": out_prims})
w.j["nodes"] = src_j["nodes"]
w.j["scenes"] = src_j["scenes"]
w.j["scene"] = src_j.get("scene", 0)
for k in ("images", "textures", "samplers"):
    if not w.j[k]:
        del w.j[k]
w.save(os.path.join(args.out, "baked.glb"))
json.dump(report, open(os.path.join(args.out, "bake_report.json"), "w"), indent=2)
log("baked.glb saved ->", args.out)
