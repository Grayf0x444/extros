"""
KAIJU PROTOCOL -- throwaway pygame feel-test prototype.

Single question: is a HUD-only mech duel against one kaiju fun?
Everything is drawn with pygame primitives -- no image/sound assets.
Touch-first (Android / Pydroid 3), falls back to mouse on desktop.
"""

import math
import random
import sys

import pygame

# ===========================================================================
# CONSTANTS -- all tuning numbers live here for fast iteration on a phone.
# ===========================================================================

DESIGN_W, DESIGN_H = 1280, 720

FOV = 75.0                     # degrees
HORIZON_FRAC = 0.72            # horizon sits low so a close kaiju stays hittable
BASE_HEIGHT = 700.0            # kaiju sprite height at dist=100m, pre-scale
KAIJU_WIDTH_RATIO = 0.62       # sprite width as a fraction of its height

ARENA_MIN_DIST = 45.0
ARENA_MAX_DIST = 180.0

# Pygame on Android is CPU blit, fill-rate bound -- render at a fraction of
# native resolution. pygame.SCALED hands the upscale to SDL's renderer
# instead of a manual per-frame transform.scale. Drop to 0.4 if still short
# of 30fps.
RENDER_SCALE = 0.5
TARGET_FPS = 30

LOOK_SENSITIVITY = 0.22        # deg of yaw per pixel of horizontal drag, at real screen scale
LOOK_SMOOTHING = 0.35          # 0 = raw, 1 = frozen
LOOK_MOMENTUM_TIME = 0.3       # seconds a flick keeps coasting after finger-up
EDGE_ZONE_FRAC = 0.12          # width of the double-tap-to-dodge edge strips
DOUBLE_TAP_WINDOW = 0.3        # seconds between taps to count as a double-tap

FIRE_BTN_RADIUS = 75
DODGE_BTN_RADIUS = 65
BTN_GAP = 24
BTN_MARGIN = 40
BTN_Y_FRAC = 0.80
BTN_HIT_PAD = 1.2              # hit-test radius vs drawn radius -- forgiveness

FIRE_RATE = 6.0                 # shots/sec while held
FIRE_INTERVAL = 1.0 / FIRE_RATE
SHOT_DAMAGE = 12.0
WEAKPOINT_MULT = 3.0            # exposed (sheared) plate
RECOVER_MULT = 1.5              # kaiju is in RECOVER state

HEAT_PER_SHOT = 5.0
HEAT_MAX = 100.0
HEAT_COOL_RATE = 30.0            # per second
HEAT_COOL_DELAY = 0.4            # seconds after last shot before cooling starts
HEAT_LOCKOUT_TIME = 2.0

PLAYER_MAX_HP = 100.0
HIT_DAMAGE = 15.0                # SWIPE / ROAR
CHARGE_DAMAGE = 30.0              # CHARGE, if it connects

DODGE_ANGLE = 12.0                # degrees, total shift over the dash
DODGE_DURATION = 0.35
DODGE_COOLDOWN = 0.8
DODGE_INVULN = 0.25               # seconds of i-frames at the start of the dash
DASH_PUSH_PX = 30.0                # lateral camera kick during a dash, design px

# The single most important number in the prototype -- how readable is the
# telegraph? Tune this first if the fight feels unfair or too easy.
TELEGRAPH_TIME = 0.9
ATTACK_TIME = 0.4
RECOVER_TIME = 1.2
APPROACH_TIME_MIN = 2.0
APPROACH_TIME_MAX = 4.0
APPROACH_CLOSE_RATE = 25.0        # m/s
APPROACH_DRIFT_RATE = 6.0         # deg/s sideways drift
CHARGE_CLOSE_FACTOR = 0.4         # CHARGE multiplies dist by this
ROAR_MIN_DIST = 110.0             # ROAR only selectable at range

KAIJU_MAX_HP = 1000.0
KAIJU_NAME = "VARANT-CLASS"
KAIJU_START_DIST = 160.0

COUNTDOWN_TIME = 3.0
KILL_SLOWMO_TIME = 1.5
KILL_SLOWMO_SCALE = 0.3
KILL_HITSTOP = 0.12
PLATE_BREAK_HITSTOP = 0.04
LOSE_DELAY = 0.6

DEBUG_TOUCH = True         # draws finger positions + look/fire state
DEBUG_PERF = True          # draws fps + build info
DEBUG_TEXT_REFRESH = 0.25  # seconds between debug text re-renders

# palette -- cold greens/cyans on near-black, red reserved for danger
COL_BG_SKY = (8, 16, 20)
COL_BG_GROUND = (5, 10, 12)
COL_HORIZON_GLOW = (40, 90, 90)
COL_CYAN = (120, 235, 220)
COL_CYAN_DIM = (60, 130, 125)
COL_GREEN = (130, 235, 140)
COL_RED = (235, 70, 70)
COL_ORANGE = (255, 150, 45)
COL_YELLOW = (235, 215, 90)
COL_WHITE = (240, 250, 248)
COL_KAIJU_BODY = (18, 30, 28)
COL_KAIJU_OUTLINE = (90, 200, 190)
COL_PLATE = (70, 90, 92)
COL_BUILDING_FAR = (14, 26, 28)
COL_BUILDING_NEAR = (10, 20, 22)
NEAR_LAYER_COLORKEY = (255, 0, 255)


def angle_diff(a, b):
    """Shortest signed difference a-b, normalized to -180..180."""
    return (a - b + 180.0) % 360.0 - 180.0


def wrap360(a):
    """Float-safe wrap to [0, 360) -- plain % can land exactly on 360.0
    after enough accumulated additions."""
    a %= 360.0
    if a >= 360.0:
        a -= 360.0
    return a


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


# ===========================================================================
# PLAYER
# ===========================================================================

