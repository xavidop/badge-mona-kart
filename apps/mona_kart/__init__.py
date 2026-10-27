"""
Mona Kart: a pseudo-3D kart race against five rival Octocats, three laps to the flag.

Steer by tilting the badge or with Left and Right, grab coffee for a boost,
dodge the bugs, and set a best lap that the badge remembers.

Controls:
* Tilt or Left / Right = Steer
* Select = Start, and accelerate during the race
* Back = Brake
* Menu = Switch between tilt and button steering on the title screen
"""

import math
import micropython
import os
import random
import sys

from badgeware import State

APP_DIR = "/system/apps/mona_kart"
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

badge.mode(HIRES | VSYNC)
screen.antialias = image.OFF

WIDTH, HEIGHT = screen.width, screen.height
HORIZON = 104              # where the road meets the sky
HALF_W = WIDTH / 2

# the world: segments of road, a camera above the kart, a far draw distance
SEG_LEN = 200
ROAD_W = 1000              # half the road, in world units
CAM_H = 1000
CAM_DEPTH = 0.84
PLAYER_Z = 740             # the camera sits this far behind the kart
HALF_H = HEIGHT / 2
DRAW_DIST = 48
NEAR_STEPS = 4             # the nearest segments are split so their edges follow the perspective
NEAR_SEGMENTS = 3
RUMBLE_EVERY = 3           # segments per rumble stripe
LANE_W = 0.03

MAX_SPEED = SEG_LEN * 60.0
ACCEL = MAX_SPEED / 1.8
BRAKE = -MAX_SPEED
COAST = -MAX_SPEED / 5
OFFROAD_DECEL = -MAX_SPEED / 1.6
OFFROAD_LIMIT = MAX_SPEED / 4
CENTRIFUGAL = 0.32
STEER_RATE = 1.9
BOOST_MS = 1800
BOOST_FACTOR = 1.35
BUG_FACTOR = 0.45
BUMP_FACTOR = 0.6
LAPS = 3
RIVALS = 5
COUNTDOWN_MS = 3200
GRAVITY = 16384.0

# sprite sheets: karts are 24x19 per frame (left, straight, right) per colour
KART_W, KART_H = 24, 19
PROP_W, PROP_H = 18, 14
TREE, BUSH, SIGN, COFFEE, BUG = 0, 1, 2, 3, 4

KARTS = image.load("assets/karts.png").spritesheet(3, 6)
PROPS = image.load("assets/props.png").spritesheet(5, 1)
PLAYER_SCALE = 3

SKY_TOP = color.rgb(72, 150, 240)
SKY_LOW = color.rgb(150, 210, 250)
SUN = color.rgb(255, 236, 120)
HILL_FAR = color.rgb(60, 120, 90)
HILL_NEAR = color.rgb(40, 100, 70)
CLOUD = color.rgb(255, 255, 255)
GRASS = (color.rgb(72, 160, 72), color.rgb(60, 140, 60))
RUMBLE = (color.rgb(230, 230, 230), color.rgb(220, 50, 50))
ROAD = (color.rgb(104, 104, 116), color.rgb(96, 96, 108))
LANE = color.rgb(230, 230, 230)
START = (color.rgb(240, 240, 240), color.rgb(30, 30, 40))
INK = color.rgb(20, 20, 32)
CREAM = color.rgb(240, 232, 208)
AMBER = color.rgb(255, 200, 48)
RED = color.rgb(220, 60, 60)
GREEN = color.rgb(96, 208, 96)
PANEL = color.rgb(20, 20, 32, 190)
SHADOW = color.rgb(0, 0, 0, 90)

TITLE = font.futile
BIG = font.ignore
BODY = font.nope
SMALL = font.sins

ORDINALS = ("1ST", "2ND", "3RD", "4TH", "5TH", "6TH")

TITLE_SCREEN, COUNTDOWN, RACE, FINISH = 0, 1, 2, 3

