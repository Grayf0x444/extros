// state.js
// Pure game state and step(). No canvas calls anywhere in this file, and no
// portrait/landscape checks — game logic only knows abstract along/across.
window.EXTROS = window.EXTROS || {};

EXTROS.state = (function () {
  'use strict';

  var T = EXTROS.tuning;

  var ball = { a: 0.5, c: 0.5, va: 0, vc: 0 };
  var prevBall = { a: 0.5, c: 0.5 };

  var player = { a: T.paddle.playerA, c: 0.5, len: T.paddle.length };
  var opponent = { a: T.paddle.opponentA, c: 0.5, len: T.paddle.length };

  var ai = {
    targetC: 0.5,
    timeSinceRetargetMs: 999,
    lastDir: 0,
    lockTimerMs: 0
  };

  var playerTarget = 0.5; // last raw input target, exposed for the debug overlay

  // ==== SERVE ====
  function serve() {
    ball.a = 0.5;
    ball.c = 0.5;
    var direction = Math.random() < 0.5 ? -1 : 1;
    var angleDeg = (Math.random() * 2 - 1) * T.ball.launchAngleMaxDeg;
    var rad = angleDeg * Math.PI / 180;
    ball.va = Math.cos(rad) * T.ball.speed * direction;
    ball.vc = Math.sin(rad) * T.ball.speed;
    prevBall.a = ball.a;
    prevBall.c = ball.c;
  }

  function reset() {
    player.c = 0.5;
    opponent.c = 0.5;
    ai.timeSinceRetargetMs = 999;
    ai.lastDir = 0;
    ai.lockTimerMs = 0;
    serve();
  }

  // ==== PLAYER PADDLE ====
  // Game state never learns which device produced the input — it only
  // consumes the normalized {target, charging, confirm} contract.
  function updatePlayer(dt) {
    if (typeof EXTROS.input === 'undefined') return;
    EXTROS.input.update(dt);
    var s = EXTROS.input.getState();
    playerTarget = s.target;
    player.c = EXTROS.physics.clampPaddleC(playerTarget, player.len);
  }

  // ==== OPPONENT AI ====
  // Predicts the ball's landing across-position (including wall bounces),
  // then re-targets on an interval and adds error proportional to ball
  // speed — a basic tracker, not a perfect one.
  function predictLanding() {
    var a = ball.a, c = ball.c, va = ball.va, vc = ball.vc;
    if (va <= 0) return opponent.c; // ball moving away — hold position
    var guard = 0;
    while (guard++ < 16) {
      var tA = (opponent.a - a) / va;
      var tC = vc > 0 ? (1 - c) / vc : (vc < 0 ? (0 - c) / vc : Infinity);
      if (tC < tA) {
        a += va * tC; c += vc * tC; vc = -vc;
      } else {
        a += va * tA; c += vc * tA;
        break;
      }
    }
    return c;
  }

  function updateAI(dt) {
    ai.timeSinceRetargetMs += dt * 1000;
    if (ai.timeSinceRetargetMs >= T.ai.retargetIntervalMs) {
      ai.timeSinceRetargetMs = 0;
      var missed = Math.random() < T.ai.missChance;
      if (missed) {
        ai.targetC = Math.random();
      } else {
        var landing = predictLanding();
        var speed = Math.hypot(ball.va, ball.vc);
        var error = (Math.random() * 2 - 1) * T.ai.predictionErrorPerSpeed * speed;
        ai.targetC = Math.max(0, Math.min(1, landing + error));
      }
    }

    if (ai.lockTimerMs > 0) ai.lockTimerMs -= dt * 1000;

    var delta = ai.targetC - opponent.c;
    var dir = delta > 0 ? 1 : delta < 0 ? -1 : 0;
    if (dir !== 0 && ai.lastDir !== 0 && dir !== ai.lastDir && ai.lockTimerMs > 0) {
      dir = ai.lastDir; // human-like overshoot: don't reverse mid-correction
    }
    if (dir !== ai.lastDir && dir !== 0) ai.lockTimerMs = T.ai.reactionLockMs;
    ai.lastDir = dir;

    var maxStep = T.ai.maxSpeed * dt;
    var step = Math.max(-maxStep, Math.min(maxStep, delta));
    opponent.c = EXTROS.physics.clampPaddleC(opponent.c + step, opponent.len);
  }

  // ==== STEP ====
  function step(dt) {
    prevBall.a = ball.a;
    prevBall.c = ball.c;

    updatePlayer(dt);
    updateAI(dt);

    var exited = EXTROS.physics.sweepBall(ball, player, opponent, dt, T);
    if (exited) serve();
  }

  return {
    reset: reset,
    step: step,
    getBall: function () { return ball; },
    getPrevBall: function () { return prevBall; },
    getPlayer: function () { return player; },
    getOpponent: function () { return opponent; },
    getPlayerTarget: function () { return playerTarget; }
  };
})();
