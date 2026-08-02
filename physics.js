// physics.js
// Swept collision, angle-based reflection, and clamping. Pure functions —
// everything needed is passed in, nothing is read from the DOM or canvas.
window.EXTROS = window.EXTROS || {};

EXTROS.physics = (function () {
  'use strict';

  var MAX_ITERATIONS = 64;
  var EPS = 1e-6;

  // ==== ANGLE HELPERS ====
  function degToRad(d) { return d * Math.PI / 180; }

  /**
   * Rebuilds a velocity vector from an angle (measured from the along axis)
   * and a speed, then clamps the angle so the resulting path can never
   * exceed tuning.ball.maxAngleFromAlongDeg — a ball ping-ponging wall to
   * wall is dead time.
   * @param {number} angleDeg
   * @param {number} speed
   * @param {number} direction +1 toward the opponent, -1 toward the player
   * @param {object} tuning
   */
  function velocityFromAngle(angleDeg, speed, direction, tuning) {
    var max = tuning.ball.maxAngleFromAlongDeg;
    var clamped = Math.max(-max, Math.min(max, angleDeg));
    var rad = degToRad(clamped);
    return {
      va: Math.cos(rad) * speed * direction,
      vc: Math.sin(rad) * speed
    };
  }

  /**
   * Reflects the ball off a paddle. Speed is taken from the ball's current
   * velocity (never touched directly) and direction/angle are rebuilt from
   * the normalized contact offset — speed and direction stay independent.
   * @param {{va:number, vc:number}} ball
   * @param {number} direction +1 off the player paddle, -1 off the opponent
   * @param {number} offset contact offset from paddle centre, -1..1
   * @param {object} tuning
   */
  function reflectOffPaddle(ball, direction, offset, tuning) {
    var speed = Math.hypot(ball.va, ball.vc);
    var clampedOffset = Math.max(-1, Math.min(1, offset));
    var angleDeg = clampedOffset * tuning.ball.maxDeflectionDeg;
    var v = velocityFromAngle(angleDeg, speed, direction, tuning);
    ball.va = v.va;
    ball.vc = v.vc;
  }

  function reflectOffWall(ball) {
    ball.vc = -ball.vc;
  }

  function clampPaddleC(c, len) {
    var half = len / 2;
    if (half >= 0.5) return 0.5;
    return Math.max(half, Math.min(1 - half, c));
  }

  // ==== SWEEP ====
  /**
   * Advances `ball` through `dt`, resolving any number of wall/paddle
   * collisions within the step. Never uses an overlap test: each candidate
   * is the exact time the ball's leading edge (inflated by its radius)
   * enters a collision volume, found via slab intersection on the along
   * and across axes together — so a ball skimming the very corner of a
   * paddle at high speed still registers a hit instead of slipping through
   * the gap between "plane crossed" and "extent checked". After a
   * collision the ball is snapped to the exact contact surface, so it can
   * never end the step overlapping.
   * @param {{a:number,c:number,va:number,vc:number}} ball
   * @param {{a:number,c:number,len:number}} player
   * @param {{a:number,c:number,len:number}} opponent
   * @param {number} dt
   * @param {object} tuning
   * @returns {'player'|'opponent'|null} which side the ball exited without
   *   being intercepted this step, or null if it didn't exit.
   */
  function sweepBall(ball, player, opponent, dt, tuning) {
    var remaining = dt;
    var r = tuning.ball.radius;
    var halfLen = tuning.paddle.length / 2;
    var halfThick = tuning.paddle.thickness / 2;
    var iterations = 0;
    var best;

    function candidate(t, type, viaAcross) {
      if (t === null || t === undefined || isNaN(t)) return;
      if (t < -EPS || t > remaining) return;
      if (t < 0) t = 0;
      if (!best || t < best.t) best = { t: t, type: type, viaAcross: viaAcross };
    }

    // Swept ball vs the paddle's (radius-inflated) rectangle, via slab
    // intersection: the ball is inside the collision volume only once it
    // has entered both the along-slab and across-slab, so the entry time
    // is the later of the two individual entry times, and a real overlap
    // only exists if that's still before either slab's exit time.
    function paddleEntry(paddle, outerFace, innerFace) {
      var cMin = paddle.c - halfLen - r, cMax = paddle.c + halfLen + r;
      var tEnterA = (outerFace - ball.a) / ball.va;
      var tExitA = (innerFace - ball.a) / ball.va;
      var tEnterC, tExitC;
      if (ball.vc > 0) {
        tEnterC = (cMin - ball.c) / ball.vc;
        tExitC = (cMax - ball.c) / ball.vc;
      } else if (ball.vc < 0) {
        tEnterC = (cMax - ball.c) / ball.vc;
        tExitC = (cMin - ball.c) / ball.vc;
      } else if (ball.c >= cMin && ball.c <= cMax) {
        tEnterC = -Infinity; tExitC = Infinity;
      } else {
        return null;
      }
      var tEnter = Math.max(tEnterA, tEnterC);
      var tExit = Math.min(tExitA, tExitC);
      if (tEnter > tExit + EPS) return null;
      return { t: Math.max(0, tEnter), viaAcross: tEnterC > tEnterA };
    }

    function resolvePaddleHit(paddle, outerFace, direction, viaAcross) {
      if (viaAcross) {
        // Grazed the side edge rather than the face — reflect like a wall.
        ball.c = ball.vc > 0 ? paddle.c - halfLen - r : paddle.c + halfLen + r;
        reflectOffWall(ball);
      } else {
        ball.a = outerFace;
        reflectOffPaddle(ball, direction, (ball.c - paddle.c) / halfLen, tuning);
      }
    }

    while (remaining > EPS && iterations < MAX_ITERATIONS) {
      iterations++;
      best = null;

      // -- across walls --
      if (ball.vc < 0) {
        candidate((r - ball.c) / ball.vc, 'wallTop');
      } else if (ball.vc > 0) {
        candidate((1 - r - ball.c) / ball.vc, 'wallBottom');
      }

      // -- player paddle, near along = 0 --
      // Gate on the inner face, not the outer one: a wall bounce earlier
      // in this same sweep can carry the ball's along-position past the
      // outer face (while it was out of across-range and so didn't
      // collide) and into the depth band itself, where it can still clip
      // the paddle's side on its way back through.
      if (ball.va < 0) {
        var pOuter = player.a + halfThick + r, pInner = player.a - halfThick - r;
        if (ball.a > pInner) {
          var pe = paddleEntry(player, pOuter, pInner);
          if (pe) candidate(pe.t, 'player', pe.viaAcross);
        }
      }

      // -- opponent paddle, near along = 1 --
      if (ball.va > 0) {
        var oOuter = opponent.a - halfThick - r, oInner = opponent.a + halfThick + r;
        if (ball.a < oInner) {
          var oe = paddleEntry(opponent, oOuter, oInner);
          if (oe) candidate(oe.t, 'opponent', oe.viaAcross);
        }
      }

      if (!best) {
        ball.a += ball.va * remaining;
        ball.c += ball.vc * remaining;
        remaining = 0;
        break;
      }

      ball.a += ball.va * best.t;
      ball.c += ball.vc * best.t;
      remaining -= best.t;

      if (best.type === 'wallTop') {
        ball.c = r;
        reflectOffWall(ball);
      } else if (best.type === 'wallBottom') {
        ball.c = 1 - r;
        reflectOffWall(ball);
      } else if (best.type === 'player') {
        resolvePaddleHit(player, player.a + halfThick + r, 1, best.viaAcross);
      } else {
        resolvePaddleHit(opponent, opponent.a - halfThick - r, -1, best.viaAcross);
      }
    }

    if (ball.a < 0) return 'player';
    if (ball.a > 1) return 'opponent';
    return null;
  }

  return {
    sweepBall: sweepBall,
    reflectOffPaddle: reflectOffPaddle,
    reflectOffWall: reflectOffWall,
    velocityFromAngle: velocityFromAngle,
    clampPaddleC: clampPaddleC
  };
})();
