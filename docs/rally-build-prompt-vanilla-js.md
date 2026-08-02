# Build Prompt: "EXTROS" — vanilla JS Pong roguelite, built entirely on Android

> Paste this into your coding agent as the brief.
> **Hard constraint: this project is written and tested on a Galaxy S25 using SPCK Editor and Pydroid 3.
> There is no Node.js, no npm, no bundler, no TypeScript, and no terminal. Every instruction below
> assumes a file must run by opening `index.html` in a browser with zero build steps.**

---

## 1. What we're building

A single-screen Pong variant for the browser. Instant load, no account, a run lasts 60–120 seconds
and ends in a score. Built for someone standing on a train with one hand free, or hiding a tab at work.

The design rule for every system: **give the player a decision, then reward the good one.** Random
things happening *to* you is not fun.

**Framing:** the player is aboard a station running a containment exercise against a system that keeps
adapting to them. The name comes from *extropy* — the tendency of a system to grow more organized and
more capable over time — which is exactly what the opponent does across a run, and exactly what the
player is racing. Everything on screen is instrumentation, not scenery. Full art direction in §12.

---

## 2. Stack — no build step, ever

- **Plain JavaScript (ES2020), HTML5 Canvas 2D.** No TypeScript, no JSX, no framework, no bundler.
- **Classic `<script>` tags in dependency order.** Do **not** use ES modules or `import` — those fail
  under `file://` and add a server dependency for no benefit here.
- **One global namespace object**, `RALLY`, declared in the first script. Every file attaches to it:
  ```js
  // physics.js
  RALLY.physics = (function () {
    'use strict';
    function sweepBallVsPaddle(ball, paddle, dt) { /* ... */ }
    return { sweepBallVsPaddle: sweepBallVsPaddle };
  })();
  ```
  This gives module-style separation with zero tooling, and each file stays independently openable.
- **Types via JSDoc comments**, not TypeScript. Free documentation, zero build:
  ```js
  /** @param {{x:number, y:number, vx:number, vy:number, r:number}} ball */
  ```
- Web Audio API, sounds generated from oscillators and noise. **No audio files.**
- `localStorage` for best score. No backend in v1.
- Everything in one flat folder. No subdirectories — nested navigation on a phone is friction.

### File layout
```
index.html          // all <script> tags, in order, plus the canvas
style.css           // ~30 lines: full-bleed canvas, touch-action:none
core.js             // RALLY namespace, constants, the game loop
input.js            // touch + keyboard + mouse, normalized
state.js            // pure game state, no drawing
physics.js          // swept collision, reflection, clamping
opponents.js        // the AI variants
powerups.js
draw.js             // all canvas rendering
fx.js               // particles, shake, hit-stop
audio.js
debug.js            // on-screen overlay + self-tests (see §7)
```

**Keep every file under ~350 lines.** Scrolling a 1,500-line file on a phone is the single biggest
drag on this project. When a file gets long, split it. Inside each file, use banner comments so
SPCK's find can jump you straight there:
```js
// ==== COLLISION ====
```

---

## 3. Fix these first — real bugs carried over from the pygame prototype

### 3.1 Frame-rate-dependent physics (critical)
The prototype moves in `px per frame` and calls `clock.tick(60)`. Your S25 display runs at 120 Hz —
the game would run at literal double speed, and slower again when the browser throttles.

**Fix:** all velocities in **units per second**. Fixed-timestep accumulator:
```js
var acc = 0, STEP = 1 / 120;
function frame(now) {
  var dt = Math.min((now - last) / 1000, 0.25); // clamp: backgrounded tabs
  last = now; acc += dt;
  while (acc >= STEP) { RALLY.state.step(STEP); acc -= STEP; }
  RALLY.draw.render(acc / STEP); // interpolate
  requestAnimationFrame(frame);
}
```
The 0.25 clamp matters a lot on Android — lock the phone mid-rally and the ball would otherwise
teleport through a paddle on resume.

### 3.2 Tunneling through paddles
`ball.colliderect(paddle)` is a discrete overlap test. With the FAST modifier at 1.8× and a paddle
`WIDTH/60` thick, a fast ball jumps clean past it between frames. Players read this as cheating.

**Fix:** swept collision — solve for the time the moving ball crosses the paddle's plane within the
step, resolve at that contact point. Never rely on overlap alone.

### 3.3 The ball sticks in walls and paddles
`if ball.top <= 0: ball_dy *= -1` — overshoot deep into the wall and it's still `<= 0` next frame, so
it flips again and jitters. Same class of bug on paddles: no reposition after contact, so a GIANT ball
overlapping a paddle re-triggers `apply_modifier()` on consecutive frames.