class Player:
    def __init__(self):
        self.angle = 0.0          # position on the arena rim (deg)
        self.yaw = 0.0             # look direction (deg)
        self.yaw_velocity = 0.0    # deg/frame, carries momentum after finger-up
        self.hp = PLAYER_MAX_HP

        self.heat = 0.0
        self.overheated = False
        self.lockout_timer = 0.0
        self.time_since_fire = 999.0
        self.fire_cooldown = 0.0

        self.dodge_cooldown = 0.0
        self.dodging = False
        self.dodge_timer = 0.0
        self.dodge_dir = 0
        self.invulnerable = False
        self.dash_push = 0.0        # lateral camera kick, logical px, this frame
        self.dash_push_max = 0.0

        self.shots_fired = 0
        self.shots_hit = 0
        self.hits_taken = 0

    def try_dodge(self, direction, game):
        if self.dodge_cooldown <= 0.0 and not self.dodging:
            self.dodging = True
            self.dodge_timer = 0.0
            self.dodge_dir = direction
            self.invulnerable = True
            self.dodge_cooldown = DODGE_COOLDOWN
            self.dash_push_max = DASH_PUSH_PX * game.scale
            game.add_shake(5, 0.15)

    def update(self, dt):
        self.time_since_fire += dt

        if self.dodge_cooldown > 0.0:
            self.dodge_cooldown = max(0.0, self.dodge_cooldown - dt)

        if self.dodging:
            self.dodge_timer += dt
            self.angle += self.dodge_dir * DODGE_ANGLE * (dt / DODGE_DURATION)
            t = clamp(self.dodge_timer / DODGE_DURATION, 0.0, 1.0)
            self.dash_push = math.sin(t * math.pi) * self.dash_push_max * self.dodge_dir
            if self.dodge_timer >= DODGE_INVULN:
                self.invulnerable = False
            if self.dodge_timer >= DODGE_DURATION:
                self.dodging = False
                self.dash_push = 0.0

        if self.fire_cooldown > 0.0:
            self.fire_cooldown = max(0.0, self.fire_cooldown - dt)

        if self.lockout_timer > 0.0:
            self.lockout_timer -= dt
            if self.lockout_timer <= 0.0:
                self.overheated = False
                self.heat = 0.0
        elif self.time_since_fire >= HEAT_COOL_DELAY:
            self.heat = max(0.0, self.heat - HEAT_COOL_RATE * dt)

        if self.heat >= HEAT_MAX and not self.overheated:
            self.overheated = True
            self.lockout_timer = HEAT_LOCKOUT_TIME
            self.heat = HEAT_MAX

    @property
    def accuracy(self):
        if self.shots_fired == 0:
            return 0.0
        return self.shots_hit / self.shots_fired * 100.0


# ===========================================================================
# KAIJU
# ===========================================================================

PLATE_NAMES = ("head", "l_shoulder", "r_shoulder", "chest")
# fractional (x0, y0, x1, y1) rects within the kaiju bounding box
PLATE_LOCAL_RECTS = {
    "head": (0.32, 0.0, 0.68, 0.17),
    "l_shoulder": (0.02, 0.16, 0.42, 0.36),
    "r_shoulder": (0.58, 0.16, 0.98, 0.36),
    "chest": (0.24, 0.32, 0.76, 0.66),
}


class Kaiju:
    def __init__(self):
        self.angle = 0.0
        self.dist = KAIJU_START_DIST
        self.hp = KAIJU_MAX_HP
        self.max_hp = KAIJU_MAX_HP
        self.plates = {name: {"hp": 100.0, "intact": True} for name in PLATE_NAMES}
        self.state = "APPROACH"
        self.state_timer = random.uniform(APPROACH_TIME_MIN, APPROACH_TIME_MAX)
        self.attack_type = None
        self.drift_dir = random.choice((-1, 1))
        self.bob_phase = random.uniform(0, math.tau)
        self.dead = False
        self.frozen = False  # true during COUNTDOWN

    def update(self, dt, game):
        if self.frozen or self.dead:
            return
        self.bob_phase += dt

        if self.state == "APPROACH":
            self.dist = clamp(self.dist - APPROACH_CLOSE_RATE * dt, ARENA_MIN_DIST, ARENA_MAX_DIST)
            self.angle += self.drift_dir * APPROACH_DRIFT_RATE * dt
            self.state_timer -= dt
            if self.state_timer <= 0.0:
                self._enter_telegraph(game)
        elif self.state == "TELEGRAPH":
            self.state_timer -= dt
            if self.state_timer <= 0.0:
                self._enter_attack(game)
        elif self.state == "ATTACK":
            self.state_timer -= dt
            if self.state_timer <= 0.0:
                self._enter_recover()
        elif self.state == "RECOVER":
            self.state_timer -= dt
            if self.state_timer <= 0.0:
                self._enter_approach()

    def _enter_telegraph(self, game):
        choices = ["SWIPE", "CHARGE"]
        if self.dist > ROAR_MIN_DIST:
            choices.append("ROAR")
        self.attack_type = random.choice(choices)
        self.state = "TELEGRAPH"
        self.state_timer = TELEGRAPH_TIME
        game.on_telegraph_start()

    def _enter_attack(self, game):
        self.state = "ATTACK"
        self.state_timer = ATTACK_TIME
        self._resolve_attack(game)

    def _resolve_attack(self, game):
        # All three attacks share one answer: dodge i-frames timed off the
        # telegraph. ROAR used to be unconditional guaranteed damage -- that
        # read as the game cheating, so it now follows the same rule.
        player = game.player
        if self.attack_type == "CHARGE":
            self.dist = clamp(self.dist * CHARGE_CLOSE_FACTOR, ARENA_MIN_DIST, ARENA_MAX_DIST)
        if player.invulnerable:
            game.on_dodge_success()
        else:
            dmg = CHARGE_DAMAGE if self.attack_type == "CHARGE" else HIT_DAMAGE
            game.damage_player(dmg)

    def _enter_recover(self):
        self.state = "RECOVER"
        self.state_timer = RECOVER_TIME

    def _enter_approach(self):
        self.state = "APPROACH"
        self.state_timer = random.uniform(APPROACH_TIME_MIN, APPROACH_TIME_MAX)
        self.drift_dir = random.choice((-1, 1))

    @property
    def hp_frac(self):
        return clamp(self.hp / self.max_hp, 0.0, 1.0)


# ===========================================================================
# CITY -- purely cosmetic parallax silhouette. Sky, ground, horizon line and
# the far building layer share zero horizontal variation in appearance
# beyond building placement, so they're baked into ONE opaque strip
# (scanlines too -- horizontal lines are x-invariant, baking them in is
# visually identical to redrawing them and costs nothing per frame). The
# near layer is a second, smaller, colorkeyed strip blitted on top.
# ===========================================================================

class Building:
    __slots__ = ("angle", "height", "width")

    def __init__(self, angle, height, width):
        self.angle = angle
        self.height = height
        self.width = width


def generate_city_layer(layer, count, seed):
    rng = random.Random(seed)
    buildings = []
    for _ in range(count):
        if layer == 0:
            height = rng.uniform(40, 130)
            width = rng.uniform(18, 46)
        else:
            height = rng.uniform(60, 220)
            width = rng.uniform(26, 60)
        angle = rng.uniform(0, 360)
        buildings.append(Building(angle, height, width))
    return buildings


LAYER_PARALLAX = (0.45, 0.8)
LAYER_PX_PER_M = (0.9, 1.5)


