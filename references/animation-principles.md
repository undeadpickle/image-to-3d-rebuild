# Animation principles (default intensity: 50%)

Every animated beat in this pipeline gets Disney's 12 principles applied **where they fit
the object and the goal**, at a default **intensity of 50%**: enough that nothing feels linear,
mechanical or bland, not so much that it reads as cartoony. The user can change the dial
("push it to 80%", "make it subtle, 30%"). Scale amplitudes (overshoot, squash, anticipation
depth, secondary motion) by `intensity / 50%`; scale *timing* differences far less (timing sells
weight, it shouldn't get sloppy at low intensity).

## The dial in numbers (at 50%)

| Principle | 50% default | Cartoony (100%) | Notes |
|---|---|---|---|
| Squash & stretch | 2–4% volume-preserving (`y = s, xz = 1/sqrt(s)`) on impacts only | 10–25% | Rigid props (wood, metal) stay ≤ 4%. Soft things (slime, cloth, creatures) can go 8%. |
| Anticipation | 5–15% of the main move, 150–400 ms before it | 25–40%, 500 ms+ | Opposite direction to the action: lid strains/dips before snapping open; loot rises before being sucked in. |
| Staging | One clear read per beat; camera and light point at it | — | Kill competing motion during the key beat (the vortex dissipates before the next beat). |
| Straight ahead vs pose-to-pose | Pose-to-pose: timelines as pure functions of time with key poses | — | Physics (loot) is the "straight ahead" layer on top. |
| Follow-through & overlapping action | Parts settle 60–150 ms after the main body; damped 1–3 cycles | 4–6 cycles | Lid rattles on its seat after the chest lands; coins keep rolling after the burst. |
| Slow in / slow out | Ease everything except impacts. Impacts: accelerate INTO contact (no ease-out) | — | `pow(k, 2.6–3.2)` into a slam; ease-out cubic out of a pop. Linear tweens are a bug. |
| Arcs | Translate along curves: spirals, parabolas, hops with tilt | — | Nothing travels in a straight line except light. |
| Secondary action | Small motion that supports the main one: glints, sparks, light pulses, camera thud | — | Must never upstage the primary action. |
| Timing | Heavy = slow start, fast hit, short settle. Light = quick, floaty, longer jitter | — | Drive mass from size³; heavy pieces bounce less, settle faster. |
| Exaggeration | 50% of "cartoon": overshoot 5–8% (lid opening to 1.075 then settling) | 15–25% | Exaggerate the *moment* (flash, thud), not the geometry. |
| Solid drawing | Rebuild has real volume, chamfers and believable proportions | — | Match the scan's proportions before animating. |
| Appeal | Clear silhouette, readable materials, a "hero" beat per sequence | — | One memorable moment per interaction (the snap, the seal). |

## Organic, weighty motion (not "perfectly lifting in one direction")

- **Never move on one axis only.** A hop gets roll *and* pitch, with different amplitudes and
  phases (e.g. roll 0.024 rad, pitch −0.010 rad rising; pitch swings +0.016 on the slam).
- **Tilt about a base edge, not the center.** Keep lifted corners above the floor:
  `lift = hop + halfWidth*|sin(roll)| + halfDepth*|sin(pitch)|`.
- **Land corner-first**, then rock across corners with a damped oscillation (2–3 visible
  wobbles, 100–170 ms period, decay ~100 ms).
- **Asymmetry and per-piece variation:** random delays (0–150 ms), random amplitudes
  (±30%), light vs heavy pieces behave differently. Use a seeded RNG for videos.
- **Weight = timing contrast:** slow wind-up, very fast action (≤ 200 ms for a slam), longer
  settle. A thud needs a 1–2 frame camera shake (h/v offset, ~1.5 cm, 110 ms decay).

## Implementation pattern

Write each beat as a **pure timeline function** `pose(t_ms) -> {values}`; never chain
tweens for hero beats. Benefits: deterministic (tests, Movie Maker), mirrorable between
GDScript and JS, and you can scrub it.

```js
// anticipation -> action -> overshoot -> settle (lid open), ~50% intensity
const bump = (t, a, b) => (t < a || t > b ? 0 : Math.sin(Math.PI * (t - a) / (b - a)));
function openTimeline(t) {
  const k = (a, b) => Math.min(1, Math.max(0, (t - a) / (b - a)));
  const env = bump(t, 0, 380) * 0.6 + bump(t, 540, 1010);           // two rattles (anticipation)
  const rock = env * 0.065 * Math.sin(2 * Math.PI * 7.5 * t / 1000);  // shake side to side
  let lid = 0;
  if (t > 380 && t < 1000) lid = (0.022 + 0.05 * k(380, 1000)) * Math.pow(Math.max(0, Math.sin(2 * Math.PI * (t - 380) / 165)), 0.7); // strains
  else if (t >= 1000 && t < 1200) lid = 1.075 * (1 - Math.pow(1 - k(1000, 1200), 3));   // snaps open, overshoots
  else if (t >= 1200) { const u = t - 1200; lid = 1 + 0.075 * Math.exp(-u / 120) * Math.cos(2 * Math.PI * 4.2 * u / 1000); } // settles
  return { lid, rock, lift: 0.5 * Math.abs(Math.sin(rock)) };
}
```

```js
// impact "seal": wind-up lift, accelerate into contact, hop + tilt, corner-first landing,
// squash, rock to rest, lid rattle (follow-through) — ≈50% intensity
lid  = T < 70 ? 1 + 0.035 * sin(π/2 · T/70)
     : T < 250 ? 1.035 · (1 − ((T−70)/180)^3.2)          // slam, no ease-out
     : 0.02·e^(−u/40)·|sin(πu/50)| + (T>330 ? 0.03·e^(−v/90)·|sin(πv/85)| : 0)
squash (after landing) = 1 − 0.04·e^(−u/45)·cos(2πu/130)
```

## Checklist before calling an animation done

- [ ] No linear interpolation anywhere a viewer can see it.
- [ ] Every big action has anticipation proportional to the dial.
- [ ] Impacts accelerate into contact and have a 1–3 frame "hit" (flash, shake, squash).
- [ ] Something overlaps/follows through after the main body stops.
- [ ] Motion has arcs and at least two rotation axes when something lifts.
- [ ] Heavy vs light reads from timing alone.
- [ ] At 50%: would a viewer call it "cartoony"? If yes, halve the amplitudes, keep the timing.