**Fix:** on every collision, reflect the velocity **and** snap the ball to the exact contact surface.
Add a 2-step collision lockout per paddle.

### 3.4 Unbounded, floor-divided spin
`ball_dy += (ball.centery - player.centery) // 10` accumulates forever and biases negative.

**Fix:** don't touch `dy` directly. Take the contact offset normalized to −1..1, map to a deflection
of ±60° from horizontal, rebuild the velocity from `(angle, currentSpeed)`. Speed and direction become
independent. Clamp so the ball can never exceed 75° — a ball ping-ponging between walls is dead time.

### 3.5 The AI is a perfect tracker
The comment claims a randomized delay, but there is none — it moves toward `ball.centery` every frame.
It only loses to a ball faster than it can move, which is a speed check, not difficulty.

**Fix:** model it as a player. Re-target only every 180 ms (down to 60 ms at high tiers). Predict the
landing point with wall bounces, then add error proportional to ball speed. Once moving, don't reverse
for 120 ms — human-like overshoot. At low tiers, an explicit miss chance, so a new player scores inside
the first 20 seconds.

### 3.6 Modifiers reset the ball to base speed on every hit
`apply_modifier()` recalculates from `BASE_BALL_SPEED_*`, so a 30-hit rally feels identical to the
first hit. **This is the single biggest reason the prototype isn't fun yet.** See §4.1.

### 3.7 GHOST punishes without teaching
`(30,30,40)` on a `(12,12,18)` background is an invisible ball. The player misses because the game hid
it, not because they were outplayed. Redesigned in §4.3.

### 3.8 Smaller items
- Trail is a fixed 12 entries → make it time-based (last 120 ms) so it looks the same at any FPS.
- Shake `randint(-10,10)` is unscaled and doesn't decay. Use a `trauma` float decaying linearly with
  offset = `trauma² × maxOffset`. The squared falloff is what makes it read as impact, not vibration.
- Fullscreen `(0,0)` → responsive canvas, re-derive all sizes on resize (§5.6).
- Pause on `visibilitychange`. Android backgrounds tabs aggressively.

---

## 4. The fun

### 4.1 Rally escalation is the core loop
- Every paddle contact multiplies ball speed by **1.04**, capped at 3.2×.
- **Score is rally length, not points.** The counter is the biggest thing on screen.
- 3 lives. A miss drops speed back to 1.4× — a punishment that's also a breather.
- One `intensity` value derived from ball speed drives background, audio pitch, and shake together.

### 4.2 Contact zones — a skill ceiling
| Zone | Result |
|---|---|
| Center 40% | Safe return, shallow angle |
| Outer bands | Sharp angle, 1.5× speed spike, **+2** |
| Outermost 8% ("EDGE") | 200 ms slow-mo, flash, **+5**, opponent stunned 300 ms |

Draw the bands on the paddle so the skill is learnable by looking.

### 4.3 Powerups become targets, not dice rolls
Delete the 35% random roll. **Orbs drift in the play field and you earn the modifier by aiming the
ball into one.** Same effects, now a choice. One at a time, 8-second duration, HUD ring showing decay.

| Orb | Effect |
|---|---|
| **SURGE** | +60% speed, +50% score rate — a risk you chose |
| **DRIFT** | −40% speed for 4 s — a rescue when you're drowning |
| **HEAVY** | Ball doubles in size and cracks the opponent's paddle on hit |
| **PHASE** | Ball turns translucent and passes *through* the opponent's paddle once. (Was GHOST — invisibility punished the player; phasing punishes the opponent. Same fantasy, inverted.) |
| **SPLIT** | Second ball for 6 s, both score |

### 4.4 One active verb: CHARGE
Hold anywhere (touch) or Space/Shift (keyboard). Paddle glows and **moves at 60% speed while charging**
— that's the cost. Release on contact = SLAM: 1.8× speed, hit-stop, particle burst. 3-second cooldown
drawn as a fill on the paddle itself, not a separate HUD element.

Now the player decides *when to trade mobility for power*, every rally.

### 4.5 Opponent gauntlet — progression inside one run
The opponent changes every 8 rally hits, announced as a **contact classification** stamped across the
readout, with a palette shift. **Build four for v1**, loop with rising speed:

