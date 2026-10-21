# image-to-3d-rebuild

A [Claude Code](https://claude.com/claude-code) skill that turns a picture of an object into a polished, animated 3D asset.

An AI scan (Meshy, Tripo or similar) is used only as a reference. The deliverable is a clean rebuild in Godot, with the scan's paint baked on, animation and effects that follow Disney's 12 principles at 50% strength, a phone-friendly three.js web viewer, and a demo video.

The workflow comes from r/aigamedev's "new crazy workflow for making 3D assets". This skill adds the steps that make the result good: measure, bake, animate, add effects, test, ship.

## Pipeline

1. Start with an image of the object.
2. Generate a rough 3D scan (Meshy, Tripo, Rodin).
3. Import it into Godot and measure it.
4. Rebuild a clean version that matches the scan's proportions.
5. Bake the scan's painted textures onto the rebuild.
6. Animate and add effects.
7. Export a web viewer and a demo video.

`SKILL.md` has the full steps. `references/` has the detail for each one.

## Install

Copy this folder into your Claude Code skills directory:

```sh
git clone https://github.com/undeadpickle/image-to-3d-rebuild ~/.claude/skills/image-to-3d-rebuild
```

Then ask Claude to make a 3D model or animated prop from an image.

## Requirements

- Godot 4.x
- Python 3 with `numpy scipy xatlas pillow` (for the bake scripts)
- ffmpeg (for the demo video)
- A 3D generation service for the scan step. The skill's examples use Higgsfield's Meshy tool, but any image-to-3D service that outputs a textured GLB works.

## Heads up: `scripts/approver_mcp.py`

This optional script auto-approves permission prompts so a headless `claude -p` run can submit a paid generation you already approved. It only approves a short allowlist and caps submissions, but it is still a permission bypass. Run it only on a prompt you wrote, and keep its tool lists short.

## License

MIT
