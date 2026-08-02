// core.js
// ==== NAMESPACE ====
window.EXTROS = window.EXTROS || {};

// ==== TUNING ====
// Every balance number lives here. Nothing else in the codebase should
// contain a magic number for ball, paddle, AI, input, or loop behaviour.
EXTROS.tuning = {
  loop: {
    stepHz: 120,        // physics steps per second
    maxFrameDt: 0.25    // clamp real-world dt so a backgrounded tab can't teleport the ball
  },
  field: {
    marginPortraitAcross: 0.07,    // fraction of the short axis
    marginPortraitAlongTop: 0.15,
    marginPortraitAlongBottom: 0.14,
    marginLandscapeAcross: 0.045,
    marginLandscapeAlongTop: 0.155,
    marginLandscapeAlongBottom: 0.105
  },
  ball: {
    speed: 0.50,              // field-fractions per second; constant in phase 1, no escalation yet
    radius: 0.014,            // normalized along/across units
    launchAngleMaxDeg: 30,    // random serve spread from the along axis
    maxDeflectionDeg: 60,     // paddle-offset deflection clamp
    maxAngleFromAlongDeg: 75  // absolute clamp so the ball can never travel near-vertical
  },
  paddle: {
    length: 0.22,        // fraction of the across axis
    thickness: 0.016,    // fraction of the along axis
    playerA: 0.035,
    opponentA: 0.965
  },
  ai: {
    retargetIntervalMs: 180,        // how often the opponent re-reads the ball
    reactionLockMs: 120,            // won't reverse direction inside this window (human-like overshoot)
    maxSpeed: 1.35,                 // units/s the opponent paddle can move
    predictionErrorPerSpeed: 0.05,  // extra across-axis error, scaled by current ball speed
    missChance: 0.05                // chance a retarget goes to a random spot instead of the prediction
  },
  input: {
    touchSensitivity: 1.6,
    smoothingPerSecond: 12,
    keyboardAccel: 3.2,
    keyboardFriction: 8.0,
    keyboardMaxSpeed: 2.2
  },
  visual: {
    trailLifetimeMs: 120,
    ballGlowUnits: 1.9,
    ballHaloUnits: 3.2,
    cornerBracketUnits: 3.2
  }
};

// ==== CANVAS + LOOP ====
EXTROS.core = (function () {
  'use strict';

  var canvas, ctx, stage;
  var W = 0, H = 0, dpr = 1;
  var portrait = false;
  var fx = 0, fy = 0, fw = 0, fh = 0, u = 1;

  var last = 0;
  var acc = 0;
  var STEP = 1 / EXTROS.tuning.loop.stepHz;
  var running = true;
  var manualPause = false;

  var stats = {
    fps: 0, frameMs: 0, stepsThisFrame: 0,
    fpsAccum: 0, fpsFrames: 0
  };

  // ==== RESIZE ====
  // The only place canvas pixel geometry (and the portrait/landscape flag)
  // gets computed. Orientation-aware coordinate transforms live in draw.js.
  function resize() {
    var f = EXTROS.tuning.field;
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    var r = stage.getBoundingClientRect();
    W = Math.max(1, Math.floor(r.width));
    H = Math.max(1, Math.floor(r.height));
    canvas.width = Math.floor(W * dpr);
    canvas.height = Math.floor(H * dpr);
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    portrait = H > W;
    u = Math.min(W, H) / 100;

    var mx = portrait ? W * f.marginPortraitAcross : W * f.marginLandscapeAcross;
    var mt = portrait ? H * f.marginPortraitAlongTop : H * f.marginLandscapeAlongTop;
    var mb = portrait ? H * f.marginPortraitAlongBottom : H * f.marginLandscapeAlongBottom;
    fx = mx; fy = mt; fw = W - mx * 2; fh = H - mt - mb;
  }

  var resizeTimer = null;
  function scheduleResize() {
    // Android fires resize/orientationchange in bursts while bars animate.
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resize, 120);
  }

  // ==== VISIBILITY ====
  function onVisibilityChange() {
    running = !document.hidden;
    if (running) {
      last = performance.now();
      acc = 0;
    }
  }

  // ==== FRAME ====
  function frame(now) {
    requestAnimationFrame(frame);
    if (!running) { last = now; return; }

    var dt = Math.min((now - last) / 1000, EXTROS.tuning.loop.maxFrameDt);
    if (dt < 0) dt = 0;
    last = now;

    stats.frameMs = dt * 1000;
    stats.fpsAccum += dt;
    stats.fpsFrames++;
    if (stats.fpsAccum >= 0.5) {
      stats.fps = stats.fpsFrames / stats.fpsAccum;
      stats.fpsAccum = 0;
      stats.fpsFrames = 0;
    }

    stats.stepsThisFrame = 0;
    if (!manualPause) {
      acc += dt;
      while (acc >= STEP) {
        EXTROS.state.step(STEP);
        acc -= STEP;
        stats.stepsThisFrame++;
      }
    }

    EXTROS.draw.render(manualPause ? 1 : acc / STEP);
    if (EXTROS.debug && EXTROS.debug.afterRender) EXTROS.debug.afterRender();
  }

  function stepOnce() {
    EXTROS.state.step(STEP);
    stats.stepsThisFrame = 1;
    EXTROS.draw.render(1);
    if (EXTROS.debug && EXTROS.debug.afterRender) EXTROS.debug.afterRender();
  }

  function setManualPause(v) { manualPause = !!v; }
  function getManualPause() { return manualPause; }

  // ==== START ====
  function start() {
    canvas = document.getElementById('cv');
    stage = document.getElementById('stage');
    ctx = canvas.getContext('2d');

    window.addEventListener('resize', scheduleResize);
    window.addEventListener('orientationchange', scheduleResize);
    document.addEventListener('visibilitychange', onVisibilityChange);

    resize();
    EXTROS.state.reset();

    last = performance.now();
    requestAnimationFrame(frame);
  }

  return {
    start: start,
    stepOnce: stepOnce,
    setManualPause: setManualPause,
    getManualPause: getManualPause,
    getCanvas: function () { return canvas; },
    getCtx: function () { return ctx; },
    getStats: function () { return stats; },
    getField: function () {
      return { W: W, H: H, fx: fx, fy: fy, fw: fw, fh: fh, u: u, portrait: portrait };
    }
  };
})();