state = {"best_lap": 0, "best_race": 0, "wins": 0, "tilt": True}
State.load("mona_kart", state)
for key, kind in (("best_lap", int), ("best_race", int), ("wins", int)):
    if not isinstance(state.get(key), int) or state[key] < 0:
        state[key] = 0
state["tilt"] = bool(state.get("tilt", True))


def save_state():
    try:
        State.save("mona_kart", state)
    except OSError as error:
        print("Mona Kart: could not save:", error)


# ----------------------------------------------------------------------------
# the track: parallel lists, one entry per segment

curve = []        # curvature added per segment
hill = []         # world y at the segment's near edge
props = []        # per segment: list of (offset, prop index) roadside objects
items = []        # per segment: [offset, kind] or None, for coffee and bugs
clip = []         # per segment: the lowest screen y still visible past it, set each frame


def ease_in(a, b, t):
    return a + (b - a) * t * t


def ease_out(a, b, t):
    return a + (b - a) * (1 - (1 - t) * (1 - t))


def ease_in_out(a, b, t):
    return a + (b - a) * ((-math.cos(t * math.pi) / 2) + 0.5)


def add_road(enter, hold, leave, bend, height):
    """Segments that ease into a bend and a hill, hold them, then ease out."""
    start_y = hill[-1] if hill else 0.0
    end_y = start_y + height * SEG_LEN
    total = enter + hold + leave
    for n in range(enter):
        curve.append(ease_in(0, bend, n / enter))
        hill.append(ease_in_out(start_y, end_y, n / total))
    for n in range(hold):
        curve.append(bend)
        hill.append(ease_in_out(start_y, end_y, (enter + n) / total))
    for n in range(leave):
        curve.append(ease_in_out(bend, 0, n / leave))
        hill.append(ease_in_out(start_y, end_y, (enter + hold + n) / total))


def build_track():
    random.seed(7)
    add_road(0, 40, 0, 0, 0)
    add_road(20, 40, 20, -3, 0)
    add_road(20, 30, 20, 0, 12)
    add_road(20, 40, 20, 4, -6)
    add_road(10, 60, 10, 0, 0)
    add_road(20, 50, 20, -5, 8)
    add_road(20, 30, 20, 5, 0)
    add_road(20, 20, 20, -4, -14)
    add_road(10, 50, 10, 0, 0)
    add_road(20, 60, 20, 2, 10)
    add_road(20, 40, 20, -6, -10)
    add_road(10, 40, 10, 0, 0)
    # level the end with the start so the loop closes without a step
    close = len(curve)
    for n in range(close):
        hill[n] -= hill[-1] * n / close
    for n in range(close):
        props.append([])
        items.append(None)
    for n in range(10, close, 7):
        side = -1 if n % 2 else 1
        kind = TREE if n % 3 else BUSH
        props[n].append((side * (1.6 + (n % 5) * 0.25), kind))
    for n in range(24, close, 38):
        props[n].append((-1.5 if n % 2 else 1.5, SIGN))
    for n in range(60, close, 90):
        items[n] = [random.choice((-0.5, 0.0, 0.5)), COFFEE]
    for n in range(110, close, 115):
        items[n] = [random.choice((-0.6, -0.2, 0.2, 0.6)), BUG]
    return close


SEGMENTS = build_track()
TRACK_LEN = SEGMENTS * SEG_LEN
clip = [HEIGHT] * SEGMENTS


# ----------------------------------------------------------------------------
# racers

class Kart:
    def __init__(self, colour, z, x, speed_factor):
        self.colour = colour
        self.z = z
        self.x = x
        self.speed = 0.0
        self.factor = speed_factor
        self.lap = 0
        self.finished_at = None
        self.target_x = x
        self.wobble = random.random() * 6

    @property
    def progress(self):
        return self.lap * TRACK_LEN + self.z

    def advance(self, dt):
        self.z += self.speed * dt
        if self.z >= TRACK_LEN:
            self.z -= TRACK_LEN
            self.lap += 1
            return True
        return False


