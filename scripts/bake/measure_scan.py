#!/usr/bin/env python3
"""Measure an AI scan so the rebuild can match its proportions (and later be baked).

  python3 measure_scan.py scan.glb --size x=1.0 [--out measure/] [--slices 12] [--rebuild rebuild.glb]

--size axis=meters  uniformly scales the scan so that axis spans that many meters (pick the
                    real-world size of the object; default: keep the scan's own units)
Prints: bounding box, per-axis extents, metal share (if the scan has a metal map), and
cross-section tables (extent of the surface in each slice along X, Y and Z, split into
base/metal), which is where proportions like "lid seam at 0.465 m", "strap at x=±0.38" come from.
Writes orthographic color projections (front/side/top) of the scan as PNGs, with a 10 cm grid,
plus the same for --rebuild overlaid in cyan outlines so mismatches are obvious.
Needs: numpy pillow (scipy not required)
"""
import argparse, os, sys
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scene import load_scan, load_rebuild, sample_surface, sample_tex  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("scan")
ap.add_argument("--size", default=None, help="axis=meters, e.g. x=1.05")
ap.add_argument("--out", default="measure")
ap.add_argument("--slices", type=int, default=12)
ap.add_argument("--samples", type=int, default=1_500_000)
ap.add_argument("--metal-threshold", type=float, default=0.35)
ap.add_argument("--rebuild", default=None)
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)

pos, nrm, uv, idx, base, mr = load_scan(args.scan)
lo, hi = pos.min(0), pos.max(0)
s = 1.0
if args.size:
    ax, m = args.size.split("=")
    a = "xyz".index(ax)
    s = float(m) / (hi[a] - lo[a])
pos = (pos - [(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2]) * s   # centered in X/Z, on the floor
rng = np.random.default_rng(1)
P, N, UV = sample_surface(pos, nrm, uv, idx, args.samples, rng)
C = sample_tex(base, UV)
metal = sample_tex(mr, UV)[:, 2] >= args.metal_threshold if mr is not None else np.zeros(len(P), bool)
lo, hi = P.min(0), P.max(0)
print(f"scale {s:.5f}   bbox {lo.round(4)} .. {hi.round(4)}")
print(f"extents  x {hi[0]-lo[0]:.4f}  y {hi[1]-lo[1]:.4f}  z {hi[2]-lo[2]:.4f}   metal share {metal.mean():.2f}")

for ai, an in enumerate("xyz"):
    o = [i for i in range(3) if i != ai]
    print(f"\nslices along {an}: [{'xyz'[o[0]]} range] [{'xyz'[o[1]]} range]  metal%")
    edges = np.linspace(lo[ai], hi[ai], args.slices + 1)
    for k in range(args.slices):
        m = (P[:, ai] >= edges[k]) & (P[:, ai] < edges[k + 1])
        if m.sum() < 20:
            continue
        q = P[m]
        print(f"  {an}={edges[k]:+.3f}..{edges[k+1]:+.3f}  {'xyz'[o[0]]} {q[:,o[0]].min():+.3f}..{q[:,o[0]].max():+.3f}"
              f"   {'xyz'[o[1]]} {q[:,o[1]].min():+.3f}..{q[:,o[1]].max():+.3f}   {100*metal[m].mean():4.0f}%")

reb = None
if args.rebuild:
    _, _, prims = load_rebuild(args.rebuild)
    reb = np.concatenate([p["wpos"] for p in prims])

PX = 900
span = float((hi - lo).max()) * 1.1
for name, (u, v, d, flip) in {"front": (0, 1, 2, 1), "side": (2, 1, 0, 1), "top": (0, 2, 1, -1)}.items():
    img = np.full((PX, PX, 3), 24, np.uint8)
    zbuf = np.full((PX, PX), -1e9)
    cu, cv = (lo[u] + hi[u]) / 2, (lo[v] + hi[v]) / 2
    x = ((P[:, u] - cu) / span + 0.5) * PX
    y = (0.5 - (P[:, v] - cv) / span) * PX
    depth = P[:, d] * flip
    ok = (x >= 0) & (x < PX) & (y >= 0) & (y < PX)
    order = np.argsort(depth[ok])
    xi, yi = x[ok].astype(int)[order], y[ok].astype(int)[order]
    img[yi, xi] = (C[ok][order] * 255).astype(np.uint8)
    im = Image.fromarray(img)
    dr = ImageDraw.Draw(im)
    for g in np.arange(-3, 3.01, 0.1):
        gx = ((g - cu) / span + 0.5) * PX; gy = (0.5 - (g - cv) / span) * PX
        dr.line([(gx, 0), (gx, PX)], fill=(60, 60, 60) if abs(g) > 1e-6 else (120, 60, 60))
        dr.line([(0, gy), (PX, gy)], fill=(60, 60, 60) if abs(g) > 1e-6 else (120, 60, 60))
    if reb is not None:
        rx = ((reb[:, u] - cu) / span + 0.5) * PX
        ry = (0.5 - (reb[:, v] - cv) / span) * PX
        for a, b in zip(rx[::7], ry[::7]):
            dr.point((a, b), fill=(0, 255, 255))
    im.save(os.path.join(args.out, f"scan_{name}.png"))
print(f"\nprojections -> {args.out}/scan_front.png, scan_side.png, scan_top.png (grid = 10 cm)")