def _strip_geometry(width, layer):
    ppd = (width / FOV) * LAYER_PARALLAX[layer]
    base_w = max(width + 1, int(360 * ppd))
    return ppd, base_w, base_w + width


def build_bg_strip(buildings, width, height, horizon_y, scale):
    ppd, base_w, strip_w = _strip_geometry(width, 0)
    strip = pygame.Surface((strip_w, height))
    strip.fill(COL_BG_SKY)
    pygame.draw.rect(strip, COL_BG_GROUND, (0, horizon_y, strip_w, height - horizon_y))
    pygame.draw.line(strip, COL_HORIZON_GLOW, (0, horizon_y), (strip_w, horizon_y), max(1, int(2 * scale)))

    px_per_m = LAYER_PX_PER_M[0] * scale
    for b in buildings:
        cx = b.angle * ppd
        h_px = b.height * px_per_m
        w_px = b.width * px_per_m
        y = horizon_y - h_px
        for x0 in (cx, cx + base_w):
            pygame.draw.rect(strip, COL_BUILDING_FAR, (x0 - w_px / 2.0, y, w_px, h_px))

    # Scanlines are horizontally uniform -- baking them in once at startup
    # is visually identical to redrawing them every frame, for free.
    scan = pygame.Surface((strip_w, height), pygame.SRCALPHA)
    for y in range(0, height, 3):
        pygame.draw.line(scan, (0, 0, 0, 40), (0, y), (strip_w, y))
    strip.blit(scan, (0, 0))

    return strip.convert(), ppd, base_w


def build_near_layer(buildings, width, height, horizon_y, scale):
    ppd, base_w, strip_w = _strip_geometry(width, 1)
    strip = pygame.Surface((strip_w, height))
    strip.fill(NEAR_LAYER_COLORKEY)

    px_per_m = LAYER_PX_PER_M[1] * scale
    for b in buildings:
        cx = b.angle * ppd
        h_px = b.height * px_per_m
        w_px = b.width * px_per_m
        y = horizon_y - h_px
        for x0 in (cx, cx + base_w):
            pygame.draw.rect(strip, COL_BUILDING_NEAR, (x0 - w_px / 2.0, y, w_px, h_px))

    strip.set_colorkey(NEAR_LAYER_COLORKEY)
    return strip.convert(), ppd, base_w


# ===========================================================================
# GAME
# ===========================================================================