1. **SENTINEL** — slow, forgiving. The tutorial you don't have to write.
2. **BINARY** — two half-height paddles with a gap. Aim for the seam.
3. **PHASE DRIVE** — teleports instead of moving, but only every 400 ms. Bait the jump.
4. **BULKHEAD** — full-height plate that shrinks 12% each time you hit it. Pure endurance.

One readable gimmick, one readable counter. That's the whole rule. (MIRROR and MAGNET, renamed to
**ECHO** and **GRAVITY WELL**, are good phase-4 additions.)

Each classification gets a one-line threat readout on its name card — "CONTACT: BINARY / TWO EMITTERS /
SEAM AT 0.5" — which doubles as the tutorial. Telling the player the counter is not a spoiler; executing
it under speed is the game.

### 4.6 Runs must end
Three misses, plus a soft timer: after 90 seconds the walls close in.

### 4.7 The death screen is the retention screen
Score, best, and **one specific line** — "4 short of your best", "New best by 12". Restart responds to
tap anywhere, Space, and Enter. Death to next ball in play in under 2 seconds.

---

## 5. Controls — both schemes, always live

One input layer emits `{ target: 0..1, charging: bool, confirm: bool }` per frame. Game logic never
knows the device. **No mode picker, no device-selection screen** — detect the *last used* input and
change only the on-screen hints.

### 5.1 Portrait: rotate the whole arena
A horizontal court on a 9:16 screen gives a narrow field, a huge amount of paddle travel, and puts the
thumb directly on top of the ball.

**In portrait, rotate 90°: player paddle at the bottom, opponent at the top, sliding left–right.** The
thumb rests at the bottom edge blocking nothing, travel matches a thumb's natural arc, and the ball
approaches toward the player, which reads better than side-on.

Write all game logic against abstract `along` / `across` axes so this is one transform at draw time,
not two codebases. Landscape (DeX, phone turned sideways) keeps the classic left/right layout.

### 5.2 Touch
- **Relative drag with offset capture.** On `touchstart`, store `touchY - paddleY` and hold that offset
  for the gesture. The paddle must **never teleport** to the finger — the prototype's
  `player.centery = event.pos[1]` snap feels broken on a phone.
- ~1.6× sensitivity so a short thumb swipe crosses the court.
- Smooth toward the target exponentially (~12/s) so jitter doesn't transfer.
- **Hold without dragging = charge.**
- `touch-action: none` on the canvas plus `overscroll-behavior: none` on body — otherwise Samsung
  Internet and Chrome will pull-to-refresh mid-rally. This will bite you; set it in phase 1.
- Track only the first active touch, ignore the rest.
- `navigator.vibrate(8)` on contact — works well on the S25, guard it for browsers that lack it.

### 5.3 Keyboard (your DeX setup is the test rig)
- **W/S** and **↑/↓** both, always. In a rotated field, **A/D** and **←/→**.
- Movement is **velocity-based**, not position-based: keydown applies acceleration, keyup applies
  friction. This is what makes desktop feel weighty rather than like a laggy mouse.
- **Space/Shift** charge, **Esc/P** pause, **R** restart.
- `preventDefault` on the game's keys only, so arrows and space never scroll the page.

### 5.4 Mouse
Position tracking with the same smoothing. Left button held = charge.

### 5.5 You can test both schemes on one device
This is the quiet advantage of your setup: **docked in DeX with a keyboard and mouse is your desktop
test, and undocking the phone is your mobile test — same build, same browser engine, two minutes
apart.** Most developers have to emulate one of those. Run both before every commit, and rotate the
phone to check the portrait transform.

### 5.6 Canvas sizing
```js
function resize() {
  var dpr = Math.min(window.devicePixelRatio || 1, 2); // cap at 2: the S25 is ~3x, uncapped kills fps
  cv.width  = Math.floor(innerWidth  * dpr);
  cv.height = Math.floor(innerHeight * dpr);
  cv.style.width = innerWidth + 'px';
  cv.style.height = innerHeight + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  RALLY.state.setOrientation(innerHeight > innerWidth ? 'portrait' : 'landscape');
}
```
Listen to `resize` and `orientationchange`, and debounce — Android fires these in bursts as the
keyboard and system bars animate.

---

## 6. Juice

Keep every effect **readable**. Nothing may ever obscure the ball.

- **Hit-stop:** freeze the simulation 40–90 ms on contact, scaled by impact speed. Highest
  value-per-line-of-code effect in the whole game. **Do this one first.**
- **Squash and stretch:** scale the ball along its velocity vector up to 1.4× at speed; compress
  against the paddle for 60 ms on contact.