player = None
rivals = []
mode = TITLE_SCREEN
countdown_at = 0
race_at = 0
race_time = 0
lap_started = 0
lap_times = []
boost_until = 0
hit_until = 0
steer = 0.0
view_skew = 0.0
rows = []               # per drawn segment: (x, dx, scale, screen x, screen y, half width)
sun_x = 60
message = ""
message_until = 0
final_rank = 1


def start_race():
    global player, rivals, mode, countdown_at, race_time, lap_times, boost_until, hit_until, lap_started, message
    player = Kart(0, SEG_LEN * 4, 0.0, 1.0)
    rivals = []
    for n in range(RIVALS):
        lane = (-0.6, 0.6, -0.3, 0.3, 0.0)[n]
        rivals.append(Kart(n + 1, SEG_LEN * (6 + n * 2), lane, 0.70 + n * 0.035))
    mode = COUNTDOWN
    countdown_at = badge.ticks
    race_time = 0
    lap_times = []
    lap_started = 0
    boost_until = 0
    hit_until = 0
    message = ""


# ----------------------------------------------------------------------------
# input

def read_steer():
    """Steering in -1..1: buttons always work, tilt when it is switched on."""
    value = 0.0
    if badge.held(BUTTON_LEFT):
        value -= 1.0
    if badge.held(BUTTON_RIGHT):
        value += 1.0
    if value == 0.0 and state["tilt"]:
        try:
            ax = badge.imu()[0]
        except (OSError, TypeError, IndexError):
            ax = 0
        value = max(-1.0, min(1.0, -ax / GRAVITY * 2.5))
        if abs(value) < 0.08:
            value = 0.0
    return value


# ----------------------------------------------------------------------------
# simulation

