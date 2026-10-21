# Step 6–7: phone-viewable web viewer, testing, demo video, publishing

## Web viewer (three.js r160 via jsdelivr importmap)
Start from `scripts/web/viewer_template.html` (read its header comment). Port the Godot
look and behavior:
- Export: `baked.glb` → base64 text (`base64 -i baked.glb > asset_baked.glb.txt`), textures →
  webp (`cwebp -q 88` or PIL), keep ≤ 2048².
- Materials by class name (strip trailing digits Godot adds). Port each Godot shader's look
  into `onBeforeCompile` injections; give each a `customProgramCacheKey`.
- Mirror the Godot timelines as identical JS functions (same constants, same ms).
- Default camera: pulled back so the whole effect is visible (2× the "fit the object"
  distance), capped on tall phones; never refit on UI toggles or quality steps.
- Add a toggle to compare with the raw scan (load `scan.glb.txt` lazily) and a paint toggle.
- Respect `prefers-reduced-motion` (skip anticipation/particles, jump to the end pose).

## Testing the web viewer headlessly (no GPU, no CDN)
- Playwright + Chromium with `--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader`.
- Route `cdn.jsdelivr.net/npm/three@0.160.0/**` to a local `npm i three@0.160.0`
  (sandboxes often block the CDN); stub Google Fonts.
- **Fake clock** (init script): override `performance.now`, `Date.now`,
  `requestAnimationFrame` with a stepper `__step(ms, dt)`. Real-time waits are meaningless
  under swiftshader (2 fps). Click with `element.click()` via evaluate (Playwright's
  "stable" check needs rAF).
- Assert numbers, then look at screenshots: camera position finite, program count unchanged
  after the first action (prewarm worked), item counts/heights over time, lid angle at key
  frames. Use small viewports (≤ 640 px) to keep runs short.
- Test a page that starts at 0×0 (an iframe resized after load). That catches NaN cameras.
- Swiftshader timings say nothing about GPU performance; compile counts do.

## Demo video (Godot Movie Maker)
- `scripts/godot/movie_director.gd`: camera keys (smoothstep between), timed events,
  captions, light changes. Everything on game time.
- Project viewport 1920×1080 (the `--resolution` flag alone isn't enough everywhere).
```
godot --path godot --write-movie renders/video/demo.avi --fixed-fps 30 --resolution 1920x1080 res://tools/movie_director.tscn
ffmpeg -y -i renders/video/demo.avi -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -movflags +faststart media/demo.mp4
ffmpeg -ss <t> -t 3 -i media/demo.mp4 -vf "fps=5,scale=480:-1,tile=5x3" -frames:v 1 sheet.png   # check beats
```
- Show: the reference → scan → rebuild story (title card), every interaction mode at least
  once, the hero moments up close, light/feature controls, an end card. Captions short.
- Leave each action time to finish before the next event (busy guards drop calls).
- Look at contact sheets of every hero beat before sending.
- When re-rendering, move the previous cut to `media/archive/<name>_vN.mp4` (git mv).
- For the web, encode a lighter copy (crf 24) and extract a poster frame.

## Publishing / sharing
- Claude artifact: hosted pages may refuse `.glb` and other binary types; ship the GLB as
  base64 `.txt` and textures as webp through the artifact's `files`. A page can be loaded
  at 0×0 first: guard the camera fit.
- Static site / repo (e.g. a team playground): put the viewer in `public/demos/<asset>/`,
  iframe it from a page with Preview / Video / How-it-was-made tabs; files in `public/` are
  served without the app's auth. Follow the repo's CLAUDE.md conventions (registries,
  i18n, release notes, explicit `git add` paths).
- Commit the project with a README covering workflow, bake, effects, performance, video.