class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("KAIJU PROTOCOL")
        print(f"pygame {pygame.version.ver}, SDL {pygame.version.SDL}")

        info = pygame.display.Info()
        real_w, real_h = info.current_w, info.current_h
        if real_w <= 0 or real_h <= 0:
            real_w, real_h = DESIGN_W, DESIGN_H
        self.real_w, self.real_h = real_w, real_h

        # Draw at logical (downscaled) resolution and let SDL's renderer do
        # the upscale via pygame.SCALED -- no manual per-frame transform.
        self.width = max(1, int(real_w * RENDER_SCALE))
        self.height = max(1, int(real_h * RENDER_SCALE))
        try:
            self.screen = pygame.display.set_mode(
                (self.width, self.height), pygame.SCALED | pygame.FULLSCREEN
            )
        except pygame.error:
            self.screen = pygame.display.set_mode((self.width, self.height))

        self.center_x = self.width / 2.0
        self.crosshair_y = self.height * 0.5
        self.scale = min(self.width / DESIGN_W, self.height / DESIGN_H)
        # touch deltas are tracked in logical (downscaled) pixels, but look
        # sensitivity is tuned per real screen pixel -- compensate so turn
        # speed doesn't change with RENDER_SCALE.
        self.look_sens = LOOK_SENSITIVITY * (self.real_w / self.width)
        self.horizon_y = self.height * HORIZON_FRAC

        h_far = BASE_HEIGHT * (100.0 / ARENA_MAX_DIST) * self.scale
        assert self.horizon_y - h_far < self.height * 0.5, (
            "kaiju is unhittable at max range -- raise BASE_HEIGHT or HORIZON_FRAC"
        )

        self.canvas = pygame.Surface((self.width, self.height)).convert()
        self.clock = pygame.time.Clock()
        self.running = True

        self._build_fonts()
        self._build_vignette()
        self._build_white_flash()
        self._build_result_overlay()
        self._build_layout()
        self._build_city()

        self.text_cache = {}
        self.button_cache = {}
        self.debug_touch_surf = None
        self.debug_perf_surf = None
        self.debug_refresh_timer = 0.0
        self.debug_refresh_due = True

        self.touches = {}
        self.touch_mode = False
        self.pending_look_dx = 0.0
        self.last_edge_tap = {"left": -999.0, "right": -999.0}

        self.time_scale = 1.0
        self.hitstop_timer = 0.0
        self.shake_mag = 0.0
        self.shake_timer = 0.0
        self.shake_x = 0.0
        self.shake_y = 0.0

        self.kill_timer = None
        self.white_flash_timer = 0.0
        self.lose_timer = None
        self.warning_flash_timer = 0.0
        self.dodge_flash_timer = 0.0
        self.hit_flash_timer = 0.0
        self.spark_timer = 0.0
        self.vignette_timer = 0.0
        self.plate_break_flash = 0.0
        self.plate_break_pos = (0, 0)

        self.kaiju_proj = None
        self.fight_timer = 0.0

        self.reset_game()

    # -- setup helpers ----------------------------------------------------

    def _build_fonts(self):
        s = self.scale
        self.font_tiny = pygame.font.SysFont(None, max(12, int(16 * s)))
        self.font_small = pygame.font.SysFont(None, max(14, int(20 * s)))
        self.font_med = pygame.font.SysFont(None, max(18, int(28 * s)))
        self.font_big = pygame.font.SysFont(None, max(28, int(44 * s)))
        self.font_huge = pygame.font.SysFont(None, max(40, int(72 * s)))
        self.font_debug = pygame.font.SysFont(None, 20)

    def _build_vignette(self):
        w, h = self.width, self.height
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        edge = max(1, int(min(w, h) * 0.18))
        for i in range(edge):
            alpha = int(255 * (1.0 - i / edge))
            col = (*COL_RED, alpha)
            pygame.draw.rect(surf, col, (0, i, w, 1))
            pygame.draw.rect(surf, col, (0, h - i - 1, w, 1))
            pygame.draw.rect(surf, col, (i, 0, 1, h))
            pygame.draw.rect(surf, col, (w - i - 1, 0, 1, h))
        self.vignette_surf = surf.convert_alpha()

    def _build_white_flash(self):
        surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        surf.fill((255, 255, 255, 255))
        self.white_flash_surf = surf.convert_alpha()

    def _build_result_overlay(self):
        surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        surf.fill((5, 10, 12, 190))
        self.result_overlay_surf = surf.convert_alpha()

    def _build_layout(self):
        s = self.scale
        fire_r = FIRE_BTN_RADIUS * s
        dodge_r = DODGE_BTN_RADIUS * s
        gap = BTN_GAP * s
        margin = BTN_MARGIN * s
        by = self.height * BTN_Y_FRAC
        self.fire_btn_pos = (self.width - margin - fire_r, by)
        self.fire_btn_r = fire_r
        self.fire_btn_hit_r = fire_r * BTN_HIT_PAD
        dr_x = self.fire_btn_pos[0] - fire_r - gap - dodge_r
        self.dodge_r_pos = (dr_x, by)
        self.dodge_l_pos = (dr_x - dodge_r * 2 - gap, by)
        self.dodge_btn_r = dodge_r
        self.dodge_btn_hit_r = dodge_r * BTN_HIT_PAD

    def _build_city(self):
        far = generate_city_layer(0, 40, seed=1337)
        near = generate_city_layer(1, 40, seed=4242)
        self.bg_strip, self.bg_ppd, self.bg_base_w = build_bg_strip(
            far, self.width, self.height, self.horizon_y, self.scale)
        self.near_strip, self.near_ppd, self.near_base_w = build_near_layer(
            near, self.width, self.height, self.horizon_y, self.scale)

    def reset_game(self):
        self.player = Player()
        self.kaiju = Kaiju()
        self.kaiju.frozen = True
        self.state = "COUNTDOWN"
        self.countdown_timer = COUNTDOWN_TIME
        self.fight_timer = 0.0
        self.kill_timer = None
        self.lose_timer = None
        self.time_scale = 1.0
        self.hitstop_timer = 0.0
        self.white_flash_timer = 0.0
        self.result_kind = None

    # -- cached drawing helpers ---------------------------------------------

    def text(self, s, font, color):
        key = (s, id(font), color)
        surf = self.text_cache.get(key)
        if surf is None:
            surf = font.render(s, True, color).convert_alpha()
            if len(self.text_cache) > 200:
                self.text_cache.clear()
            self.text_cache[key] = surf
        return surf

    def button_surface(self, radius, color, active):
        key = (int(radius), color, active)
        surf = self.button_cache.get(key)
        if surf is None:
            r = int(radius)
            surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            alpha = 140 if active else 70
            pygame.draw.circle(surf, (*color, alpha), (r, r), r)
            pygame.draw.circle(surf, (*color, 220), (r, r), r, max(2, int(2 * self.scale)))
            surf = surf.convert_alpha()
            self.button_cache[key] = surf
        return surf

    # -- feedback helpers ---------------------------------------------------

    def add_shake(self, magnitude, duration):
        self.shake_mag = max(self.shake_mag, magnitude * self.scale)
        self.shake_timer = max(self.shake_timer, duration)

    def add_hitstop(self, seconds):
        self.hitstop_timer = max(self.hitstop_timer, seconds)

    def on_telegraph_start(self):
        self.warning_flash_timer = TELEGRAPH_TIME

    def on_dodge_success(self):
        self.dodge_flash_timer = 0.5

    def damage_player(self, dmg):
        self.player.hp = max(0.0, self.player.hp - dmg)
        self.player.hits_taken += 1
        self.add_shake(16, 0.3)
        self.vignette_timer = 0.4
        if self.player.hp <= 0.0 and self.state == "FIGHT" and self.lose_timer is None:
            self.lose_timer = LOSE_DELAY

    def on_crosshair_hit(self):
        self.hit_flash_timer = 0.08
        self.spark_timer = 0.15

    def apply_damage_to_kaiju(self, hit_info):
        k = self.kaiju
        mult = 1.0
        if hit_info["weakpoint"]:
            mult *= WEAKPOINT_MULT
        if k.state == "RECOVER":
            mult *= RECOVER_MULT
        dmg = SHOT_DAMAGE * mult

        zone = hit_info["zone"]
        if zone in k.plates:
            plate = k.plates[zone]
            if plate["intact"]:
                plate["hp"] -= dmg
                if plate["hp"] <= 0.0:
                    plate["hp"] = 0.0
                    plate["intact"] = False
                    self.add_hitstop(PLATE_BREAK_HITSTOP)
                    self.add_shake(12, 0.25)
                    self.plate_break_flash = 0.3
                    self.plate_break_pos = self.kaiju_proj["plate_rects"][zone].center

        k.hp = max(0.0, k.hp - dmg)
        if k.hp <= 0.0 and not k.dead:
            k.dead = True
            self.trigger_kill()

    def trigger_kill(self):
        self.time_scale = KILL_SLOWMO_SCALE
        self.kill_timer = KILL_SLOWMO_TIME
        self.add_hitstop(KILL_HITSTOP)
        self.add_shake(24, 0.5)

    def enter_result(self, kind):
        self.state = "RESULT"
        self.result_kind = kind
        p = self.player
        self.result_time = self.fight_timer
        self.result_accuracy = p.accuracy
        self.result_hits_taken = p.hits_taken
        self.result_rank = compute_rank(self.result_time, self.result_accuracy, self.result_hits_taken, kind)

    # -- input --------------------------------------------------------------

    def zone_at(self, x, y):
        """Buttons are the only exceptions -- everything else turns the
        camera, matching how every mobile FPS handles look-drag."""
        if _dist(x, y, *self.fire_btn_pos) <= self.fire_btn_hit_r:
            return "fire"
        if _dist(x, y, *self.dodge_r_pos) <= self.dodge_btn_hit_r:
            return "dodge_r"
        if _dist(x, y, *self.dodge_l_pos) <= self.dodge_btn_hit_r:
            return "dodge_l"
        return "look"

    def _check_edge_double_tap(self, x, now):
        if x < self.width * EDGE_ZONE_FRAC:
            if now - self.last_edge_tap["left"] < DOUBLE_TAP_WINDOW:
                self.player.try_dodge(-1, self)
                self.last_edge_tap["left"] = -999.0
            else:
                self.last_edge_tap["left"] = now
        elif x > self.width * (1.0 - EDGE_ZONE_FRAC):
            if now - self.last_edge_tap["right"] < DOUBLE_TAP_WINDOW:
                self.player.try_dodge(1, self)
                self.last_edge_tap["right"] = -999.0
            else:
                self.last_edge_tap["right"] = now

    def touch_down(self, tid, x, y):
        if self.state == "RESULT":
            self.reset_game()
            return
        zone = self.zone_at(x, y)
        self.touches[tid] = {"zone": zone, "last_x": x, "last_y": y}
        if zone == "dodge_l":
            self.player.try_dodge(-1, self)
        elif zone == "dodge_r":
            self.player.try_dodge(1, self)
        elif zone == "look":
            self._check_edge_double_tap(x, pygame.time.get_ticks() / 1000.0)

    def touch_move(self, tid, x, y):
        t = self.touches.get(tid)
        if t is None:
            return
        if t["zone"] == "look":
            self.pending_look_dx += x - t["last_x"]
        t["last_x"], t["last_y"] = x, y

    def touch_up(self, tid):
        self.touches.pop(tid, None)

    @property
    def fire_held(self):
        return any(t["zone"] == "fire" for t in self.touches.values())

    @property
    def look_active(self):
        return any(t["zone"] == "look" for t in self.touches.values())

    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            self.running = False
        elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.running = False
        elif hasattr(pygame, "FINGERDOWN") and ev.type == pygame.FINGERDOWN:
            if not self.touch_mode:
                self.touch_mode = True
                self.touches.pop("mouse", None)  # drop any phantom pre-detection
            self.touch_down(ev.finger_id, ev.x * self.width, ev.y * self.height)
        elif hasattr(pygame, "FINGERMOTION") and ev.type == pygame.FINGERMOTION:
            self.touch_move(ev.finger_id, ev.x * self.width, ev.y * self.height)
        elif hasattr(pygame, "FINGERUP") and ev.type == pygame.FINGERUP:
            self.touch_up(ev.finger_id)
        elif ev.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
            # Android SDL emits a synthesised mouse event alongside every
            # FINGER event. getattr(ev, "touch") catches it directly;
            # self.touch_mode catches it even if that attribute is missing,
            # once any real finger event has proven this device sends them.
            if getattr(ev, "touch", False) or self.touch_mode:
                return
            if ev.type == pygame.MOUSEBUTTONDOWN:
                self.touch_down("mouse", *ev.pos)
            elif ev.type == pygame.MOUSEMOTION:
                if "mouse" in self.touches:
                    self.touch_move("mouse", *ev.pos)
            else:
                self.touch_up("mouse")

    # -- update ---------------------------------------------------------

    def fire_shot(self):
        p = self.player
        p.shots_fired += 1
        p.heat = min(HEAT_MAX, p.heat + HEAT_PER_SHOT)
        p.time_since_fire = 0.0
        self.add_shake(3, 0.06)

        hit_info = self.hit_test()
        if hit_info:
            p.shots_hit += 1
            self.apply_damage_to_kaiju(hit_info)
            self.on_crosshair_hit()

        if p.heat >= HEAT_MAX and not p.overheated:
            p.overheated = True
            p.lockout_timer = HEAT_LOCKOUT_TIME

    def hit_test(self):
        proj = self.kaiju_proj
        if proj is None:
            return None
        cx, cy = self.center_x, self.crosshair_y
        if not proj["rect"].collidepoint(cx, cy):
            return None
        for name, prect in proj["plate_rects"].items():
            if prect.collidepoint(cx, cy):
                plate = self.kaiju.plates[name]
                return {"zone": name, "weakpoint": not plate["intact"]}
        return {"zone": "body", "weakpoint": False}

    def compute_kaiju_projection(self):
        k = self.kaiju
        bearing = angle_diff(k.angle - self.player.angle, 0.0)
        rel = angle_diff(bearing, self.player.yaw)
        if abs(rel) > FOV / 2.0 + 20.0:
            self.kaiju_proj = None
            return

        screen_x = self.center_x + (rel / (FOV / 2.0)) * (self.width / 2.0)
        scale = 1.0 / (k.dist / 100.0)
        height_px = BASE_HEIGHT * scale * self.scale
        bob = math.sin(k.bob_phase * 2.0) * 6.0 * self.scale
        screen_y = self.horizon_y - height_px * 0.5 + bob

        width_px = height_px * KAIJU_WIDTH_RATIO
        top = screen_y - height_px / 2.0
        left = screen_x - width_px / 2.0
        rect = pygame.Rect(left, top, width_px, height_px)

        plate_rects = {}
        for name, (fx0, fy0, fx1, fy1) in PLATE_LOCAL_RECTS.items():
            pr = pygame.Rect(
                left + fx0 * width_px,
                top + fy0 * height_px,
                (fx1 - fx0) * width_px,
                (fy1 - fy0) * height_px,
            )
            plate_rects[name] = pr

        self.kaiju_proj = {
            "rect": rect,
            "plate_rects": plate_rects,
            "screen_x": screen_x,
            "top": top,
            "width_px": width_px,
            "height_px": height_px,
        }

    def _update_look(self, real_dt):
        raw_delta = self.pending_look_dx * self.look_sens
        self.pending_look_dx = 0.0
        p = self.player
        if self.look_active:
            p.yaw_velocity = p.yaw_velocity * LOOK_SMOOTHING + raw_delta * (1.0 - LOOK_SMOOTHING)
        elif p.yaw_velocity:
            p.yaw_velocity *= 0.0001 ** (real_dt / LOOK_MOMENTUM_TIME)
            if abs(p.yaw_velocity) < 0.001:
                p.yaw_velocity = 0.0
        p.yaw = wrap360(p.yaw + p.yaw_velocity)

    def update(self, real_dt):
        real_dt = min(real_dt, 0.05)

        if self.touch_mode:
            self.touches.pop("mouse", None)

        self.debug_refresh_timer -= real_dt
        if self.debug_refresh_timer <= 0.0:
            self.debug_refresh_timer = DEBUG_TEXT_REFRESH
            self.debug_refresh_due = True
        else:
            self.debug_refresh_due = False

        self._update_look(real_dt)

        if self.shake_timer > 0.0:
            self.shake_timer = max(0.0, self.shake_timer - real_dt)
            if self.shake_timer <= 0.0:
                self.shake_mag = 0.0
        if self.shake_mag > 0.0:
            self.shake_x = random.uniform(-self.shake_mag, self.shake_mag)
            self.shake_y = random.uniform(-self.shake_mag, self.shake_mag)
        else:
            self.shake_x = self.shake_y = 0.0

        for attr in ("warning_flash_timer", "dodge_flash_timer", "hit_flash_timer",
                     "spark_timer", "vignette_timer", "plate_break_flash", "white_flash_timer"):
            v = getattr(self, attr)
            if v > 0.0:
                setattr(self, attr, max(0.0, v - real_dt))

        if self.hitstop_timer > 0.0:
            self.hitstop_timer = max(0.0, self.hitstop_timer - real_dt)
            dt = 0.0
        else:
            dt = real_dt * self.time_scale

        if self.kill_timer is not None:
            self.kill_timer -= real_dt
            if self.kill_timer <= 0.0:
                self.kill_timer = None
                self.time_scale = 1.0
                self.white_flash_timer = 0.3
                self.enter_result("WIN")

        if self.lose_timer is not None:
            self.lose_timer -= real_dt
            if self.lose_timer <= 0.0:
                self.lose_timer = None
                self.enter_result("LOSE")

        if self.state == "COUNTDOWN":
            self.countdown_timer -= real_dt
            self.compute_kaiju_projection()
            if self.countdown_timer <= 0.0:
                self.state = "FIGHT"
                self.kaiju.frozen = False

        elif self.state == "FIGHT":
            self.fight_timer += real_dt
            self.kaiju.update(dt, self)
            self.compute_kaiju_projection()

            p = self.player
            if p.fire_cooldown <= 0.0 and self.fire_held and not p.overheated:
                p.fire_cooldown = FIRE_INTERVAL
                self.fire_shot()
            p.update(dt)

        elif self.state == "RESULT":
            self.kaiju.bob_phase += real_dt * 0.3
            self.compute_kaiju_projection()

    # -- draw -----------------------------------------------------------

    def draw(self):
        c = self.canvas
        draw_city(c, self)
        if self.kaiju_proj is not None and not self.kaiju.dead:
            draw_kaiju(c, self)
        elif self.kaiju_proj is not None and self.kaiju.dead and self.kill_timer is not None:
            draw_kaiju(c, self)

        draw_hud(c, self)

        self.screen.fill((0, 0, 0))
        self.screen.blit(c, (self.shake_x + self.player.dash_push, self.shake_y))

        if self.white_flash_timer > 0.0:
            self.white_flash_surf.set_alpha(int(255 * (self.white_flash_timer / 0.3)))
            self.screen.blit(self.white_flash_surf, (0, 0))

        if DEBUG_TOUCH:
            draw_touch_debug(self)
        if DEBUG_PERF:
            draw_perf_debug(self)

        pygame.display.flip()

    def run(self):
        while self.running:
            real_dt = self.clock.tick(TARGET_FPS) / 1000.0
            for ev in pygame.event.get():
                self.handle_event(ev)
            self.update(real_dt)
            self.draw()
        pygame.quit()


