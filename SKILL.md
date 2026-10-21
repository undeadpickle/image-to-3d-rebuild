---
name: image-to-3d-rebuild
description: Turn an image of any object into a polished, animated 3D asset. An AI scan (Meshy/Tripo) is the reference; the deliverable is a clean Godot rebuild with the scan's paint baked on, animation and effects that follow Disney's principles at 50% strength, a phone-friendly web viewer and a demo video. Use when someone wants a 3D model or animated prop made from a picture. Don't use for plain mesh conversion or for 2D art.
---

# Image → 3D asset (scan, rebuild, bake, animate, ship)

The workflow comes from r/aigamedev's "new crazy workflow for making 3D assets" and was
proven end to end on a treasure chest:

1. Start with an image of the object.
2. Generate a rough 3D model with Meshy, Tripo or a similar service.
3. Import it into Godot.
4. Build a better replacement that uses the scan as reference.

This skill adds the steps that make the result good: measure, bake, animate, add effects,
test, ship.

The scan is **never** the deliverable. It is a measuring stick and a paint source.

## Defaults (override only when the user says so)
- **Engine:** Godot 4.x (GDScript). **Web:** three.js r160 via an importmap. **Video:** Godot Movie Maker → ffmpeg.
- **Animation:** apply Disney's 12 principles **wherever they fit the object and goal**, at **50% intensity**. Nothing linear or bland, nothing cartoony. Read `references/animation-principles.md` before animating anything. If the user names a percentage, use it.
- **Budget:** paid generations: use exactly the number the user approved. Always preflight the price. Never resubmit after a timeout.
- **Autonomy:** when the user says "loop until done", keep iterating with renders and comparisons. Don't stop for approvals unless something is risky or costs money beyond what they approved.
- **Never** edit the user's global settings or permissions to get around a prompt.

## Pipeline

### 1. Intake (ask once, briefly, only if unclear)
Settle these before starting:
- The object.
- Its real-world size.
- Which parts move: lid, door, wheels or other hinges.
- What interaction they want.
- The generation budget.
- Where the project lives. Default: `~/Projects/<object>-3d/`, a git repo.

Note what the image shows that a scan will lose: thin parts, separate moving parts, interiors and small hardware.

### 2. Generate the scan → `references/generation.md`
1. Upload the image.
2. Preflight the cost.
3. Submit exactly one generation, then poll and download the GLB and its textures into `scan/`.
   - Higgsfield MCP: `meshy_v7_image_to_3d` (or the newest Meshy).
   - Otherwise use the Meshy, Tripo or Rodin API.
4. Headless runs that are blocked by an "ask" rule can use `scripts/approver_mcp.py`, but only for spend the user has already approved. It auto-approves prompts, so keep its tool lists minimal and never run it on a prompt the user didn't write.

### 3. Inspect and measure
1. Set up a Godot project:
   - Viewport 1920×1080.
   - Physics at 120 Hz if small things will fly.
   - Copy the skill's `scripts/godot/*` into `godot/tools/` and `scripts/bake/*` into `tools/bake/`.
2. Render the scan from 4 views with `tools/capture.gd`, matching the reference angle first.
3. Run `python3 tools/bake/measure_scan.py scan/scan.glb --size x=<meters>` to get the bounding box, slices and front/side/top projections on a 10 cm grid.
4. List what's wrong with the scan: fused parts, mushy edges, smeared hardware, no interior, lighting baked into the texture.

### 4. Rebuild → `references/rebuild.md`
1. Decompose the object into parts, pivots and 2–5 material classes (`wood`, `metal`…).
2. Build procedurally with `ProcBuilder` (`tools/proc_builder.gd`). It provides chamfered boxes, arcs, prisms, domes, cylinders and lathes.
   - Put measurements in named constants.
   - Use one surface per material class.
   - Write a `@tool` script.
   - Give it a clear API: a state property plus `open()`, `close()`, `toggle()` and `is_busy()`, or the equivalent for the object.
3. Iterate with side-by-side renders against the scan until proportions match. Save a `_vN_backup.gd` for each version. Look at the images; don't assume.
4. Use shaders per class: a procedural base plus baked paint on UV2, mixed by the bake's alpha.

