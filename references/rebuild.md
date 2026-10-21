# Step 3–4: rebuild a clean replacement in Godot, then bake the scan's paint on

The scan is reference only. The deliverable is a clean, procedural (or hand-modeled) asset:
real parts, real pivots, chamfered edges, sane topology, named materials, an API.

## Project layout
```
<project>/
  reference.png            scan/ (raw GLB + result.json)
  godot/  project.godot (1920x1080 viewport, physics 120 Hz if physics matters)
    models/scan.glb        asset/asset.gd + asset.tscn + *.gdshader
    tools/ capture.gd export_glb.gd perf_probe.gd movie_director.gd proc_builder.gd
    export/asset.glb       models/asset_baked.glb + baked_albedo.png + baked_orm.png
  tools/bake/              (copy of scripts/bake)
  web/                     viewer (index.html + *.glb.txt + *.webp)
  media/                   demo video, comparison images (media/archive/ for old cuts)
```
Copy the skill's `scripts/` in; don't reference the skill folder from the project.

## Decompose the object
1. List parts from the reference + scan: body shells, moving parts (lid, door, drawer, wheel,
   hinge), trims/straps/bands, hardware (rivets, plates, lock, handles), feet, interior.
2. For each moving part, decide the pivot (hinge axis at the back edge, wheel axle…). Each
   moving part is its own node under a pivot `Node3D`; the API drives the pivot.
3. Assign material classes by real material, not by color: `wood`, `metal`, `cloth`,
   `glass`, `stone`… Keep the list short (2–5). Each class becomes one surface.
4. Measure everything from `measure_scan.py` (slices + projections). Put measurements in
   named constants at the top of the script (W, D, SEAM, CY, R, STRAP_X, MT…).

## Build
- Use `ProcBuilder` (`scripts/godot/proc_builder.gd`): `box` (chamfered), `arc` (curved
  shells/bands), `prism_x` (profiles), `dome` (rivets, studs), `cylinder`, `lathe`
  (goblets, vases, knobs). One `use("class", tint)` per part; vary tint per plank/panel.
- Chamfer every hard edge (1–3% of the part size). Vertex color G marks chamfers so the
  shader can add edge wear/highlights.
- `@tool` script with `_build()` in `_ready()` so the editor shows it; expose a state
  property (`open_amount` 0–1, allow ~1.1 for overshoot) whose setter applies the pose.
- API for anything interactive: `open()`, `close()`, `toggle()`, `is_busy()`,
  `set_open_amount(v)`, signals for beats (`opened_burst`), plus exported knobs
  (`close_behavior`, `anticipation`).
- Shaders: procedural base per class (wood grain from planar UVs in meters, metal with edge
  wear from vertex G), plus `baked_albedo`/`baked_orm` sampled on UV2 and mixed by the
  baked alpha (confidence). Use `hint_default_transparent` so a missing bake shows the
  procedural look.

## Iterate against the scan
Loop until the side-by-side matches (usually 3–5 passes; save `asset_vN_backup.gd`):
```
godot --path godot --script res://tools/capture.gd -- --target=res://models/scan.glb --out=res://renders/scan
godot --path godot --script res://tools/capture.gd -- --target=res://asset/asset.tscn --out=res://renders/v3
```
Compare the same views; fix proportions first (silhouette, seam height, part positions), then
details. Compose comparisons with PIL into one image and look at it. Before baking, the
rebuild's proportions must match the scan (width, depth, seam height, hardware positions),
or the paint lands in the wrong place.

## Bake the scan's paint onto the rebuild
```
godot --headless --path godot --script res://tools/export_glb.gd -- --scene=res://asset/asset.tscn --out=res://export/asset.glb --call=set_open_amount:0
python3 tools/bake/bake_scan.py --scan scan/scan.glb --rebuild godot/export/asset.glb \
    --out godot/models/ --map wood=base,metal=metal [--res 2048]
```
- `--map`: which rebuild classes take paint from which scan class. Without a metal map in the
  scan, use `all`. Hardware that's tiny or fused in the scan (rivets, chains) is better left
  procedural: leave it out of `--map`.
- Check the two bboxes the script prints. Auto-align scales the scan to the rebuild's extent
  on `--align-axis`; if the rebuild has parts the scan lacks (handles, a pile of treasure,
  a base) that axis is off. Pass `--scale` (the factor `measure_scan.py --size` printed) or an
  axis both share. Misalignment shows up as paint shifted across seams in the debug atlas.
- Read `bake_report.json` (coverage per class) and look at `debug_atlas.png` (magenta = no
  data; expected inside, under parts, on faces the scan fused).
- Rest pose matters: export with moving parts closed (the scan is closed).
- Then load `baked.glb` in a `asset_baked.gd` that assigns the shader materials by name and
  feeds the two textures; add a `paint` 0–1 uniform so the user can compare.
- Compare: procedural only / baked / scan, same 3 views, one image.

## Common mistakes
- Godot front faces are **clockwise**; ProcBuilder orients from normals, raw SurfaceTool
  code must do the same or faces vanish.
- GDScript can't infer types from untyped loop arrays: `for s: float in [-1.0, 1.0]`.
- GDScript lambdas capture locals **by value**: a local reassigned inside one lambda is not
  seen by another (or by the caller). Share mutable state through an Array
  (`var ys := [0.0]`) or a member/method instead.
- Too-dark metal in Godot: lower `metallic` (0.5–0.6) and add `metallic_specular`/rim, or
  give the scene a reflection source; pure metallic in a dark room renders black.