def _dist(x0, y0, x1, y1):
    return math.hypot(x0 - x1, y0 - y1)


def compute_rank(time_s, accuracy, hits_taken, kind):
    if kind == "LOSE":
        return "-"
    score = accuracy - hits_taken * 12.0 - max(0.0, time_s - 90.0) * 0.4
    if score >= 75:
        return "S"
    if score >= 55:
        return "A"
    if score >= 35:
        return "B"
    if score >= 15:
        return "C"
    return "D"


# ===========================================================================
# DRAWING -- kaiju
# ===========================================================================

def _plate_flash_color(t):
    k = (math.sin(t * 18.0) + 1.0) * 0.5
    return (
        int(lerp(COL_ORANGE[0], 255, k)),
        int(lerp(COL_ORANGE[1], 200, k)),
        int(lerp(COL_ORANGE[2], 80, k)),
    )


def draw_kaiju(surf, game):
    k = game.kaiju
    proj = game.kaiju_proj
    rect = proj["rect"]
    outline_w = max(2, int(3 * game.scale))

    slump = 0.12 if k.state == "RECOVER" else 0.0
    top = rect.top + rect.height * slump
    height = rect.height * (1.0 - slump)
    left = rect.left
    width = rect.width

    def pt(fx, fy):
        return (left + fx * width, top + fy * height)

    body_color = COL_KAIJU_BODY
    outline_color = COL_KAIJU_OUTLINE
    if k.state == "TELEGRAPH":
        flash = (math.sin(pygame.time.get_ticks() * 0.02) + 1.0) * 0.5
        outline_color = (
            int(lerp(COL_KAIJU_OUTLINE[0], COL_RED[0], flash)),
            int(lerp(COL_KAIJU_OUTLINE[1], COL_RED[1], flash)),
            int(lerp(COL_KAIJU_OUTLINE[2], COL_RED[2], flash)),
        )

    # hunched biped silhouette
    torso = [
        pt(0.30, 0.16), pt(0.70, 0.16), pt(0.82, 0.36), pt(0.78, 0.62),
        pt(0.62, 0.72), pt(0.38, 0.72), pt(0.22, 0.62), pt(0.18, 0.36),
    ]
    pygame.draw.polygon(surf, body_color, torso)
    pygame.draw.polygon(surf, outline_color, torso, outline_w)

    # legs
    left_leg = [pt(0.30, 0.66), pt(0.46, 0.66), pt(0.44, 1.0), pt(0.28, 1.0)]
    right_leg = [pt(0.54, 0.66), pt(0.70, 0.66), pt(0.72, 1.0), pt(0.56, 1.0)]
    pygame.draw.polygon(surf, body_color, left_leg)
    pygame.draw.polygon(surf, outline_color, left_leg, outline_w)
    pygame.draw.polygon(surf, body_color, right_leg)
    pygame.draw.polygon(surf, outline_color, right_leg, outline_w)

    # arms
    left_arm = [pt(0.16, 0.30), pt(0.26, 0.30), pt(0.20, 0.62), pt(0.08, 0.58)]
    right_arm = [pt(0.74, 0.30), pt(0.84, 0.30), pt(0.92, 0.58), pt(0.80, 0.62)]
    pygame.draw.polygon(surf, body_color, left_arm)
    pygame.draw.polygon(surf, outline_color, left_arm, outline_w)
    pygame.draw.polygon(surf, body_color, right_arm)
    pygame.draw.polygon(surf, outline_color, right_arm, outline_w)

    # head
    head = [pt(0.36, 0.0), pt(0.64, 0.0), pt(0.68, 0.17), pt(0.32, 0.17)]
    pygame.draw.polygon(surf, body_color, head)
    pygame.draw.polygon(surf, outline_color, head, outline_w)

    # plates
    flash_t = pygame.time.get_ticks() * 0.001
    for name, prect in proj["plate_rects"].items():
        plate = k.plates[name]
        adj = pygame.Rect(prect.x, top + (prect.y - rect.top) * (height / rect.height),
                           prect.width, prect.height * (height / rect.height))
        if plate["intact"]:
            pygame.draw.rect(surf, COL_PLATE, adj)
            pygame.draw.rect(surf, outline_color, adj, max(1, int(2 * game.scale)))
        else:
            color = _plate_flash_color(flash_t)
            pygame.draw.rect(surf, color, adj, max(2, int(3 * game.scale)))

    if game.plate_break_flash > 0.0:
        t = 1.0 - game.plate_break_flash / 0.3
        radius = int((10 + t * 55) * game.scale)
        bx, by = game.plate_break_pos
        pygame.draw.circle(surf, COL_WHITE, (int(bx), int(by)), radius, max(2, int(3 * game.scale)))

