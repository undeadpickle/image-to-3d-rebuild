# Step 5: interaction, effects and physics ("juice")

Recipes from the treasure-chest build, written generically. Apply the animation principles
(references/animation-principles.md) to every one of them, at the 50% default.

## Interaction design
- One tap = one beat, with a clear state machine: `idle → anticipation → action → settle`.
  Ignore input while busy (`is_busy()`); expose options as explicit modes
  (e.g. `close_behavior`: leave items / vacuum them back).
- Every beat gets: anticipation, a hero moment (≤ 250 ms), and follow-through.
- The hero moment gets a 1–3 frame hit: a brief flash or light spike, a shock ring, a bloom
  bump, a small camera kick. **Brief and not blinding**: peak flash opacity ≤ 0.85,
  exponential decay 40–90 ms, bloom +0.5 max, exposure +0.15–0.3 max.

## Physics loot (things that burst out and land)
- Godot: `RigidBody3D` with `continuous_cd`, per-piece `PhysicsMaterial`; container
  colliders: concave mound, walls, and an `AnimatableBody3D` for a moving lid.
  `physics_ticks_per_second = 120` for small fast objects.
- Web: a small custom sim (gravity, floor/wall contacts, restitution, friction, spin damping,
  settle-to-flat), no physics library needed for < 500 pieces.
- **Mass ∝ size³**; `heavy = clamp(log2(1 + mass) / 3)`: heavy pieces launch slower, bounce
  less (`0.45 → 0.12`), more friction, more angular damping, settle fast. Light ones roll on
  edge or spin down flat (give some coins an axis spin).
- Randomize everything per open (direction, speed, spin, size, which pieces spill) but use a
  seeded RNG for the demo video.
- Cap the total on the floor (e.g. 420) when items accumulate.
- Per-item look: random emission strength per piece, ~1 in 20 "hero" pieces (a big gem with
  refraction/transmission), visible facets (low-poly gem geometry + flat shading).
- Hero props that stay in the container (goblet, cross, scrolls…) are built with lathe /
  prisms and placed by hand, scaled so they read from the default camera.

## Particles: closed-form on the GPU
Every particle's position is a pure function of `TIME` and a per-particle seed
(Godot `shader_type particles` writing `TRANSFORM`, three.js `Points` with a vertex
shader). No CPU simulation, deterministic, cheap. Modes that worked:
- swirl/vortex (helix arms), envelope that **dissipates after ~4 s** (only on the action)
- aura motes spiralling up and fading
- burst sparks on the hero moment
- **inflow**: spiral in from a shell, `k = phase^1.8` accelerating into a mouth point; global
  `uOn` 0–1; cut to 0 (and hide) in one frame when the container seals ("power contained")
- **suck**: one uniform that pulls every system toward a sink (rotate + shrink + fade).

## Vacuum / recall (items return)
1. **Wind-up (≈950 ms):** items lift 5–11 cm (light more, heavy less), hover with a
   tremble (position jitter 4–5 mm, small rotation wobble), dip back toward the floor.
   The container trembles subtly in sync (≈0.006 rad) and goes still right before release.
2. **Release:** each item spirals in (`e = u^2.1`, radius × (1 − e), angle += e·(2.4 + r0)),
   arcs up over the rim, dives and shrinks into the mouth. Stagger: random 0–140 ms + by
   distance. Aura/rays get pulled in with the `suck` uniform.
3. **Seal:** compute the last item's arrival time up front; start the close so the lid
   **hits exactly as the last item enters** (`closeStart = lastEnd − slamDuration`).

## Seal / slam (closing with weight)
Wind-up lift of the lid (+3.5%, 70 ms) → accelerating slam (`pow(k, 3.2)`, 180 ms) →
in the seal frame: inflow + aura + rays cut to zero, a blink of light from the seam
(light spike, 45 ms decay) → the container (already hopping 2–3 cm and tilting off one
corner as the items pour in) is driven down, lands corner-first (squash 4%), a low ring rolls
out on the floor, camera thud (h/v offset 1.6 cm, 110 ms decay) → rocks across its corners
2–3 times → the lid rattles on its seat (overlapping action).

## Stage and light
- Dark room, one radial spotlight on the object, floor that falls off to black (fog that
  follows camera distance). Expose strength, radius and color; brighten ~1.4× during
  the action.
- Objects react to the light: glints (star sprites) whose rate/size scale with the light
  level, emissive pieces, transmission/iridescence on hero gems, rim on metals.

## Performance rules
- Warm up every pipeline before the first big moment: Godot: draw one of each material
  hidden for a few frames (`_warm_up()`); web: `prewarm()` compiling against the composer's
  render target. Measure the hero moment's worst frame (`perf_probe.gd`; web: count
  `renderer.info.programs` before/after the first action — it must not change).
- Shadows only for pieces > 3 cm. Pixel ratio ≤ 1.6 on phones, step down when frames
  average > 28 ms. One draw call per material class on the main asset.
- Use a game-time clock (`_clock += delta`) for anything filmed, never wall time.

## Bugs that will happen
- The hero effect re-fires on the closing bounce: reset the "fired" flag only once the lid is
  fully shut (< 0.12) and not during the recall.
- The flash is blinding the first time you see it: it's always too bright, halve it.
- A shared `onBeforeCompile` without `customProgramCacheKey` makes materials share programs.
- A late-added uniform not declared in every shader that reads it fails to compile only on
  that path (e.g. `uSuck` in the column shader).
