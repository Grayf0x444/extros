// input.js
// Touch + keyboard + mouse, fused into one normalized signal. Game logic
// never learns which device produced it. All schemes are always live —
// no mode picker, no device-detection screen.
window.EXTROS = window.EXTROS || {};

EXTROS.input = (function () {
  'use strict';

  var T = EXTROS.tuning.input;

  var pos = 0.5;          // current smoothed/integrated target, 0..1
  var smoothTarget = 0.5; // where touch/mouse are steering pos toward
  var charging = false;
  var confirm = false;
  var mode = 'idle';      // 'touch' | 'mouse' | 'keyboard' | 'idle', for HUD hints only

  function clamp01(v) { return Math.max(0, Math.min(1, v)); }

  // The one place input needs orientation-aware pixel math; it borrows
  // draw.js's single canonical transform rather than duplicating it.
  function acrossFromEvent(x, y) {
    if (EXTROS.draw && EXTROS.draw.screenToAcross) return EXTROS.draw.screenToAcross(x, y);
    return pos;
  }

  // ==== TOUCH ====
  // Relative drag with offset capture: the paddle never jumps to the
  // finger. Only the first active touch is tracked; the rest are ignored.
  var activeTouchId = null;
  var touchStartRaw = 0;
  var touchStartPos = 0;

  function findTouch(list) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].identifier === activeTouchId) return list[i];
    }
    return null;
  }

  function onTouchStart(e) {
    if (activeTouchId !== null) return;
    var t = e.changedTouches[0];
    activeTouchId = t.identifier;
    touchStartRaw = acrossFromEvent(t.clientX, t.clientY);
    touchStartPos = pos;
    smoothTarget = pos;
    mode = 'touch';
    charging = true;
    e.preventDefault();
  }

  function onTouchMove(e) {
    var t = findTouch(e.touches);
    if (!t) return;
    var raw = acrossFromEvent(t.clientX, t.clientY);
    smoothTarget = clamp01(touchStartPos + (raw - touchStartRaw) * T.touchSensitivity);
    e.preventDefault();
  }

  function onTouchEnd(e) {
    var t = findTouch(e.changedTouches);
    if (!t) return;
    activeTouchId = null;
    charging = false;
    e.preventDefault();
  }

  // ==== MOUSE ====
  function onMouseMove(e) {
    if (activeTouchId !== null) return; // an active touch gesture wins
    smoothTarget = clamp01(acrossFromEvent(e.clientX, e.clientY));
    mode = 'mouse';
  }
  function onMouseDown(e) {
    if (e.button === 0) charging = true;
    mode = 'mouse';
  }
  function onMouseUp(e) {
    if (e.button === 0) charging = false;
  }

  // ==== KEYBOARD ====
  // Velocity-based: keydown accelerates, keyup applies friction. Both W/S
  // and A/D (plus arrows) map to the same two logical directions, so
  // keyboard input needs no orientation knowledge at all — it stays
  // correct in both portrait and landscape without a single check.
  var DECREASE = { KeyW: 1, ArrowUp: 1, KeyA: 1, ArrowLeft: 1 };
  var INCREASE = { KeyS: 1, ArrowDown: 1, KeyD: 1, ArrowRight: 1 };
  var CHARGE_KEYS = { Space: 1, ShiftLeft: 1, ShiftRight: 1 };
  var keysDown = {};
  var keyVelocity = 0;

  function keyDir() {
    var dec = false, inc = false, k;
    for (k in DECREASE) if (keysDown[k]) { dec = true; break; }
    for (k in INCREASE) if (keysDown[k]) { inc = true; break; }
    if (dec && !inc) return -1;
    if (inc && !dec) return 1;
    return 0;
  }

  function onKeyDown(e) {
    if (DECREASE[e.code] || INCREASE[e.code]) {
      keysDown[e.code] = true; mode = 'keyboard'; e.preventDefault();
    } else if (CHARGE_KEYS[e.code]) {
      charging = true; e.preventDefault();
    } else if (e.code === 'Enter') {
      confirm = true;
    }
  }

  function onKeyUp(e) {
    if (DECREASE[e.code] || INCREASE[e.code]) {
      keysDown[e.code] = false; e.preventDefault();
    } else if (CHARGE_KEYS[e.code]) {
      charging = false; e.preventDefault();
    } else if (e.code === 'Enter') {
      confirm = false;
    }
  }

  // ==== PER-FRAME UPDATE ====
  function update(dt) {
    var dir = keyDir();
    if (dir !== 0) {
      keyVelocity += dir * T.keyboardAccel * dt;
      keyVelocity = Math.max(-T.keyboardMaxSpeed, Math.min(T.keyboardMaxSpeed, keyVelocity));
    } else if (keyVelocity !== 0) {
      var friction = T.keyboardFriction * dt;
      if (Math.abs(keyVelocity) <= friction) keyVelocity = 0;
      else keyVelocity -= Math.sign(keyVelocity) * friction;
    }
    if (keyVelocity !== 0) {
      pos = clamp01(pos + keyVelocity * dt);
      smoothTarget = pos;
    }

    if (mode === 'touch' || mode === 'mouse') {
      var rate = 1 - Math.exp(-T.smoothingPerSecond * dt);
      pos = pos + (smoothTarget - pos) * rate;
    }
  }

  // ==== WIRING ====
  function attach() {
    var canvas = document.getElementById('cv');
    canvas.addEventListener('touchstart', onTouchStart, { passive: false });
    canvas.addEventListener('touchmove', onTouchMove, { passive: false });
    canvas.addEventListener('touchend', onTouchEnd, { passive: false });
    canvas.addEventListener('touchcancel', onTouchEnd, { passive: false });
    canvas.addEventListener('mousemove', onMouseMove);
    canvas.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mouseup', onMouseUp);
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
  }
  attach();

  return {
    update: update,
    getState: function () {
      return { target: pos, charging: charging, confirm: confirm };
    },
    getMode: function () { return mode; }
  };
})();
