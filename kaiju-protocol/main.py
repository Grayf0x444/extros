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
HORIZON_FRAC = 0.62            # horizon sits 62% down the screen
BASE_HEIGHT = 400.0            # kaiju sprite height at dist=100m, pre-scale
KAIJU_WIDTH_RATIO = 0.62       # sprite width as a fraction of its height

ARENA_MIN_DIST = 80.0
ARENA_MAX_DIST = 400.0

LOOK_ZONE_FRAC = 0.40          # left 40% of screen is the look/drag zone
LOOK_SENSITIVITY = 0.25        # deg of yaw per pixel of horizontal drag

FIRE_BTN_RADIUS = 70
DODGE_BTN_RADIUS = 55
BTN_GAP = 24
BTN_MARGIN = 40
BTN_Y_FRAC = 0.80

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
ROAR_MIN_DIST = 200.0             # ROAR only selectable at range

KAIJU_MAX_HP = 1000.0
KAIJU_NAME = "VARANT-CLASS"

COUNTDOWN_TIME = 3.0
KILL_SLOWMO_TIME = 1.5
KILL_SLOWMO_SCALE = 0.3
KILL_HITSTOP = 0.12
PLATE_BREAK_HITSTOP = 0.04
LOSE_DELAY = 0.6

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


def angle_diff(a, b):
    """Shortest signed difference a-b, normalized to -180..180."""
    return (a - b + 180.0) % 360.0 - 180.0


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
        self.tilt = 0.0

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
            game.add_shake(5, 0.15)

    def update(self, dt):
        self.time_since_fire += dt

        if self.dodge_cooldown > 0.0:
            self.dodge_cooldown = max(0.0, self.dodge_cooldown - dt)

        if self.dodging:
            self.dodge_timer += dt
            self.angle += self.dodge_dir * DODGE_ANGLE * (dt / DODGE_DURATION)
            t = clamp(self.dodge_timer / DODGE_DURATION, 0.0, 1.0)
            self.tilt = math.sin(t * math.pi) * 8.0 * self.dodge_dir
            if self.dodge_timer >= DODGE_INVULN:
                self.invulnerable = False
            if self.dodge_timer >= DODGE_DURATION:
                self.dodging = False
                self.tilt = 0.0

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
        self.dist = 300.0
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
        player = game.player
        if self.attack_type in ("SWIPE", "CHARGE"):
            avoided = player.invulnerable
            if self.attack_type == "CHARGE":
                self.dist = clamp(self.dist * CHARGE_CLOSE_FACTOR, ARENA_MIN_DIST, ARENA_MAX_DIST)
            if avoided:
                game.on_dodge_success()
            else:
                dmg = CHARGE_DAMAGE if self.attack_type == "CHARGE" else HIT_DAMAGE
                game.damage_player(dmg)
        elif self.attack_type == "ROAR":
            game.damage_player(HIT_DAMAGE)

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
# CITY -- purely cosmetic parallax silhouette
# ===========================================================================

class Building:
    __slots__ = ("angle", "height", "width", "layer")

    def __init__(self, angle, height, width, layer):
        self.angle = angle
        self.height = height
        self.width = width
        self.layer = layer


def generate_city(count=40, seed=1337):
    rng = random.Random(seed)
    buildings = []
    for _ in range(count):
        layer = 0 if rng.random() < 0.5 else 1
        height = rng.uniform(40, 130) if layer == 0 else rng.uniform(60, 220)
        width = rng.uniform(18, 46) if layer == 0 else rng.uniform(26, 60)
        angle = rng.uniform(0, 360)
        buildings.append(Building(angle, height, width, layer))
    buildings.sort(key=lambda b: b.layer)
    return buildings


LAYER_PARALLAX = (0.45, 0.8)
LAYER_PX_PER_M = (0.9, 1.5)
LAYER_COLOR = (COL_BUILDING_FAR, COL_BUILDING_NEAR)


# ===========================================================================
# GAME
# ===========================================================================