- **Trail:** time-based, tapering width and alpha, tinted by the active modifier.
- **Particles:** 8–14 sparks along the reflection normal, with gravity and drag. Pool the objects —
  allocating per-frame will trigger GC stutter on mobile.
- **Paddle recoil:** compress 15% and spring back over 150 ms.
- **Shake:** trauma-based, squared falloff, capped.
- **Audio:** pitch the paddle blip up with rally length. The rising pitch communicates escalation
  better than any HUD element. **Muted by default** with an obvious unmute — office players — and the
  game must be fully legible with sound off.
- **`prefers-reduced-motion`:** kill shake and speed lines, keep hit-stop and color.

---

## 7. Debugging without DevTools

You have no desktop inspector, so build the instrumentation into the game. This is a phase-1 task,
not an afterthought.

- **`debug.js` overlay**, toggled by the `~` key or a 4-finger tap: FPS, frame time, step count,
  ball speed and angle, active modifier, opponent tier, particle count, live `dt`.
- **Add [Eruda](https://github.com/liriliri/eruda) behind a URL flag** — a full console, network panel,
  and element inspector that runs on the page itself. One script tag, loaded only when `?debug=1` is
  present so it never ships to players:
  ```html
  <script>
    if (location.search.indexOf('debug=1') > -1) {
      var s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/eruda';
      s.onload = function () { eruda.init(); };
      document.head.appendChild(s);
    }
  </script>
  ```
  This is the closest thing to Chrome DevTools you'll get on-device, and it's genuinely good.
- **Self-tests as a plain function**, not a test framework. `RALLY.debug.runTests()` fires 10,000
  randomized high-speed ball approaches at a paddle and asserts none pass through, then prints
  pass/fail to the overlay. Call it from the debug menu. No npm required for any of this.
- **Slow-motion and step-frame keys** (`[` and `]`) so you can watch a collision resolve one step at a
  time. You will need this for the swept-collision work.

---

## 8. Where Pydroid still earns its place

Don't maintain two versions of the game — that's double the work and they'll drift apart. But Pydroid
is genuinely faster than the browser for **tuning numbers**:

- Plot the rally speed curve (`1.04^n`, capped) and check when it becomes unplayable, before you feel
  it in-game.
- Simulate the AI's prediction error model across a few thousand rallies to find the miss rate per tier.
- Work out the deflection-angle mapping and confirm it never produces a near-vertical result.

Use it as a **maths scratchpad**, then port the constants across as a single `RALLY.tuning = {...}`
object in `core.js` so all balance lives in one editable place.

---

## 9. Shipping from the phone

- SPCK Editor has git built in — commit and push to a GitHub repo, enable **GitHub Pages** on the
  `main` branch. That's a live HTTPS URL with no terminal, no CI, and no deploy tooling.
- HTTPS is required anyway for `navigator.vibrate` and for a service worker later.
- For an `.io`-style audience, also zip the folder and upload to **itch.io** as an HTML5 game — that
  gets you actual players and feedback for free, and the upload flow works in a mobile browser.
- Offline support (phase 4) is one small `sw.js` with a cache-first fetch handler. Worth it: your
  players are on trains.

---

## 10. Acceptance criteria

- [ ] Identical game speed at 60 Hz and at the S25's 120 Hz.
- [ ] `runTests()` reports zero tunneling across 10,000 high-speed approaches.
- [ ] The ball never sticks in a wall or paddle, and never travels near-vertically.
- [ ] Playable one-handed in portrait with the thumb never covering the ball.
- [ ] Playable start to finish on keyboard alone in DeX, including restart.
- [ ] Switching between touch and keyboard mid-run causes no glitch and no prompt.
- [ ] No pull-to-refresh, no text selection, no zoom on double-tap.
- [ ] A first-time player scores within 20 seconds.
- [ ] Death to next ball in play in under 2 seconds.
- [ ] Locking the phone mid-rally and returning does not lose or teleport the ball.
- [ ] Loads and plays with no network connection after first visit (phase 4).

---

## 11. Build order

**Phase 1 — the port.** Fixed timestep, swept collision, angle-based reflection, responsive canvas,
input layer with touch + keyboard, portrait rotation, debug overlay. No new features. The result is a
boring but flawless Pong. **Do not skip this phase.**

**Phase 2 — the loop.** Rally escalation, 3 lives, contact zones, charge/slam, death screen, best score.
**Playtest here.** If it isn't fun with zero powerups, no powerup will save it.

**Phase 3 — content and juice.** Powerup orbs, the four opponents, hit-stop, particles, audio.

**Phase 4 — retention.** Daily seeded run, share card, service worker, two more opponents, ghost
replay of your best run as a faint second paddle.

**Out of scope for v1:** accounts, real-time multiplayer, monetization, tutorials, cosmetics, settings
beyond mute and reduced motion.

---

## 12. Art direction — "AMBER TELEMETRY"

### The trap to avoid
"Futuristic space" defaults to purple nebulae, neon grids, glowing cyan, and lens flare. That is the
same look every generated arcade prototype arrives in, and it's why the current prototype reads as a
tech demo rather than a product. The way out is to **render the instrumentation, not the vista.** The
player isn't looking out of a window. They're looking at the panel that tells them what's out there.

This is also the cheap option, which matters on your toolchain: it's all strokes, rects, and monospace
text. No sprites, no image files, no asset pipeline, no load time.

### The concept
The entire screen is a single amber phosphor CRT readout on a station's defense console. The court is a
containment field diagram. The paddles are emitters. The ball is a tracked contact with a live vector.
Everything the game needs to communicate — speed, angle, lives, cooldown — is presented as a real
instrument would present it, because that's how a console *would* show it.

### Tokens
| Role | Hex | Use |
|---|---|---|
| Void | `#0B0D0C` | Background, everything sits on this |
| Phosphor | `#FFB000` | Primary amber — court lines, paddles, text |
| Phosphor dim | `#8A5E00` | Grid, inactive UI, decayed trails |
| Burn | `#FFE9B8` | Hot core of the ball, peak-impact flash |
| Alert | `#FF3B1F` | Life loss, redline, hull warnings |
| Cold | `#4FD1C5` | The opponent — **the only non-amber element in the game** |

That last row is the whole palette discipline. One color that isn't yours, and it belongs to the thing
trying to beat you. Every other pixel is warm. Restraint here is what makes the opponent read as alien
without a single extra effect.

**Type:** one monospace face for everything (system-ui monospace stack — no webfont, no load). Score in
a large tabular readout with leading zeros: `RALLY 0047`. Labels in small uppercase with wide tracking.

### Signature: the readout degrades under load
This is the one memorable thing. Tie it directly to the `intensity` value from §4.1:

- **Low intensity:** clean panel. A dotted trajectory line predicts where the ball will land, with
  reflections off the walls calculated ahead. Telemetry text along the edge is legible and stable —
  `VEL 412 M/S · VEC 038° · CONTACT SENTINEL · INTEGRITY 3`.
- **Rising:** phosphor persistence lengthens, so the ball smears (this *is* your trail effect, now
  justified by the fiction). Scanlines start to roll. The predicted trajectory gets shorter — the
  console can no longer compute far enough ahead.
- **High:** the prediction line **fails entirely**. Telemetry starts dropping characters mid-word.
  Horizontal tear lines rip across the panel on impacts. The score readout flickers between frames.
- **Redline:** the phosphor blooms to `#FFE9B8` and the panel briefly whites out on every hit.

The escalation is legible without a tutorial and it removes UI exactly when the player needs to rely on
reflex instead of information. Difficulty and art direction doing the same job is the goal.

### How each existing element maps
- **Court:** not a solid border. A dotted containment boundary with corner brackets, plus a faint
  measurement grid. The center line becomes a range scale with tick marks.
- **Paddles:** hollow rectangles with a bright inner bar showing charge state (§4.4). Contact zones
  from §4.2 are drawn as segment divisions, brighter at the EDGE bands.
- **Ball:** a hot `#FFE9B8` core with an amber halo and a short vector line pointing where it's going.
  Under PHASE, the fill drops out and only the outline remains.
- **Powerup orbs:** targeting reticles that lock on with corner brackets as the ball nears — a small
  detail that makes aiming for them feel deliberate.
- **Lives:** three `INTEGRITY` bars that don't just disappear when lost. They short out, flicker, and
  go dark, with an alert-red pulse across the whole panel.
- **Death screen:** an incident report. `CONTAINMENT FAILED · RALLY 0047 · BEST 0059 · 12 SHORT`.

### The risk worth taking
On the final life, drop the amber almost entirely: the panel goes to emergency red, the grid dies, the
telemetry cuts to a single line, and the ball becomes the brightest object on screen by a wide margin.
The player should feel the console give up on being informative and start just trying to keep them
alive. It costs one palette swap and it will be the thing people remember.

### Non-negotiable
Nothing above may obscure the ball — if scanlines, bloom, or tear lines ever hide it, cut them. All
degradation effects are disabled under `prefers-reduced-motion`; keep the color and the hit-stop.
