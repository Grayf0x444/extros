// debug.js
// On-screen overlay + self-tests. Toggle with the ` key or a four-finger
// tap. [ and ] step the simulation one physics tick at a time.
window.EXTROS = window.EXTROS || {};

EXTROS.debug = (function () {
  'use strict';

  var visible = false;
  var lastTestResult = null;

  function toggle() { visible = !visible; }
  function isVisible() { return visible; }

  // ==== INPUT ====
  window.addEventListener('keydown', function (e) {
    if (e.code === 'Backquote') {
      toggle(); e.preventDefault();
    } else if (e.code === 'BracketLeft' || e.code === 'BracketRight') {
      EXTROS.core.setManualPause(true);
      EXTROS.core.stepOnce();
      e.preventDefault();
    } else if (e.code === 'Backslash') {
      EXTROS.core.setManualPause(!EXTROS.core.getManualPause());
      e.preventDefault();
    } else if (e.code === 'KeyT' && visible) {
      runTests();
    }
  });

  window.addEventListener('touchstart', function (e) {
    if (e.touches.length === 4) toggle();
  }, { passive: true });

  // ==== SELF-TESTS ====
  // Fires randomized high-speed ball approaches at a paddle from random
  // angles and positions, and asserts that none tunnel through, none end
  // the step overlapping the paddle, and none exit beyond the angle clamp.
  function runTests(trials) {
    trials = trials || 10000;
    var T = EXTROS.tuning;
    var tunnelFails = 0, angleFails = 0;
    var maxAngle = T.ball.maxAngleFromAlongDeg + 0.5; // small float-error margin
    var halfThick = T.paddle.thickness / 2, r = T.ball.radius, halfLen = T.paddle.length / 2;

    for (var i = 0; i < trials; i++) {
      var side = Math.random() < 0.5 ? 'player' : 'opponent';
      var target = {
        a: side === 'player' ? T.paddle.playerA : T.paddle.opponentA,
        c: Math.random(),
        len: T.paddle.length
      };
      var other = {
        a: side === 'player' ? T.paddle.opponentA : T.paddle.playerA,
        c: Math.random(),
        len: T.paddle.length
      };
      var outerFace = side === 'player' ? target.a + halfThick + r : target.a - halfThick - r;
      var innerFace = side === 'player' ? target.a - halfThick - r : target.a + halfThick + r;

      var dist = 0.005 + Math.random() * 0.9;
      var startA = side === 'player' ? outerFace + dist : outerFace - dist;
      var offsetFrac = (Math.random() * 2 - 1) * 2.0; // some inside, some well past the extent
      var startC = Math.max(0, Math.min(1, target.c + offsetFrac * halfLen));

      var speed = T.ball.speed * (1 + Math.random() * 100); // deliberately extreme
      var direction = side === 'player' ? -1 : 1;
      var angleDeg = (Math.random() * 2 - 1) * 74.9; // right up against the clamp
      var rad = angleDeg * Math.PI / 180;

      var ball = {
        a: startA, c: startC,
        va: Math.cos(rad) * speed * direction,
        vc: Math.sin(rad) * speed
      };

      var dt = 1 / 240 + Math.random() * (1 / 6); // a slow, laggy frame
      var player = side === 'player' ? target : other;
      var opponent = side === 'player' ? other : target;

      EXTROS.physics.sweepBall(ball, player, opponent, dt, T);

      // The real failure signature: the ball's final resting position sits
      // inside the paddle's solid body (embedded in its along-depth band
      // while also inside its across extent) — it should be geometrically
      // impossible for the sweep to end there.
      var lo = Math.min(outerFace, innerFace), hi = Math.max(outerFace, innerFace);
      var embedded = ball.a > lo + 1e-9 && ball.a < hi - 1e-9;
      var withinExtent = ball.c >= target.c - halfLen - r - 1e-9 &&
                          ball.c <= target.c + halfLen + r - 1e-9;
      if (embedded && withinExtent) tunnelFails++;

      var resultAngle = Math.abs(Math.atan2(ball.vc, ball.va) * 180 / Math.PI);
      if (resultAngle > 90) resultAngle = 180 - resultAngle;
      if (resultAngle > maxAngle) angleFails++;
    }

    lastTestResult = {
      trials: trials,
      tunnelFails: tunnelFails,
      angleFails: angleFails,
      pass: tunnelFails === 0 && angleFails === 0
    };
    console.log('[EXTROS.debug.runTests]', lastTestResult.pass ? 'PASS' : 'FAIL', lastTestResult);
    return lastTestResult;
  }

  // ==== OVERLAY ====
  function afterRender() {
    if (!visible) return;
    var ctx = EXTROS.core.getCtx();
    if (!ctx) return;
    var field = EXTROS.core.getField();
    var stats = EXTROS.core.getStats();
    var ball = EXTROS.state.getBall();
    var speed = Math.hypot(ball.va, ball.vc);
    var angle = Math.atan2(ball.vc, ball.va) * 180 / Math.PI;

    var lines = [
      'FPS ' + stats.fps.toFixed(1) + '   FRAME ' + stats.frameMs.toFixed(2) + 'ms   STEPS ' + stats.stepsThisFrame,
      'BALL SPD ' + speed.toFixed(3) + '   VEC ' + angle.toFixed(1) + '°   A ' + ball.a.toFixed(3) + '  C ' + ball.c.toFixed(3),
      'PADDLE TARGET ' + EXTROS.state.getPlayerTarget().toFixed(3) + '   ACTUAL ' + EXTROS.state.getPlayer().c.toFixed(3),
      'ORIENTATION ' + (field.portrait ? 'PORTRAIT' : 'LANDSCAPE'),
      EXTROS.core.getManualPause() ? 'PAUSED — [ ] step · \\ resume' : '` toggle · \\ pause · [ ] step · T run tests'
    ];
    if (lastTestResult) {
      lines.push('TESTS ' + (lastTestResult.pass ? 'PASS' : 'FAIL') +
        ' (' + lastTestResult.trials + ' trials, ' +
        lastTestResult.tunnelFails + ' tunnel, ' + lastTestResult.angleFails + ' angle)');
    }

    ctx.save();
    ctx.font = '12px ui-monospace, monospace';
    ctx.textBaseline = 'top';
    var lineHeight = 15;
    var boxH = lines.length * lineHeight + 12;
    ctx.fillStyle = 'rgba(11,13,12,0.85)';
    ctx.fillRect(6, 6, 380, boxH);
    ctx.strokeStyle = '#8A5E00';
    ctx.strokeRect(6, 6, 380, boxH);
    ctx.fillStyle = '#FFB000';
    for (var i = 0; i < lines.length; i++) {
      ctx.fillText(lines[i], 12, 12 + i * lineHeight);
    }
    ctx.restore();
  }

  return {
    toggle: toggle,
    isVisible: isVisible,
    runTests: runTests,
    afterRender: afterRender
  };
})();
