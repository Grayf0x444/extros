// draw.js
// All rendering. This is the one file that knows about portrait vs
// landscape — pt() is the sole along/across-to-pixel transform in the
// codebase; everything else works in abstract 0..1 field coordinates.
window.EXTROS = window.EXTROS || {};

EXTROS.draw = (function () {
  'use strict';

  var COLORS = {
    void: '#0B0D0C',
    phos: '#FFB000',
    dim: '#8A5E00',
    burn: '#FFE9B8',
    alert: '#FF3B1F',
    cold: '#4FD1C5'
  };

  var ctx = null;       // set on first render()
  var curField = null;  // set at the top of each render() call

  // ==== FIELD TRANSFORM ====
  // along 0 = player, along 1 = opponent. Portrait rotates the whole
  // arena so the player's emitter is always nearest the bottom edge.
  function pt(a, c) {
    var f = curField;
    return f.portrait
      ? { x: f.fx + c * f.fw, y: f.fy + f.fh - a * f.fh }
      : { x: f.fx + a * f.fw, y: f.fy + c * f.fh };
  }

  function fieldRect(aC, cC, aSize, cSize) {
    var p = pt(aC, cC);
    var f = curField;
    var w = f.portrait ? cSize * f.fw : aSize * f.fw;
    var h = f.portrait ? aSize * f.fh : cSize * f.fh;
    return { x: p.x - w / 2, y: p.y - h / 2, w: w, h: h };
  }

  // Inverse of pt() for the across axis only — the one thing input.js
  // needs to turn a touch/mouse pixel position into a paddle target.
  function screenToAcross(x, y) {
    var f = EXTROS.core.getField();
    return f.portrait ? (x - f.fx) / f.fw : (y - f.fy) / f.fh;
  }

  // ==== COURT ====
  function drawCourt() {
    var f = curField, A = COLORS.phos;
    ctx.save();
    ctx.strokeStyle = A; ctx.globalAlpha = 0.10; ctx.lineWidth = 1;
    var i, p1, p2;
    for (i = 1; i < 10; i++) {
      p1 = pt(i / 10, 0); p2 = pt(i / 10, 1);
      ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
    }
    for (i = 1; i < 6; i++) {
      p1 = pt(0, i / 6); p2 = pt(1, i / 6);
      ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
    }
    ctx.restore();

    ctx.save();
    ctx.strokeStyle = A; ctx.globalAlpha = 0.55; ctx.lineWidth = 1.2;
    ctx.setLineDash([f.u * 1.5, f.u * 1.5]);
    ctx.strokeRect(f.fx, f.fy, f.fw, f.fh);
    ctx.restore();

    ctx.save();
    ctx.strokeStyle = A; ctx.lineWidth = 2; ctx.globalAlpha = 0.9;
    var b = f.u * EXTROS.tuning.visual.cornerBracketUnits;
    [[f.fx, f.fy, 1, 1], [f.fx + f.fw, f.fy, -1, 1],
     [f.fx, f.fy + f.fh, 1, -1], [f.fx + f.fw, f.fy + f.fh, -1, -1]]
      .forEach(function (k) {
        ctx.beginPath();
        ctx.moveTo(k[0] + b * k[2], k[1]);
        ctx.lineTo(k[0], k[1]);
        ctx.lineTo(k[0], k[1] + b * k[3]);
        ctx.stroke();
      });
    ctx.restore();
  }

  // ==== EMITTERS ====
  function drawPlayer() {
    var player = EXTROS.state.getPlayer();
    var r = fieldRect(player.a, player.c, EXTROS.tuning.paddle.thickness, player.len);
    ctx.save();
    ctx.strokeStyle = COLORS.phos; ctx.lineWidth = 1.5; ctx.globalAlpha = 0.9;
    ctx.strokeRect(r.x, r.y, r.w, r.h);
    ctx.globalAlpha = 0.18; ctx.fillStyle = COLORS.phos;
    ctx.fillRect(r.x, r.y, r.w, r.h);
    ctx.restore();
  }

  function drawOpponent() {
    var opponent = EXTROS.state.getOpponent();
    var r = fieldRect(opponent.a, opponent.c, EXTROS.tuning.paddle.thickness, opponent.len);
    ctx.save();
    ctx.shadowColor = COLORS.cold; ctx.shadowBlur = 10;
    ctx.fillStyle = COLORS.cold; ctx.globalAlpha = 0.92;
    ctx.fillRect(r.x, r.y, r.w, r.h);
    ctx.restore();
  }

  // ==== BALL + TRAIL ====
  var trailBuf = []; // { a, c, t } — pruned by age, so it looks the same at any FPS

  function updateTrail(a, c, now) {
    trailBuf.push({ a: a, c: c, t: now });
    var lifetime = EXTROS.tuning.visual.trailLifetimeMs;
    while (trailBuf.length && now - trailBuf[0].t > lifetime) trailBuf.shift();
  }

  function drawTrail(now) {
    var f = curField;
    var lifetime = EXTROS.tuning.visual.trailLifetimeMs;
    ctx.save();
    for (var i = 0; i < trailBuf.length; i++) {
      var e = trailBuf[i];
      var age = (now - e.t) / lifetime; // 0 fresh .. 1 stale
      var p = pt(e.a, e.c);
      ctx.globalAlpha = (1 - age) * 0.35;
      ctx.fillStyle = COLORS.phos;
      ctx.beginPath();
      ctx.arc(p.x, p.y, f.u * 1.4 * (1 - age * 0.7), 0, 6.2832);
      ctx.fill();
    }
    ctx.restore();
  }

  function drawBall(a, c) {
    var f = curField;
    var p = pt(a, c);
    var rr = f.u * EXTROS.tuning.visual.ballGlowUnits;
    ctx.save();
    ctx.globalAlpha = 0.30; ctx.fillStyle = COLORS.phos;
    ctx.beginPath(); ctx.arc(p.x, p.y, rr * EXTROS.tuning.visual.ballHaloUnits, 0, 6.2832); ctx.fill();
    ctx.globalAlpha = 1; ctx.fillStyle = COLORS.burn;
    ctx.shadowColor = COLORS.burn; ctx.shadowBlur = 16;
    ctx.beginPath(); ctx.arc(p.x, p.y, rr, 0, 6.2832); ctx.fill();
    ctx.restore();
  }

  // ==== HUD ====
  function text(str, x, y, size, color, align, track) {
    ctx.save();
    ctx.font = size + 'px ui-monospace, monospace';
    ctx.fillStyle = color; ctx.textBaseline = 'middle';
    var sp = track || 0;
    var w = ctx.measureText(str).width + sp * (str.length - 1);
    var sx = align === 'center' ? x - w / 2 : align === 'right' ? x - w : x;
    for (var i = 0; i < str.length; i++) {
      ctx.fillText(str[i], sx, y);
      sx += ctx.measureText(str[i]).width + sp;
    }
    ctx.restore();
  }

  function drawHUD() {
    var f = curField;
    var top = f.fy - f.u * 8;
    text('EXTROS', f.fx, top, f.u * 2.4, COLORS.dim, 'left', f.u * 0.4);
    text('// CONTAINMENT', f.fx + f.u * 16, top, f.u * 1.8, COLORS.dim, 'left', f.u * 0.18);
  }

  // ==== FRAME ====
  function render(alpha) {
    var field = EXTROS.core.getField();
    var ctxRef = EXTROS.core.getCtx();
    if (!ctxRef || field.W === 0) return;
    ctx = ctxRef;
    curField = field;

    ctx.fillStyle = COLORS.void;
    ctx.fillRect(0, 0, field.W, field.H);

    var ball = EXTROS.state.getBall();
    var prevBall = EXTROS.state.getPrevBall();
    var ia = prevBall.a + (ball.a - prevBall.a) * alpha;
    var ic = prevBall.c + (ball.c - prevBall.c) * alpha;

    var now = performance.now();
    drawCourt();
    updateTrail(ia, ic, now);
    drawTrail(now);
    drawOpponent();
    drawPlayer();
    drawBall(ia, ic);
    drawHUD();
  }

  return {
    render: render,
    screenToAcross: screenToAcross
  };
})();
