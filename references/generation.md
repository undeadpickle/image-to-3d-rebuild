# Step 1–2: reference image → rough 3D scan

## Prepare the image
- One object, centered, 3/4 view, plain or transparent background, no text, no cropping of
  parts. 1024–2048 px. If the user's image has a busy background, cut it out first.
- Note what the image shows that a scan will lose: thin parts (handles, chains), separate
  moving parts (lids, doors, wheels), interiors, small hardware. The rebuild must add these.

## Generators (pick by what's connected; ask the user only if none is)
| Route | Model | Notes |
|---|---|---|
| Higgsfield MCP | `meshy_v7_image_to_3d` (newest Meshy at time of writing; check the model list) | `generate_3d` with `get_cost:true` first. ~38 credits for one standard textured model. |
| Meshy API | image-to-3d v5+/v7 | `should_texture`, `enable_pbr` for base color + metallic/roughness maps. |
| Tripo / Rodin / Hunyuan3D | image-to-3d | Fine as references. Check that the output GLB has a base color texture (the bake needs it) and ideally a metallic map (for the material split). |

Higgsfield `generate_3d` params that worked well:
```
model: "meshy_v7_image_to_3d"
medias: [{ value: <uploaded media_id>, role: "image_references" }]
should_texture: true, enable_pbr: true, model_type: "standard", topology: "triangle",
target_polycount: 30000, symmetry_mode: "auto", should_remesh: true,
enable_rigging: false, enable_animation: false, count: 1
```
(omit `folder_id` unless the user has one).

## Rules for paid generations
- **Respect the user's budget exactly.** If they approved N generations, track the count and
  stop at N. Always run the price preflight (`get_cost:true`) and stop if it is far above the
  expected cost.
- **Never resubmit after a timeout.** A transport timeout does not mean the job failed:
  look it up (`show_generation_by_ids`, `jobs_wait`) and keep waiting.
- Long-poll with `jobs_wait` repeatedly; 3D jobs take several minutes.
- Download every output (GLB, textures, thumbnails) with `curl` into `scan/` and write
  `scan/result.json` (job id, cost, raw job JSON).

## Headless runs blocked by an "ask" rule
If generation must run in a headless `claude -p` subprocess and the user's settings have an
"ask" rule on the generation tool, headless mode can't show the prompt and denies the call,
even under `bypassPermissions`. **Never edit the user's settings.** If (and only if) the user has
already approved the spend, use `scripts/approver_mcp.py` as `--permission-prompt-tool`: it
approves only the listed tools and caps submissions (see the docstring for the command).
Keep `ToolSearch` allowed, or the MCP tools can't load. Write the subprocess prompt to a file
(`gen_prompt.txt`) that spells out: media id, preflight, exactly one submit, no resubmit on
timeout, poll, download, write result.json, print a summary.

## First look at the scan
1. Import into Godot (`models/scan.glb`), run `capture.gd` for 4 views (3/4 matching the
   reference, front, side, back 3/4). Compare against the reference image.
2. `measure_scan.py scan.glb --size x=<real width>`: bbox, slices and front/side/top
   projections with a 10 cm grid. This is the measurement source for the rebuild.
3. Write down what's wrong with the scan (it is a reference, not the asset): fused moving
   parts, lumpy hard edges, smeared hardware, baked lighting in the texture, no interior,
   messy topology, wrong scale.