class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("KAIJU PROTOCOL")

        info = pygame.display.Info()
        w, h = info.current_w, info.current_h
        if w <= 0 or h <= 0:
            w, h = DESIGN_W, DESIGN_H
        try:
            self.screen = pygame.display.set_mode((w, h), pygame.FULLSCREEN)
        except pygame.error:
            self.screen = pygame.display.set_mode((DESIGN_W, DESIGN_H))
        self.width, self.height = self.screen.get_size()
        self.center_x = self.width / 2.0
        self.scale = min(self.width / DESIGN_W, self.height / DESIGN_H)
        self.horizon_y = self.height * HORIZON_FRAC

        self.canvas = pygame.Surface((self.width, self.height))
        self.clock = pygame.time.Clock()
        self.running = True

        self._build_fonts()
        self._build_scanlines()
        self._build_layout()
        self.buildings = generate_city()

        self.touches = {}
        self.touch_mode = False

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

    def _build_scanlines(self):
        surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        for y in range(0, self.height, 3):
            pygame.draw.line(surf, (0, 0, 0, 28), (0, y), (self.width, y))
        self.scanline_surf = surf

    def _build_layout(self):
        s = self.scale
        fire_r = FIRE_BTN_RADIUS * s
        dodge_r = DODGE_BTN_RADIUS * s
        gap = BTN_GAP * s
        margin = BTN_MARGIN * s
        by = self.height * BTN_Y_FRAC
        self.fire_btn_pos = (self.width - margin - fire_r, by)
        self.fire_btn_r = fire_r
        dr_x = self.fire_btn_pos[0] - fire_r - gap - dodge_r
        self.dodge_r_pos = (dr_x, by)
        self.dodge_l_pos = (dr_x - dodge_r * 2 - gap, by)
        self.dodge_btn_r = dodge_r

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
        if x < self.width * LOOK_ZONE_FRAC:
            return "look"
        if _dist(x, y, *self.fire_btn_pos) <= self.fire_btn_r:
            return "fire"
        if _dist(x, y, *self.dodge_r_pos) <= self.dodge_btn_r:
            return "dodge_r"
        if _dist(x, y, *self.dodge_l_pos) <= self.dodge_btn_r:
            return "dodge_l"
        return None

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

    def touch_move(self, tid, x, y):
        t = self.touches.get(tid)
        if t is None:
            return
        if t["zone"] == "look":
            dx = x - t["last_x"]
            self.player.yaw = (self.player.yaw + dx * LOOK_SENSITIVITY) % 360.0
        t["last_x"], t["last_y"] = x, y

    def touch_up(self, tid):
        self.touches.pop(tid, None)

    @property
    def fire_held(self):
        return any(t["zone"] == "fire" for t in self.touches.values())

    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            self.running = False
        elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.running = False
        elif hasattr(pygame, "FINGERDOWN") and ev.type == pygame.FINGERDOWN:
            self.touch_mode = True
            self.touch_down(ev.finger_id, ev.x * self.width, ev.y * self.height)
        elif hasattr(pygame, "FINGERMOTION") and ev.type == pygame.FINGERMOTION:
            self.touch_move(ev.finger_id, ev.x * self.width, ev.y * self.height)
        elif hasattr(pygame, "FINGERUP") and ev.type == pygame.FINGERUP:
            self.touch_up(ev.finger_id)
        elif ev.type == pygame.MOUSEBUTTONDOWN and not self.touch_mode:
            self.touch_down("mouse", *ev.pos)
        elif ev.type == pygame.MOUSEMOTION and not self.touch_mode:
            if "mouse" in self.touches:
                self.touch_move("mouse", *ev.pos)
        elif ev.type == pygame.MOUSEBUTTONUP and not self.touch_mode:
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
        cx, cy = self.center_x, self.height / 2.0
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

    def update(self, real_dt):
        real_dt = min(real_dt, 0.05)

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
        c.fill(COL_BG_SKY)
        pygame.draw.rect(c, COL_BG_GROUND, (0, self.horizon_y, self.width, self.height - self.horizon_y))
        pygame.draw.line(c, COL_HORIZON_GLOW, (0, self.horizon_y), (self.width, self.horizon_y), max(1, int(2 * self.scale)))

        draw_city(c, self)
        if self.kaiju_proj is not None and not self.kaiju.dead:
            draw_kaiju(c, self)
        elif self.kaiju_proj is not None and self.kaiju.dead and self.kill_timer is not None:
            draw_kaiju(c, self)

        draw_hud(c, self)

        # compose with screenshake + dash tilt
        final = c
        if self.player.tilt:
            final = pygame.transform.rotate(c, self.player.tilt)
        rect = final.get_rect(center=(self.width / 2.0 + self.shake_x, self.height / 2.0 + self.shake_y))
        self.screen.fill((0, 0, 0))
        self.screen.blit(final, rect)

        if self.white_flash_timer > 0.0:
            a = int(255 * (self.white_flash_timer / 0.3))
            flash = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            flash.fill((255, 255, 255, a))
            self.screen.blit(flash, (0, 0))

        self.screen.blit(self.scanline_surf, (0, 0))
        pygame.display.flip()

    def run(self):
        while self.running:
            real_dt = self.clock.tick(60) / 1000.0
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
        radius = (10 + t * 55) * game.scale
        alpha = int(255 * (1.0 - t))
        burst = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(burst, (255, 255, 255, alpha), (radius, radius), radius, max(2, int(3 * game.scale)))
        bx, by = game.plate_break_pos
        surf.blit(burst, (bx - radius, by - radius))