def segment_at(z):
    return int(z // SEG_LEN) % SEGMENTS


def update_player(dt):
    global steer, boost_until, hit_until, lap_started, race_time, mode, message, message_until, final_rank
    now = badge.ticks
    steer = read_steer()
    boosting = now < boost_until
    hit = now < hit_until
    limit = MAX_SPEED * (BOOST_FACTOR if boosting else 1.0)
    if abs(player.x) > 1.0:
        limit = min(limit, OFFROAD_LIMIT) if not boosting else limit * 0.7

    if boosting:
        player.speed = min(limit, player.speed + ACCEL * 2 * dt)
    elif badge.held(BUTTON_BACK):
        player.speed += BRAKE * dt
    else:
        player.speed += ACCEL * dt
    if abs(player.x) > 1.0 and player.speed > OFFROAD_LIMIT and not boosting:
        player.speed += OFFROAD_DECEL * dt
    player.speed = max(0.0, min(limit, player.speed))

    seg = segment_at(player.z)
    before = seg
    speed_pct = player.speed / MAX_SPEED
    dx = dt * STEER_RATE * speed_pct
    player.x += steer * dx * (0.5 if hit else 1.0)
    player.x -= dx * speed_pct * curve[seg] * CENTRIFUGAL
    player.x = max(-2.2, min(2.2, player.x))

    # rivals in the way
    for rival in rivals:
        gap = (rival.z - player.z) % TRACK_LEN
        if gap < SEG_LEN * 1.2 and abs(rival.x - player.x) < 0.45 and player.speed > rival.speed:
            player.speed = rival.speed * BUMP_FACTOR
            player.x += 0.08 if player.x > rival.x else -0.08
    lapped = player.advance(dt)
    # coffee and bugs on every segment crossed this frame
    crossed = (segment_at(player.z) - before) % SEGMENTS
    for k in range(crossed + 1):
        index = (before + k) % SEGMENTS
        item = items[index]
        if item is not None and abs(item[0] - player.x) < 0.35:
            if item[1] == COFFEE:
                boost_until = now + BOOST_MS
                message, message_until = "COFFEE BOOST!", now + 1200
            else:
                player.speed *= BUG_FACTOR
                hit_until = now + 900
                message, message_until = "BUG!", now + 900
            items[index] = None

    if lapped:
        lap_time = now - lap_started
        lap_times.append(lap_time)
        if state["best_lap"] == 0 or lap_time < state["best_lap"]:
            state["best_lap"] = lap_time
            message, message_until = "BEST LAP!", now + 1500
        lap_started = now
        if player.lap >= LAPS:
            finish()


def update_rivals(dt):
    behind = 0
    for rival in rivals:
        rival.wobble += dt
        # rubber banding keeps the pack close: slower when ahead, faster when behind
        gap = rival.progress - player.progress
        factor = rival.factor + (0.18 if gap < -TRACK_LEN * 0.05 else (-0.16 if gap > TRACK_LEN * 0.06 else 0.0))
        rival.speed += (MAX_SPEED * factor - rival.speed) * min(1.0, dt * 0.8)
        rival.x += (rival.target_x + math.sin(rival.wobble * 0.7) * 0.15 - rival.x) * min(1.0, dt * 2)
        if random.random() < dt * 0.15:
            rival.target_x = random.choice((-0.6, -0.3, 0.0, 0.3, 0.6))
        rival.advance(dt)
        if rival.progress < player.progress:
            behind += 1
    return behind


def rank():
    ahead = 0
    for rival in rivals:
        if rival.progress > player.progress:
            ahead += 1
    return ahead + 1


def finish():
    global mode, race_time, final_rank
    final_rank = rank()
    race_time = badge.ticks - race_at
    if final_rank == 1:
        state["wins"] += 1
    if state["best_race"] == 0 or race_time < state["best_race"]:
        state["best_race"] = race_time
    save_state()
    mode = FINISH


# ----------------------------------------------------------------------------
# drawing

def fill(x, y, w, h, pen):
    screen.pen = pen
    screen.rectangle(x, y, w, h)


def write(text, x, y, pen, face=BODY):
    screen.font = face
    screen.pen = pen
    screen.text(text, x, y)


def text_width(text, face=BODY):
    screen.font = face
    return screen.measure_text(text)[0]


def write_centred(text, cx, y, pen, face=BODY):
    write(text, cx - text_width(text, face) // 2, y, pen, face)


def write_shadowed(text, cx, y, pen, face=BODY):
    write_centred(text, cx + 2, y + 2, INK, face)
    write_centred(text, cx, y, pen, face)


def clock(ms):
    return "%d:%02d.%d" % (ms // 60000, (ms // 1000) % 60, (ms // 100) % 10)


def draw_sky(skew):
    fill(0, 0, WIDTH, HORIZON // 2, SKY_TOP)
    fill(0, HORIZON // 2, WIDTH, HORIZON - HORIZON // 2, SKY_LOW)
    screen.pen = SUN
    screen.shape(shape.circle(int(sun_x - skew * 0.2) % (WIDTH + 80) - 40, 34, 16))
    for n in range(3):
        cx = (60 + n * 130 - int(skew * 0.35) - int(race_time * 0.004)) % (WIDTH + 60) - 30
        fill(cx, 44 + n * 9, 34, 7, CLOUD)
        fill(cx + 8, 39 + n * 9, 18, 6, CLOUD)
    screen.pen = HILL_FAR
    for n in range(5):
        screen.shape(shape.circle((n * 90 - int(skew * 0.6)) % (WIDTH + 100) - 50, HORIZON + 10, 42))
    screen.pen = HILL_NEAR
    for n in range(4):
        screen.shape(shape.circle((50 + n * 110 - int(skew * 0.9)) % (WIDTH + 100) - 50, HORIZON + 18, 34))


@micropython.viper
def span_rows(bottom: int, top: int, y1: int, y2: int, sx1: int, sx2: int, w1: int, w2: int, lane: int, road_pen, rumble_pen, lane_pen):
    """Span the road rows between two projected edges; positions are 1/256 px."""
    span = y1 - y2
    if span <= 0:
        return
    scr = screen
    y = bottom - 1
    while y >= top:
        t = ((y - y2) << 8) // span
        cx = sx2 + (((sx1 - sx2) * t) >> 8)
        w = w2 + (((w1 - w2) * t) >> 8)
        r = (w * 23) >> 8
        if r < 256:
            r = 256
        scr.pen = rumble_pen
        scr.hspan((cx - w - r) >> 8, y, r >> 8)
        scr.hspan((cx + w) >> 8, y, r >> 8)
        scr.pen = road_pen
        scr.hspan((cx - w) >> 8, y, (2 * w) >> 8)
        if lane:
            lw = (w * 8) >> 8
            if lw < 256:
                lw = 256
            scr.pen = lane_pen
            scr.hspan((cx - lw) >> 8, y, (2 * lw) >> 8)
        y -= 1


def draw_road():
    """The classic pseudo-3D road: project each segment and span the rows between.

    Fills `rows` with every segment's projection so sprites can reuse it, and
    keeps the curve ahead in `view_skew` for the sky's parallax. The nearest
    segments are walked in quarter steps so their edges bend with the
    perspective instead of showing a kink.
    """
    global view_skew
    base = segment_at(player.z)
    base_pct = (player.z % SEG_LEN) / SEG_LEN
    cam_y = CAM_H + hill[base] + (hill[(base + 1) % SEGMENTS] - hill[base]) * base_pct
    cam_x = player.x * ROAD_W
    maxy = HEIGHT
    x = 0.0
    dx = -curve[base] * base_pct
    skew = 0.0
    del rows[:]
    for n in range(DRAW_DIST):
        index = (base + n) % SEGMENTS
        nxt = (index + 1) % SEGMENTS
        bend = curve[index]
        z1 = n * SEG_LEN - base_pct * SEG_LEN + PLAYER_Z
        scale1 = CAM_DEPTH / z1
        sx1 = HALF_W + scale1 * (x - cam_x) * HALF_W
        y1 = int(HORIZON - scale1 * (hill[index] - cam_y) * HALF_H)
        w1 = scale1 * ROAD_W * HALF_W
        rows.append((x, dx, scale1, sx1, y1, w1))
        if n < 12:
            skew += bend
        clip[index] = maxy
        stripe = (index // RUMBLE_EVERY) % 2
        road_pen = START[stripe] if index < 2 else ROAD[stripe]
        lane = 1 if (stripe == 0 and index > 2) else 0
        steps = NEAR_STEPS if n < NEAR_SEGMENTS else 1
        # walk the segment in steps, projecting each step's far edge
        ya = y1
        sxa = sx1
        wa = w1
        for k in range(1, steps + 1):
            f = k / steps
            zb = z1 + SEG_LEN * f
            scale2 = CAM_DEPTH / zb
            xb = x + dx * f + bend * f * f / 2
            sxb = HALF_W + scale2 * (xb - cam_x) * HALF_W
            yb = int(HORIZON - scale2 * (hill[index] + (hill[nxt] - hill[index]) * f - cam_y) * HALF_H)
            wb = scale2 * ROAD_W * HALF_W
            if yb < maxy and ya > yb:
                top = max(yb, HORIZON - 40)
                bottom = min(ya, maxy)
                fill(0, top, WIDTH, bottom - top, GRASS[stripe])
                span_rows(bottom, top, ya, yb, int(sxa * 256), int(sxb * 256), int(wa * 256), int(wb * 256), lane, road_pen, RUMBLE[stripe], LANE)
                maxy = yb
            ya, sxa, wa = yb, sxb, wb
        x += dx
        dx += bend
    view_skew = skew


def draw_sprite(sprite, sx, sy, size, clip_y):
    """A sprite scaled to `size` wide, its feet at sy, hidden below clip_y."""
    if size < 2 or sy < HORIZON - 60:
        return
    height = int(size * sprite.height / sprite.width)
    top = sy - height
    if top >= clip_y:
        return
    screen.clip = rect(0, 0, WIDTH, clip_y)
    screen.blit(sprite, rect(0, 0, sprite.width, sprite.height), rect(int(sx - size / 2), top, int(size), height), image.NEAREST)
    screen.clip = rect(0, 0, WIDTH, HEIGHT)


def draw_scene_sprites():
    """Props, items and rivals from far to near so nearer ones cover farther ones."""
    base = segment_at(player.z)
    base_pct = (player.z % SEG_LEN) / SEG_LEN
    cam_y = CAM_H + hill[base] + (hill[(base + 1) % SEGMENTS] - hill[base]) * base_pct
    cam_x = player.x * ROAD_W
    order = []
    for n in range(len(rows)):
        index = (base + n) % SEGMENTS
        if props[index] or items[index] is not None:
            order.append((n, None))
    for rival in rivals:
        gap = (rival.z - player.z) % TRACK_LEN
        n = int(gap // SEG_LEN)
        if 1 <= n < len(rows):
            order.append((n + (gap % SEG_LEN) / SEG_LEN, rival))
    order.sort(key=lambda entry: -entry[0])
    for depth, rival in order:
        n = int(depth)
        index = (base + n) % SEGMENTS
        x, dx, scale, sx, sy, w = rows[n]
        if rival is None:
            for offset, prop in props[index]:
                draw_sprite(PROPS.sprite(prop, 0), sx + offset * w, sy, w * 0.45, clip[index])
            item = items[index]
            if item is not None:
                draw_sprite(PROPS.sprite(item[1], 0), sx + item[0] * w, sy, w * 0.3, clip[index])
        else:
            # the rival sits part way along its segment: project that exact spot
            frac = depth - n
            z = n * SEG_LEN - base_pct * SEG_LEN + PLAYER_Z + frac * SEG_LEN
            scale = CAM_DEPTH / z
            y_world = hill[index] + (hill[(index + 1) % SEGMENTS] - hill[index]) * frac
            ry = int(HORIZON - scale * (y_world - cam_y) * HALF_H)
            rx = HALF_W + scale * (x + dx * frac + rival.x * ROAD_W - cam_x) * HALF_W
            size = scale * ROAD_W * HALF_W * 0.33
            bend = curve[index]
            frame = 0 if bend < -1 else (2 if bend > 1 else 1)
            draw_sprite(KARTS.sprite(frame, rival.colour), rx, ry, size, clip[index])


def draw_player():
    frame = 1 if abs(steer) < 0.25 else (0 if steer < 0 else 2)
    bounce = 0
    if abs(player.x) > 1.0 and player.speed > 0:
        bounce = int(badge.ticks // 60) % 2 * 2
    if badge.ticks < hit_until:
        bounce = int(badge.ticks // 40) % 3
    size = KART_W * PLAYER_SCALE
    x = int(HALF_W - size / 2)
    y = HEIGHT - 20 - KART_H * PLAYER_SCALE + bounce
    fill(x + 6, y + KART_H * PLAYER_SCALE - 6, size - 12, 6, SHADOW)
    screen.blit(KARTS.sprite(frame, 0), rect(0, 0, KART_W, KART_H), rect(x, y, size, KART_H * PLAYER_SCALE), image.NEAREST)
    if badge.ticks < boost_until:
        flame = int(badge.ticks // 50) % 2
        fill(x + 10, y + KART_H * PLAYER_SCALE - 10, 10, 6 + flame * 4, AMBER)
        fill(x + size - 20, y + KART_H * PLAYER_SCALE - 10, 10, 6 + flame * 4, AMBER)


def draw_hud():
    fill(0, 0, WIDTH, 22, PANEL)
    write("LAP %d/%d" % (min(player.lap + 1, LAPS), LAPS), 8, 5, CREAM, BODY)
    write_centred(ORDINALS[rank() - 1], HALF_W, 2, AMBER, TITLE)
    elapsed = race_time if mode == FINISH else (badge.ticks - race_at if mode == RACE else 0)
    write(clock(elapsed), WIDTH - 8 - text_width(clock(elapsed), BODY), 5, CREAM, BODY)
    # the speed bar down the right edge
    pct = player.speed / (MAX_SPEED * BOOST_FACTOR)
    fill(WIDTH - 14, 60, 8, 120, PANEL)
    fill(WIDTH - 13, 61 + int(118 * (1 - pct)), 6, int(118 * pct), AMBER if badge.ticks < boost_until else GREEN)
    if message and badge.ticks < message_until:
        write_shadowed(message, HALF_W, 60, AMBER, TITLE)


def draw_race():
    draw_sky(view_skew * 40 + player.x * 20)
    draw_road()
    draw_scene_sprites()
    draw_player()
    draw_hud()


def draw_title():
    draw_sky(0)
    fill(0, HORIZON, WIDTH, HEIGHT - HORIZON, GRASS[0])
    for y in range(HORIZON, HEIGHT):
        t = (y - HORIZON) / (HEIGHT - HORIZON)
        w = int(20 + 140 * t)
        screen.pen = ROAD[(y // 8) % 2]
        screen.hspan(int(HALF_W - w), y, 2 * w)
    size = KART_W * 4
    screen.blit(KARTS.sprite(1, 0), rect(0, 0, KART_W, KART_H), rect(int(HALF_W - size / 2), 140, size, KART_H * 4), image.NEAREST)
    write_shadowed("MONA KART", HALF_W, 30, AMBER, BIG)
    write_shadowed("3 LAPS - 5 RIVALS - 1 FLAG", HALF_W, 62, CREAM, SMALL)
    if (badge.ticks // 400) % 2:
        write_shadowed("SELECT TO RACE", HALF_W, 100, CREAM, BODY)
    write_shadowed("MENU: STEER BY %s" % ("TILT" if state["tilt"] else "BUTTONS"), HALF_W, 118, CREAM, SMALL)
    if state["best_lap"]:
        write_shadowed("BEST LAP %s   WINS %d" % (clock(state["best_lap"]), state["wins"]), HALF_W, 222, AMBER, SMALL)


def draw_countdown():
    draw_race()
    left = COUNTDOWN_MS - (badge.ticks - countdown_at)
    label = "GO!" if left <= 200 else str(min(3, left // 1000 + 1))
    write_shadowed(label, HALF_W, 90, AMBER if label == "GO!" else CREAM, BIG)


def draw_finish():
    draw_race()
    fill(30, 40, WIDTH - 60, 160, PANEL)
    write_shadowed("YOU FINISHED %s" % ORDINALS[final_rank - 1], HALF_W, 50, AMBER if final_rank == 1 else CREAM, TITLE)
    write_centred("RACE TIME %s" % clock(race_time), HALF_W, 84, CREAM, BODY)
    for n, lap_time in enumerate(lap_times[:LAPS]):
        best = lap_time == min(lap_times)
        write_centred("LAP %d  %s%s" % (n + 1, clock(lap_time), "  *" if best else ""), HALF_W, 104 + n * 16, AMBER if best else CREAM, SMALL)
    write_centred("BEST LAP EVER %s" % clock(state["best_lap"]), HALF_W, 156, CREAM, SMALL)
    if (badge.ticks // 400) % 2:
        write_centred("SELECT: RACE AGAIN   BACK: TITLE", HALF_W, 180, CREAM, SMALL)


# ----------------------------------------------------------------------------
# frame loop

def update():
    global mode, race_at, lap_started, race_time
    dt = min(badge.ticks_delta, 80) / 1000
    if mode == TITLE_SCREEN:
        if badge.pressed(BUTTON_MENU):
            state["tilt"] = not state["tilt"]
            save_state()
        if badge.pressed(BUTTON_SELECT):
            start_race()
        draw_title()
    elif mode == COUNTDOWN:
        if badge.ticks - countdown_at >= COUNTDOWN_MS:
            mode = RACE
            race_at = badge.ticks
            lap_started = race_at
        draw_countdown()
    elif mode == RACE:
        race_time = badge.ticks - race_at
        update_player(dt)
        update_rivals(dt)
        draw_race()
    else:
        update_rivals(dt)
        player.speed = max(0.0, player.speed - MAX_SPEED * dt)
        player.advance(dt)
        if badge.pressed(BUTTON_SELECT):
            start_race()
        elif badge.pressed(BUTTON_BACK):
            mode = TITLE_SCREEN
        draw_finish()


def on_exit():
    save_state()


run(update)