### 5. Bake the scan's paint → `tools/bake/bake_scan.py`
1. Export at rest pose with `export_glb.gd --call=set_open_amount:0`.
2. Run `bake_scan.py --scan … --rebuild … --map wood=base,metal=metal`.
3. Check `bake_report.json` and `debug_atlas.png`.
4. Load `baked.glb` with the shaders.
5. Add a `paint` 0–1 control.
6. Show a comparison of procedural only, baked and the scan.

### 6. Animate, add effects and physics → `references/animation-principles.md`, `references/effects-and-physics.md`
- **Write each hero beat as a pure timeline function** of time in ms, mirrored exactly in GDScript and JS.
- **Every beat** gets anticipation, a fast action, an impact moment, then follow-through and overlapping action.
- **Lifts** are organic: tilt on two axes about a base edge, land corner-first, rock to rest.
- **Effects:**
  - GPU particles in closed form.
  - A brief, non-blinding flash or shock ring on hero moments.
  - Physics items with mass ∝ size³.
  - A stage with a dark room and a controllable spotlight.
  - Glints that react to the light.
- **Interaction modes** are explicit: for example, leave the items out vs. vacuum them back.
- **Warm up** every shader or pipeline before the first big moment.

### 7. Verify (every round, before reporting)
- **Godot:** headless runs show no script errors. A probe script prints the key values over time: pose, counts, heights, lid angle.
- **Godot performance:** `perf_probe.gd`. The worst frame at the hero moment should be ≤ ~1.5× the average.
- **Web:** Playwright + swiftshader with a fake clock.
  - No page errors.
  - A finite camera, including on a 0×0 first load.
  - `renderer.info.programs` doesn't change after the first action.
  - Screenshots at the key frames.
- **Visual review:** look at contact sheets or screenshots of every hero beat, and fix anything that's linear, blinding or cartoony.

### 8. Ship → `references/web-and-video.md`
- **Web viewer:** build it from `scripts/web/viewer_template.html`. Use base64 GLB `.txt` and webp textures, and pull the default camera back 2× so the whole effect is visible.
- **Demo video:** `movie_director.gd` → Movie Maker → mp4. Show every mode and hero beat, with short captions. Check contact sheets before sending, and archive old cuts in `media/archive/`.
- **Publishing:** publish as an artifact or to the user's site or repo as asked, and commit the project with a README.

## Feedback loop with the user
- Users react to feel: "snappier", "more weight", "less shaking", "too cartoony". Translate each into concrete changes:
  - **Timing:** shorter action, longer settle.
  - **Amplitude:** scale it by the intensity dial.
  - **Missing principle:** add anticipation, overlapping action, a hit frame or tilt.
- Apply each change to Godot and the web viewer together.
- Redeploy the viewer, and re-render the video if asked.
- Keep timings consistent across the pieces. For example, the lid should land exactly when the last item enters. Compute that from data, not a guess.

## Files in this skill
- `scripts/bake/bake_scan.py`, `scene.py`, `glbio.py`: scan → rebuild texture transfer (numpy, scipy, xatlas, pillow).
- `scripts/bake/measure_scan.py`: dimensions, slices and grid projections of the scan.
- `scripts/godot/capture.gd`: multi-view renders of any GLB or scene. `--call` poses it and `--frame` frames one subtree (e.g. the model without its FX).
- `scripts/godot/export_glb.gd`: procedural scene → GLB with class-named materials.
- `scripts/godot/proc_builder.gd`: the `ProcBuilder` mesh kit.
- `scripts/godot/perf_probe.gd`: frame-time phases for a scripted sequence of calls.
- `scripts/godot/movie_director.gd`: deterministic demo-video template.
- `scripts/web/viewer_template.html`: three.js viewer with baked UV2 paint, bloom, prewarm, adaptive DPR, camera fit and shake.
- `scripts/approver_mcp.py`: scoped permission-prompt server for approved headless generations.
- `references/*.md`: details for each step. Read the one for the step you're on.