# ===========================================================================
# DRAWING -- city
# ===========================================================================

def draw_city(surf, game):
    for building in game.buildings:
        rel_raw = angle_diff(building.angle, game.player.yaw)
        if abs(rel_raw) > FOV / 2.0 + 40.0:
            continue
        rel = rel_raw * LAYER_PARALLAX[building.layer]
        screen_x = game.center_x + (rel / (FOV / 2.0)) * (game.width / 2.0)
        px_per_m = LAYER_PX_PER_M[building.layer] * game.scale
        h_px = building.height * px_per_m
        w_px = building.width * px_per_m
        rect = pygame.Rect(screen_x - w_px / 2.0, game.horizon_y - h_px, w_px, h_px)
        pygame.draw.rect(surf, LAYER_COLOR[building.layer], rect)


# ===========================================================================
# DRAWING -- HUD
# ===========================================================================

def draw_hud(surf, game):
    s = game.scale
    w, h = game.width, game.height
    p = game.player
    k = game.kaiju

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
        draw_buttons(surf, game)
        draw_vignette(surf, game)
        draw_spark(surf, game)
    elif game.state == "RESULT":
        draw_result(surf, game)


def draw_top_bar(surf, game):
    s = game.scale
    pad = 20 * s
    label = f"TARGET: {KAIJU_NAME}"
    txt = game.font_small.render(label, True, COL_CYAN)
    surf.blit(txt, (pad, pad))

    dist_m = int(game.kaiju.dist)
    dtxt = game.font_small.render(f"DIST {dist_m}m", True, COL_CYAN)
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
    cx, cy = game.center_x, game.height / 2.0
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
    cx, cy = game.center_x, game.height / 2.0
    t = game.spark_timer / 0.15
    length = 20 * s * t
    for ang in range(0, 360, 45):
        rad = math.radians(ang)
        x1 = cx + math.cos(rad) * 6 * s
        y1 = cy + math.sin(rad) * 6 * s
        x2 = cx + math.cos(rad) * (6 * s + length)
        y2 = cy + math.sin(rad) * (6 * s + length)
        pygame.draw.line(surf, COL_WHITE, (x1, y1), (x2, y2), max(1, int(2 * s)))


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
    ltxt = game.font_tiny.render(label, True, col)
    surf.blit(ltxt, (x, y - ltxt.get_height() - 4 * s))

    if p.overheated and int(pygame.time.get_ticks() * 0.006) % 2 == 0:
        warn = game.font_med.render("OVERHEAT", True, COL_RED)
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

    label = game.font_tiny.render("HULL", True, COL_CYAN)
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
    txt = game.font_huge.render("WARNING", True, COL_RED)
    surf.blit(txt, (game.center_x - txt.get_width() / 2, game.height * 0.22))