# ===========================================================================
# DRAWING -- city (two pre-baked strips, two blits total)
# ===========================================================================

def draw_city(surf, game):
    bg_off = (game.player.yaw * game.bg_ppd - game.width / 2.0) % game.bg_base_w
    surf.blit(game.bg_strip, (0, 0), pygame.Rect(int(bg_off), 0, game.width, game.height))
    near_off = (game.player.yaw * game.near_ppd - game.width / 2.0) % game.near_base_w
    surf.blit(game.near_strip, (0, 0), pygame.Rect(int(near_off), 0, game.width, game.height))


# ===========================================================================
# DRAWING -- HUD
# ===========================================================================

def draw_hud(surf, game):
    if game.state == "COUNTDOWN":
        draw_countdown(surf, game)
    elif game.state == "FIGHT":
        draw_top_bar(surf, game)
        draw_target_bracket(surf, game)
        draw_crosshair(surf, game)
        draw_heat_bar(surf, game)
        draw_health(surf, game)
        draw_warning(surf, game)
        draw_dodge_flash(surf, game)
        draw_dash_streaks(surf, game)
        draw_buttons(surf, game)
        draw_vignette(surf, game)
        draw_spark(surf, game)
    elif game.state == "RESULT":
        draw_result(surf, game)


def draw_top_bar(surf, game):
    s = game.scale
    pad = 20 * s
    txt = game.text(f"TARGET: {KAIJU_NAME}", game.font_small, COL_CYAN)
    surf.blit(txt, (pad, pad))

    dist_m = int(game.kaiju.dist // 5 * 5)
    dtxt = game.text(f"DIST {dist_m}m", game.font_small, COL_CYAN)
    surf.blit(dtxt, (game.width - dtxt.get_width() - pad, pad))


def draw_target_bracket(surf, game):
    proj = game.kaiju_proj
    if proj is None or game.kaiju.dead:
        return
    s = game.scale
    r = proj["rect"]
    ln = 16 * s
    lw = max(2, int(3 * s))
    col = COL_RED if game.kaiju.state == "TELEGRAPH" else COL_CYAN
    corners = [(r.left, r.top, 1, 1), (r.right, r.top, -1, 1),
               (r.left, r.bottom, 1, -1), (r.right, r.bottom, -1, -1)]
    for x, y, dx, dy in corners:
        pygame.draw.line(surf, col, (x, y), (x + ln * dx, y), lw)
        pygame.draw.line(surf, col, (x, y), (x, y + ln * dy), lw)


def draw_crosshair(surf, game):
    s = game.scale
    cx, cy = game.center_x + game.player.dash_push, game.crosshair_y
    p = game.player
    expand = 6 * s if game.fire_held else 0.0
    gap = 10 * s + expand
    ln = 14 * s
    lw = max(2, int(2 * s))

    col = COL_CYAN
    if p.overheated:
        col = COL_RED
    elif game.hit_flash_timer > 0.0:
        col = COL_WHITE

    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        x0 = cx + dx * gap
        y0 = cy + dy * gap
        x1 = cx + dx * (gap + ln)
        y1 = cy + dy * (gap + ln)
        pygame.draw.line(surf, col, (x0, y0), (x1, y1), lw)


def draw_spark(surf, game):
    if game.spark_timer <= 0.0:
        return
    s = game.scale
    cx, cy = game.center_x, game.crosshair_y
    t = game.spark_timer / 0.15
    length = 20 * s * t
    for ang in range(0, 360, 45):
        rad = math.radians(ang)
        x1 = cx + math.cos(rad) * 6 * s
        y1 = cy + math.sin(rad) * 6 * s
        x2 = cx + math.cos(rad) * (6 * s + length)
        y2 = cy + math.sin(rad) * (6 * s + length)
        pygame.draw.line(surf, COL_WHITE, (x1, y1), (x2, y2), max(1, int(2 * s)))


def draw_dash_streaks(surf, game):
    p = game.player
    if not p.dodging:
        return
    s = game.scale
    t = clamp(p.dodge_timer / DODGE_DURATION, 0.0, 1.0)
    length = 70 * s * math.sin(t * math.pi)
    x_edge = 0 if p.dodge_dir > 0 else game.width
    dx = length if p.dodge_dir > 0 else -length
    for frac in (0.3, 0.5, 0.7):
        y = game.height * frac
        pygame.draw.line(surf, COL_CYAN_DIM, (x_edge, y), (x_edge + dx, y), max(1, int(3 * s)))


def draw_heat_bar(surf, game):
    s = game.scale
    p = game.player
    bar_w, bar_h = 220 * s, 22 * s
    x = game.width - bar_w - 24 * s
    y = game.height - 70 * s
    pygame.draw.rect(surf, (30, 40, 40), (x, y, bar_w, bar_h))

    frac = p.heat / HEAT_MAX
    if p.overheated:
        fill_col = COL_RED
        frac = 1.0
    elif frac < 0.5:
        fill_col = COL_GREEN
    elif frac < 0.8:
        fill_col = COL_YELLOW
    else:
        fill_col = COL_ORANGE
    pygame.draw.rect(surf, fill_col, (x, y, bar_w * frac, bar_h))
    pygame.draw.rect(surf, COL_CYAN_DIM, (x, y, bar_w, bar_h), max(1, int(2 * s)))

    label = "OVERHEAT" if p.overheated else "HEAT"
    col = COL_RED if p.overheated else COL_CYAN
    ltxt = game.text(label, game.font_tiny, col)
    surf.blit(ltxt, (x, y - ltxt.get_height() - 4 * s))

    if p.overheated and int(pygame.time.get_ticks() * 0.006) % 2 == 0:
        warn = game.text("OVERHEAT", game.font_med, COL_RED)
        surf.blit(warn, (game.center_x - warn.get_width() / 2, game.height * 0.3))


def draw_health(surf, game):
    s = game.scale
    p = game.player
    segments = 10
    seg_w, seg_h = 22 * s, 22 * s
    gap = 4 * s
    x0 = 24 * s
    y = game.height - 70 * s
    filled = round(p.hp / PLAYER_MAX_HP * segments)

    label = game.text("HULL", game.font_tiny, COL_CYAN)
    surf.blit(label, (x0, y - label.get_height() - 4 * s))

    frac = p.hp / PLAYER_MAX_HP
    col = COL_GREEN if frac > 0.5 else (COL_YELLOW if frac > 0.25 else COL_RED)
    for i in range(segments):
        rx = x0 + i * (seg_w + gap)
        rect = (rx, y, seg_w, seg_h)
        if i < filled:
            pygame.draw.rect(surf, col, rect)
        else:
            pygame.draw.rect(surf, (30, 40, 40), rect)
        pygame.draw.rect(surf, COL_CYAN_DIM, rect, max(1, int(1 * s)))


def draw_warning(surf, game):
    if game.kaiju.state != "TELEGRAPH":
        return
    flash = (math.sin(pygame.time.get_ticks() * 0.02) + 1.0) * 0.5
    if flash < 0.5:
        return
    txt = game.text("WARNING", game.font_huge, COL_RED)
    surf.blit(txt, (game.center_x - txt.get_width() / 2, game.height * 0.22))


def draw_dodge_flash(surf, game):
    if game.dodge_flash_timer <= 0.0:
        return
    a = int(255 * (game.dodge_flash_timer / 0.5))
    txt = game.text("DODGED", game.font_med, COL_GREEN)
    txt.set_alpha(a)
    surf.blit(txt, (game.center_x - txt.get_width() / 2, game.height * 0.38))
    txt.set_alpha(255)


def draw_buttons(surf, game):
    p = game.player

    def circle(pos, radius, label, active, color, label_color=COL_WHITE):
        base = game.button_surface(radius, color, active)
        surf.blit(base, (pos[0] - radius, pos[1] - radius))
        txt = game.text(label, game.font_small, label_color)
        surf.blit(txt, (pos[0] - txt.get_width() / 2, pos[1] - txt.get_height() / 2))

    fire_active = game.fire_held
    circle(game.fire_btn_pos, game.fire_btn_r, "FIRE", fire_active, COL_ORANGE if not p.overheated else COL_RED)

    dl_active = p.dodging and p.dodge_dir < 0
    dr_active = p.dodging and p.dodge_dir > 0
    cooldown_col = COL_CYAN_DIM if p.dodge_cooldown > 0 else COL_CYAN
    circle(game.dodge_l_pos, game.dodge_btn_r, "L", dl_active, cooldown_col)
    circle(game.dodge_r_pos, game.dodge_btn_r, "R", dr_active, cooldown_col)


def draw_vignette(surf, game):
    if game.vignette_timer <= 0.0:
        return
    game.vignette_surf.set_alpha(int(160 * (game.vignette_timer / 0.4)))
    surf.blit(game.vignette_surf, (0, 0))


def draw_countdown(surf, game):
    t = game.countdown_timer
    n = int(math.ceil(t))
    n = max(1, min(3, n))
    txt = game.text(str(n), game.font_huge, COL_CYAN)
    surf.blit(txt, (game.center_x - txt.get_width() / 2, game.height * 0.4))

    boot = game.text("SYSTEMS ONLINE", game.font_small, COL_GREEN)
    surf.blit(boot, (game.center_x - boot.get_width() / 2, game.height * 0.4 + txt.get_height()))


def draw_result(surf, game):
    surf.blit(game.result_overlay_surf, (0, 0))

    s = game.scale
    cx = game.center_x
    y = game.height * 0.22

    if game.result_kind == "WIN":
        title = f"{KAIJU_NAME} — DOWN"
        col = COL_CYAN
    else:
        title = "MECH DOWN"
        col = COL_RED

    t_txt = game.text(title, game.font_big, col)
    surf.blit(t_txt, (cx - t_txt.get_width() / 2, y))
    y += t_txt.get_height() + 30 * s

    minutes = int(game.result_time) // 60
    seconds = int(game.result_time) % 60
    rows = [
        ("TIME", f"{minutes}:{seconds:02d}"),
        ("ACCURACY", f"{game.result_accuracy:.0f}%"),
        ("HITS TAKEN", f"{game.result_hits_taken}"),
        ("RANK", game.result_rank),
    ]
    for label, value in rows:
        ltxt = game.text(label, game.font_med, COL_CYAN_DIM)
        vtxt = game.text(value, game.font_med, COL_WHITE)
        surf.blit(ltxt, (cx - 160 * s, y))
        surf.blit(vtxt, (cx + 40 * s, y))
        y += ltxt.get_height() + 10 * s

    y += 30 * s
    flash = (math.sin(pygame.time.get_ticks() * 0.004) + 1.0) * 0.5
    prompt_col = tuple(int(lerp(COL_CYAN_DIM[i], COL_CYAN[i], flash)) for i in range(3))
    prompt = game.text("[ TAP TO RETRY ]", game.font_med, prompt_col)
    surf.blit(prompt, (cx - prompt.get_width() / 2, y))


# ===========================================================================
# DEBUG OVERLAYS -- text re-renders throttled to DEBUG_TEXT_REFRESH; the
# finger position dots are cheap draw.circle calls and stay live every frame.
# ===========================================================================

def draw_touch_debug(game):
    screen = game.screen
    for tid, t in game.touches.items():
        x, y = t["last_x"], t["last_y"]
        col = {"look": COL_CYAN, "fire": COL_ORANGE, "dodge_l": COL_GREEN, "dodge_r": COL_GREEN}.get(t["zone"], COL_WHITE)
        pygame.draw.circle(screen, col, (int(x), int(y)), 14, 2)

    if game.debug_touch_surf is None or game.debug_refresh_due:
        ids = " ".join(f"{tid}:{t['zone']}" for tid, t in game.touches.items()) or "none"
        info = f"{ids}  look={game.look_active} fire={game.fire_held} yaw={game.player.yaw:.1f}"
        game.debug_touch_surf = game.font_debug.render(info, True, COL_CYAN)
    screen.blit(game.debug_touch_surf, (10, game.height - 22))


def draw_perf_debug(game):
    if game.debug_perf_surf is None or game.debug_refresh_due:
        fps = game.clock.get_fps()
        game.debug_perf_surf = game.font_debug.render(
            f"FPS {fps:.0f}  render={game.width}x{game.height}  pygame={pygame.version.ver}",
            True, COL_GREEN)
    game.screen.blit(game.debug_perf_surf, (10, 6))


# ===========================================================================
# ENTRY POINT
# ===========================================================================

def main():
    game = Game()
    try:
        game.run()
    except KeyboardInterrupt:
        pass
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
    sys.exit(0)