def draw_dodge_flash(surf, game):
    if game.dodge_flash_timer <= 0.0:
        return
    a = int(255 * (game.dodge_flash_timer / 0.5))
    txt = game.font_med.render("DODGED", True, COL_GREEN)
    txt.set_alpha(a)
    surf.blit(txt, (game.center_x - txt.get_width() / 2, game.height * 0.38))


def draw_buttons(surf, game):
    s = game.scale
    p = game.player

    def circle(pos, radius, label, active, color):
        overlay = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        alpha = 140 if active else 70
        pygame.draw.circle(overlay, (*color, alpha), (radius, radius), radius)
        pygame.draw.circle(overlay, (*color, 220), (radius, radius), radius, max(2, int(2 * s)))
        surf.blit(overlay, (pos[0] - radius, pos[1] - radius))
        txt = game.font_small.render(label, True, COL_WHITE)
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
    a = int(160 * (game.vignette_timer / 0.4))
    w, h = game.width, game.height
    edge = int(min(w, h) * 0.18)
    overlay = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(edge):
        alpha = int(a * (1.0 - i / edge))
        col = (*COL_RED, alpha)
        pygame.draw.rect(overlay, col, (0, i, w, 1))
        pygame.draw.rect(overlay, col, (0, h - i - 1, w, 1))
        pygame.draw.rect(overlay, col, (i, 0, 1, h))
        pygame.draw.rect(overlay, col, (w - i - 1, 0, 1, h))
    surf.blit(overlay, (0, 0))


def draw_countdown(surf, game):
    s = game.scale
    draw_city(surf, game)
    if game.kaiju_proj is None:
        game.compute_kaiju_projection()
    if game.kaiju_proj is not None:
        draw_kaiju(surf, game)

    t = game.countdown_timer
    n = int(math.ceil(t))
    n = max(1, min(3, n))
    txt = game.font_huge.render(str(n), True, COL_CYAN)
    surf.blit(txt, (game.center_x - txt.get_width() / 2, game.height * 0.4))

    boot = game.font_small.render("SYSTEMS ONLINE", True, COL_GREEN)
    surf.blit(boot, (game.center_x - boot.get_width() / 2, game.height * 0.4 + txt.get_height()))


def draw_result(surf, game):
    draw_city(surf, game)
    if game.kaiju_proj is not None:
        draw_kaiju(surf, game)

    w, h = game.width, game.height
    overlay = pygame.Surface((w, h), pygame.SRCALPHA)
    overlay.fill((5, 10, 12, 190))
    surf.blit(overlay, (0, 0))

    s = game.scale
    cx = game.center_x
    y = h * 0.22

    if game.result_kind == "WIN":
        title = f"{KAIJU_NAME} — DOWN"
        col = COL_CYAN
    else:
        title = "MECH DOWN"
        col = COL_RED

    t_txt = game.font_big.render(title, True, col)
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
        ltxt = game.font_med.render(label, True, COL_CYAN_DIM)
        vtxt = game.font_med.render(value, True, COL_WHITE)
        surf.blit(ltxt, (cx - 160 * s, y))
        surf.blit(vtxt, (cx + 40 * s, y))
        y += ltxt.get_height() + 10 * s

    y += 30 * s
    flash = (math.sin(pygame.time.get_ticks() * 0.004) + 1.0) * 0.5
    prompt_col = tuple(int(lerp(COL_CYAN_DIM[i], COL_CYAN[i], flash)) for i in range(3))
    prompt = game.font_med.render("[ TAP TO RETRY ]", True, prompt_col)
    surf.blit(prompt, (cx - prompt.get_width() / 2, y))


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
