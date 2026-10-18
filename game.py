"""Desktop Terraria - a small Terraria recreation that plays out on top of your own desktop.

Art and sounds are loaded from your local Terraria install (exported by tools/XnbExport.exe).
Physics constants mirror Terraria's player defaults (gravity 0.4, jumpSpeed 5.01, jumpHeight 15,
maxRunSpeed 3, runAcceleration 0.08, runSlowdown 0.2, maxFallSpeed 10).
"""
import io
import math
import os
import random
import struct
import sys

import desktop

desktop.set_dpi_aware()
os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "0,0")
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import numpy as np
import pygame

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
from find_terraria import find_terraria

TERRARIA = find_terraria() or ""
TS = 16

# ----------------------------------------------------------------------------- tiles
AIR, DIRT, STONE, GRASS, COPPER, IRON, GOLD, WOOD, PLATFORM, TORCH, TRUNK, PLANT = range(12)
SOLID = {DIRT, STONE, GRASS, COPPER, IRON, GOLD, WOOD}
EARTH = {DIRT, STONE, GRASS, COPPER, IRON, GOLD}
DECO = {TORCH, TRUNK, PLANT}
SOLID_LUT = np.zeros(256, bool)
for _t in SOLID:
    SOLID_LUT[_t] = True
TILE_SHEET = {DIRT: "Tiles_0", STONE: "Tiles_1", GRASS: "Tiles_2", COPPER: "Tiles_7", IRON: "Tiles_6",
              GOLD: "Tiles_8", WOOD: "Tiles_30"}
TILE_HITS = {DIRT: 2, GRASS: 1, STONE: 3, COPPER: 4, IRON: 4, GOLD: 5, WOOD: 2, PLATFORM: 1, TORCH: 1, PLANT: 1}
TILE_DROP = {DIRT: "dirt", GRASS: "dirt", STONE: "stone", COPPER: "copper_ore", IRON: "iron_ore",
             GOLD: "gold_ore", WOOD: "wood", PLATFORM: "platform", TORCH: "torch"}
TINK = {STONE, COPPER, IRON, GOLD}

ITEMS = {
    "copper_sword": dict(name="Copper Broadsword", tex="Item_3508", kind="sword", use=20, dmg=8, kb=5, stack=1),
    "copper_pickaxe": dict(name="Copper Pickaxe", tex="Item_3509", kind="pick", use=15, dmg=4, kb=2, stack=1),
    "copper_axe": dict(name="Copper Axe", tex="Item_3506", kind="axe", use=21, dmg=3, kb=4, stack=1),
    "dirt": dict(name="Dirt Block", tex="Item_2", kind="tile", place=DIRT),
    "stone": dict(name="Stone Block", tex="Item_3", kind="tile", place=STONE),
    "wood": dict(name="Wood", tex="Item_9", kind="tile", place=WOOD),
    "copper_ore": dict(name="Copper Ore", tex="Item_12", kind="tile", place=COPPER),
    "iron_ore": dict(name="Iron Ore", tex="Item_11", kind="tile", place=IRON),
    "gold_ore": dict(name="Gold Ore", tex="Item_13", kind="tile", place=GOLD),
    "torch": dict(name="Torch", tex="Item_8", kind="tile", place=TORCH),
    "platform": dict(name="Wood Platform", tex="Item_94", kind="tile", place=PLATFORM),
    "gel": dict(name="Gel", tex="Item_23", kind="material", tint=(110, 160, 255)),
}
RECIPES = [("torch", 3, [("gel", 1), ("wood", 1)]),
           ("platform", 2, [("wood", 1)]),
           ("copper_sword", 1, [("copper_ore", 8)])]

SKIN = (255, 125, 90); EYE = (105, 90, 75); HAIR = (215, 90, 55)
SHIRT = (175, 165, 140); UNDER = (160, 180, 215); PANTS = (255, 230, 175); SHOES = (160, 105, 60)

# Terraria player defaults
GRAVITY, MAX_FALL, JUMP_SPEED, JUMP_HEIGHT = 0.4, 10.0, 5.01, 15
MAX_RUN, RUN_ACCEL, RUN_SLOW = 3.0, 0.08, 0.2
PW, PH = 20, 42


# ----------------------------------------------------------------------------- assets
_img_cache = {}


def img(name):
    if name not in _img_cache:
        path = os.path.join(ASSETS, "Images_" + name + ".png")
        _img_cache[name] = pygame.image.load(path).convert_alpha()
    return _img_cache[name]


def tinted(surf, color, alpha=255):
    s = surf.copy()
    s.fill(tuple(color) + (alpha,), special_flags=pygame.BLEND_RGBA_MULT)
    return s


def load_xnb_sound(path):
    """Parse an uncompressed XNA SoundEffect .xnb into a pygame Sound."""
    try:
        b = open(path, "rb").read()
        if b[:3] != b"XNB" or b[5] & 0x80:
            return None
        p = 10

        def r7():
            nonlocal p
            v = s = 0
            while True:
                c = b[p]; p += 1
                v |= (c & 0x7F) << s; s += 7
                if not c & 0x80:
                    return v
        for _ in range(r7()):
            n = r7()
            p += n + 4
        r7(); r7()
        fl = struct.unpack_from("<I", b, p)[0]; p += 4
        fmt = b[p:p + fl]; p += fl
        dl = struct.unpack_from("<I", b, p)[0]; p += 4
        data = b[p:p + dl]
        wav = (b"RIFF" + struct.pack("<I", 4 + 8 + fl + 8 + dl) + b"WAVE" + b"fmt " + struct.pack("<I", fl) + fmt
               + b"data" + struct.pack("<I", dl) + data)
        return pygame.mixer.Sound(file=io.BytesIO(wav))
    except Exception:
        return None


class Sounds:
    def __init__(self):
        self.s = {}
        names = ["Dig_0", "Dig_1", "Dig_2", "Tink_0", "Tink_1", "Tink_2", "Grab", "Item_1", "NPC_Hit_1",
                 "NPC_Killed_1", "Player_Hit_0", "Player_Hit_1", "Player_Hit_2", "Player_Killed", "Menu_Open",
                 "Menu_Close", "Menu_Tick", "Shatter", "Item_8", "Item_7"]
        if pygame.mixer.get_init():
            for n in names:
                snd = load_xnb_sound(os.path.join(TERRARIA, "Content", "Sounds", n + ".xnb"))
                if snd:
                    snd.set_volume(0.45)
                    self.s[n] = snd

    def play(self, name, *alts):
        choices = [n for n in (name,) + alts if n in self.s]
        if choices:
            self.s[random.choice(choices)].play()

    def dig(self):
        self.play("Dig_0", "Dig_1", "Dig_2")

    def tink(self):
        self.play("Tink_0", "Tink_1", "Tink_2")


# ----------------------------------------------------------------------------- text
class Text:
    def __init__(self):
        name = pygame.font.match_font("andy,segoeuisemibold,segoeui,arial", bold=True)
        self.fonts = {sz: pygame.font.Font(name, sz) for sz in (14, 16, 20, 28, 48)}
        self.cache = {}

    def render(self, s, size=16, color=(255, 255, 255)):
        key = (s, size, color)
        if key not in self.cache:
            f = self.fonts[size]
            fg = f.render(s, True, color)
            bg = f.render(s, True, (0, 0, 0))
            out = pygame.Surface((fg.get_width() + 4, fg.get_height() + 4), pygame.SRCALPHA)
            for dx, dy in ((0, 2), (4, 2), (2, 0), (2, 4), (0, 0), (4, 4), (0, 4), (4, 0)):
                out.blit(bg, (dx, dy))
            out.blit(fg, (2, 2))
            if len(self.cache) > 600:
                self.cache.clear()
            self.cache[key] = out
        return self.cache[key]

    def draw(self, dst, s, pos, size=16, color=(255, 255, 255), center=False, right=False):
        surf = self.render(s, size, color)
        x, y = pos
        if center:
            x -= surf.get_width() // 2
        elif right:
            x -= surf.get_width()
        dst.blit(surf, (x, y))
        return surf.get_rect(topleft=(x, y))


# ----------------------------------------------------------------------------- world
class World:
    def __init__(self, wt, ht, icons, surface_row, rng):
        self.w, self.h = wt, ht
        self.t = bytearray(wt * ht)
        self.wall = bytearray(wt * ht)
        self.var = bytearray(rng.randrange(256) for _ in range(wt * ht))
        self.T = np.frombuffer(self.t, np.uint8).reshape(ht, wt)
        self.W = np.frombuffer(self.wall, np.uint8).reshape(ht, wt)
        self.trees = []
        self.damage = {}
        self.icons = icons
        self.light = np.ones((ht, wt), np.float32)
        self.light_dirty = True
        self.sheets = {k: img(v) for k, v in TILE_SHEET.items()}
        self.wall_tex = img("Wall_2").subsurface((224, 8, 16, 16)).copy()
        self.platform_tex = img("Tiles_19")
        self.layer = pygame.Surface((wt * TS, ht * TS), pygame.SRCALPHA)
        self.generate(surface_row, rng)
        for y in range(ht):
            for x in range(wt):
                self.draw_tile(x, y)

    # -- access
    def get(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.t[y * self.w + x]
        return AIR if y < 0 else STONE

    def set(self, x, y, v, redraw=True):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return
        self.t[y * self.w + x] = v
        self.light_dirty = True
        if redraw:
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= x + dx < self.w and 0 <= y + dy < self.h:
                    self.draw_tile(x + dx, y + dy)

    def has_wall(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h and self.wall[y * self.w + x]

    def solid(self, x, y):
        if x < 0 or x >= self.w or y >= self.h:
            return True
        if y < 0:
            return False
        return self.t[y * self.w + x] in SOLID

    # -- generation
    def generate(self, base, rng):
        w, h = self.w, self.h
        p = [rng.uniform(0, 6.28) for _ in range(5)]
        self.surf = []
        for x in range(w):
            s = base + 2.2 * math.sin(x * 0.07 + p[0]) + 1.3 * math.sin(x * 0.17 + p[1]) + 0.7 * math.sin(x * 0.33 + p[2])
            self.surf.append(int(round(s)))
        for x in range(w):
            s = self.surf[x]
            dirt_depth = int(11 + 3 * math.sin(x * 0.05 + p[3]) + 2 * math.sin(x * 0.21 + p[4]))
            for y in range(s, h):
                self.t[y * w + x] = DIRT if y < s + dirt_depth else STONE
                if y > s:
                    self.wall[y * w + x] = 1

        def blob(cx, cy, r, val, only=None):
            r2 = r * r
            for yy in range(int(cy - r) - 1, int(cy + r) + 2):
                for xx in range(int(cx - r) - 1, int(cx + r) + 2):
                    if 0 <= xx < w and 0 <= yy < h - 1 and (xx - cx) ** 2 + (yy - cy) ** 2 <= r2:
                        if only is None or self.t[yy * w + xx] in only:
                            self.t[yy * w + xx] = val

        top = min(self.surf)
        for _ in range(45):
            blob(rng.uniform(0, w), rng.uniform(top + 16, h), rng.uniform(1.5, 4), DIRT, {STONE})
        for _ in range(20):
            blob(rng.uniform(0, w), rng.uniform(top + 4, top + 16), rng.uniform(1, 2.2), STONE, {DIRT})
        # caves (worms)
        for i in range(22):
            if i < 3:
                x = rng.uniform(8, w - 8); y = self.surf[int(x)] + 1.0
                ang = rng.uniform(1.0, 2.1)
            else:
                x = rng.uniform(0, w); y = rng.uniform(top + 10, h - 6)
                ang = rng.uniform(0, 6.28)
            r = rng.uniform(1.3, 2.6)
            for _ in range(rng.randint(40, 130)):
                blob(x, y, r, AIR)
                ang += rng.uniform(-0.45, 0.45)
                x += math.cos(ang); y += math.sin(ang) * 0.7
                r = max(1.1, min(3.4, r + rng.uniform(-0.25, 0.25)))
                if not (1 < x < w - 1 and top < y < h - 3):
                    break
        for n, val, dmin, rmax in ((45, COPPER, 5, 1.7), (32, IRON, 18, 1.6), (22, GOLD, 45, 1.5)):
            for _ in range(n):
                blob(rng.uniform(0, w), rng.uniform(top + dmin, h - 2), rng.uniform(0.8, rmax), val, {STONE, DIRT})
        for x in range(w):
            self.t[(h - 1) * w + x] = STONE
        # carve space for desktop icons
        for ic in self.icons:
            r = ic.rect
            for ty in range(r.top // TS, (r.bottom - 1) // TS + 1):
                for tx in range(r.left // TS, (r.right - 1) // TS + 1):
                    if 0 <= tx < w and 0 <= ty < h:
                        self.t[ty * w + tx] = AIR
                        self.wall[ty * w + tx] = 0
        # grass on exposed dirt near the surface
        for x in range(w):
            for y in range(0, h):
                tt = self.t[y * w + x]
                if tt != AIR:
                    if tt == DIRT and not self.wall[max(0, y - 1) * w + x]:
                        self.t[y * w + x] = GRASS
                    self.surf[x] = y
                    break
        # trees and plants
        last_tree = -10
        icon_rects = [ic.rect.inflate(16, 16) for ic in self.icons]
        for x in range(2, w - 2):
            s = self.surf[x]
            if self.get(x, s) != GRASS:
                continue
            if x - last_tree >= 5 and rng.random() < 0.33 and abs(self.surf[x - 1] - s) <= 1 and abs(self.surf[x + 1] - s) <= 1:
                height = rng.randint(6, 13)
                top_y = s - height
                crown = pygame.Rect(x * TS + 8 - 40, top_y * TS - 78, 80, (s - top_y) * TS + 78)
                if top_y > 6 and crown.collidelist(icon_rects) < 0 and abs(x - w // 2) > 3:
                    for y in range(top_y, s):
                        self.t[y * w + x] = TRUNK
                    self.trees.append([x, top_y, s - 1, rng.randrange(3)])
                    last_tree = x
                    continue
            if rng.random() < 0.5 and self.get(x, s - 1) == AIR:
                r = pygame.Rect(x * TS, (s - 1) * TS, TS, TS)
                if r.collidelist(icon_rects) < 0:
                    self.t[(s - 1) * w + x] = PLANT

    # -- rendering
    def frame_for(self, x, y, tt):
        def same(nx, ny):
            if nx < 0 or nx >= self.w or ny >= self.h:
                return True
            if ny < 0:
                return False
            n = self.t[ny * self.w + nx]
            return n == tt or (tt in EARTH and n in EARTH)
        u, d, l, r = same(x, y - 1), same(x, y + 1), same(x - 1, y), same(x + 1, y)
        v = self.var[y * self.w + x] % 3
        if u and d and l and r: return 18 + 18 * v, 18
        if not u and d and l and r: return 18 + 18 * v, 0
        if u and not d and l and r: return 18 + 18 * v, 36
        if u and d and not l and r: return 0, 18 * v
        if u and d and l and not r: return 72, 18 * v
        if not u and d and not l and r: return 36 * v, 54
        if not u and d and l and not r: return 18 + 36 * v, 54
        if u and not d and not l and r: return 36 * v, 72
        if u and not d and l and not r: return 18 + 36 * v, 72
        if not u and not d and l and r: return 108 + 18 * v, 72
        if u and d and not l and not r: return 90, 18 * v
        if not u and d and not l and not r: return 108 + 18 * v, 0
        if u and not d and not l and not r: return 108 + 18 * v, 54
        if not u and not d and not l and r: return 162, 18 * v
        if not u and not d and l and not r: return 216, 18 * v
        return 162 + 18 * v, 54

    def draw_tile(self, x, y):
        px, py = x * TS, y * TS
        self.layer.fill((0, 0, 0, 0), (px, py, TS, TS))
        if self.wall[y * self.w + x]:
            self.layer.blit(self.wall_tex, (px, py))
        tt = self.t[y * self.w + x]
        if tt in self.sheets:
            fx, fy = self.frame_for(x, y, tt)
            self.layer.blit(self.sheets[tt], (px, py), (fx, fy, TS, TS))
        elif tt == PLATFORM:
            l = self.get(x - 1, y) in (PLATFORM,) or self.solid(x - 1, y)
            r = self.get(x + 1, y) in (PLATFORM,) or self.solid(x + 1, y)
            fx = 0 if (l and r) else (18 * 4 if l else (18 * 3 if r else 18 * 5))
            self.layer.blit(self.platform_tex, (px, py), (fx, 0, TS, TS))

    # -- lighting (Terraria-like falloff; vectorised in log space)
    def compute_light(self):
        T, Wl = self.T, self.W
        solid = SOLID_LUT[T]
        cost = np.where(solid, 0.5, 0.1).astype(np.float64)
        src = np.full(T.shape, -60.0)
        src[(~solid) & (Wl == 0)] = 0.0
        src[T == TORCH] = 0.0
        L = src
        for _ in range(2):
            L = _sweep(L, cost, 1)
            L = _sweep(L, cost, 0)
        self.light = np.exp(L).astype(np.float32)
        self.light_dirty = False


def _sweep(L, cost, axis):
    C = np.cumsum(cost, axis=axis)
    fwd = np.maximum.accumulate(L + C, axis=axis) - C
    Lr = np.flip(L, axis)
    Cr = np.cumsum(np.flip(cost, axis), axis=axis)
    bwd = np.flip(np.maximum.accumulate(Lr + Cr, axis=axis) - Cr, axis)
    return np.maximum(np.maximum(fwd, bwd), L)


# ----------------------------------------------------------------------------- entities
class DesktopIcon:
    def __init__(self, idx, name, surf, rect):
        self.idx, self.name, self.surf, self.rect = idx, name, surf, rect
        self.hits = 0
        self.shake = 0


def collides(world, rect, prev_bottom=None, drop=False, ignore_icons=False):
    x0, x1 = rect.left // TS, (rect.right - 1) // TS
    y0, y1 = rect.top // TS, (rect.bottom - 1) // TS
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            if world.solid(tx, ty):
                return True
            if prev_bottom is not None and not drop and world.get(tx, ty) == PLATFORM:
                top = ty * TS
                if prev_bottom <= top < rect.bottom:
                    return True
    if not ignore_icons:
        for ic in world.icons:
            if ic.rect.colliderect(rect):
                return True
    return False


class Body:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = float(x), float(y), w, h
        self.vx = self.vy = 0.0
        self.on_ground = False
        self.gfx_off = 0.0

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def move(self, world, step_up=False, drop=False):
        hit_x = hit_y = False
        rem = self.vx
        while abs(rem) > 1e-6:
            d = max(-1.0, min(1.0, rem))
            nr = pygame.Rect(int(self.x + d), int(self.y), self.w, self.h)
            if collides(world, nr):
                stepped = False
                if step_up and self.on_ground:
                    for k in range(1, TS + 1):
                        sr = nr.move(0, -k)
                        if not collides(world, sr):
                            self.y -= k; self.x += d; self.gfx_off += k; stepped = True
                            break
                if not stepped:
                    hit_x = True
                    self.vx = 0
                    break
            else:
                self.x += d
            rem -= d
        rem = self.vy
        self.on_ground = False
        while abs(rem) > 1e-6:
            d = max(-1.0, min(1.0, rem))
            cur = self.rect
            nr = pygame.Rect(int(self.x), int(self.y + d), self.w, self.h)
            if collides(world, nr, prev_bottom=cur.bottom if d > 0 else None, drop=drop):
                hit_y = True
                if d > 0:
                    self.on_ground = True
                self.vy = 0
                break
            self.y += d
            rem -= d
        if not self.on_ground and self.vy >= 0:
            cur = self.rect
            if collides(world, cur.move(0, 1), prev_bottom=cur.bottom, drop=drop):
                self.on_ground = True
        return hit_x, hit_y


class Player(Body):
    def __init__(self, x, y):
        super().__init__(x, y, PW, PH)
        self.dir = 1
        self.jump = 0
        self.hp = self.max_hp = 100
        self.immune = 0
        self.since_hurt = 999
        self.dead = 0
        self.leg_counter = 0.0
        self.leg_frame = 0
        self.use_timer = 0
        self.use_max = 1
        self.use_item = None
        self.fall_start = y
        self.swing_hit = set()


class Slime(Body):
    def __init__(self, x, y, blue, rng):
        super().__init__(x, y, 30, 22)
        self.color = (60, 110, 255) if blue else (60, 220, 60)
        self.hp = 25 if blue else 14
        self.dmg = 7 if blue else 6
        self.timer = rng.randint(30, 90)
        self.immune = 0
        self.frame = 0
        self.anim = 0


class Drop(Body):
    def __init__(self, key, count, x, y):
        super().__init__(x, y, 12, 12)
        self.key, self.count = key, count
        self.vx = random.uniform(-1.6, 1.6)
        self.vy = random.uniform(-3, -1)
        self.delay = 20


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "color", "size")

    def __init__(self, x, y, color, spread=2.5):
        self.x, self.y = x, y
        self.vx = random.uniform(-spread, spread)
        self.vy = random.uniform(-spread * 1.2, spread * 0.4)
        self.life = random.randint(20, 40)
        self.color = color
        self.size = random.choice((2, 2, 3, 4))


# ----------------------------------------------------------------------------- game
class Game:
    def __init__(self, snap):
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        self.SW, self.SH = snap.size
        self.screen = pygame.display.set_mode((self.SW, self.SH), pygame.NOFRAME)
        pygame.display.set_caption("Desktop Terraria")
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()
        self.rng = random.Random()
        self.snd = Sounds()
        self.txt = Text()
        self.tick = 0
        self.messages = []

        # desktop images
        full = pygame.image.frombuffer(snap.with_icons, snap.size, "BGRA").convert()
        clean = pygame.image.frombuffer(snap.without_icons, snap.size, "BGRA").convert()
        self.bg = clean
        icons = self.build_icons(full, clean, snap.icons)

        wt = math.ceil(self.SW / TS)
        ht = math.ceil(self.SH / TS) * 3
        work_bottom = snap.work[3]
        self.world = World(wt, ht, icons, work_bottom // TS - 4, self.rng)
        for ic in icons:
            ITEMS[f"icon{ic.idx}"] = dict(name=ic.name, kind="icon", icon=ic.idx, stack=1,
                                          surf=self.fit(ic.surf, 32), full=ic.surf)
        self.icon_by_idx = {ic.idx: ic for ic in icons}

        self.item_tex = {}
        for k, d in ITEMS.items():
            if "tex" in d:
                s = img(d["tex"])
                if "tint" in d:
                    s = tinted(s, d["tint"])
                self.item_tex[k] = s
            else:
                self.item_tex[k] = d["surf"]

        self.inv = [None] * 50
        for i, (k, n) in enumerate((("copper_sword", 1), ("copper_pickaxe", 1), ("copper_axe", 1), ("torch", 15))):
            self.inv[i] = [k, n]
        self.sel = 1
        self.inv_open = False
        self.mouse_item = None

        self.spawn = self.find_spawn()
        self.player = Player(*self.spawn)
        self.cam_y = 0.0
        self.slimes, self.drops, self.particles, self.floaters = [], [], [], []
        self.spawn_timer = 400
        self.build_player_art()
        self.cursor = tinted(img("UI_Cursor_0"), (255, 50, 95))
        self.cursor = pygame.transform.scale_by(self.cursor, 1.4)
        self.slot = pygame.transform.smoothscale(img("Inventory_Back"), (44, 44))
        self.slot_sel = pygame.transform.smoothscale(img("Inventory_Back14"), (48, 48))
        self.heart = img("Heart")
        self.logo = img("Logo")
        self.torch_tex = img("Tiles_4")
        self.trunk_tex = img("Tiles_5")
        self.plant_tex = img("Tiles_3")
        self.tops_tex = img("Tree_Tops_0")
        self.slime_tex = img("NPC_1")
        self.slime_cache = {}
        self.palette = self.build_palette()
        self.dark_cache = None
        self.running = True

    # -- setup helpers
    @staticmethod
    def fit(surf, size):
        w, h = surf.get_size()
        k = min(size / w, size / h, 1.0)
        return pygame.transform.smoothscale(surf, (max(1, int(w * k)), max(1, int(h * k))))

    def build_icons(self, full, clean, raw):
        A = pygame.surfarray.array3d(full).astype(np.int16)
        B = pygame.surfarray.array3d(clean).astype(np.int16)
        out = []
        for i, (name, (l, t, r, b)) in enumerate(raw):
            l, t = max(0, l), max(0, t)
            r, b = min(self.SW, r), min(self.SH, b)
            if r - l < 4 or b - t < 4:
                continue
            a, c = A[l:r, t:b], B[l:r, t:b]
            diff = np.abs(a - c).max(axis=2)
            alpha = np.clip((diff - 5) * 6, 0, 255).astype(np.uint8)
            mask = alpha > 60
            if mask.sum() < 20:
                alpha[:] = 255
                mask[:] = True
            xs, ys = np.where(mask)
            x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
            surf = pygame.Surface((x1 - x0, y1 - y0), pygame.SRCALPHA)
            pygame.surfarray.pixels3d(surf)[:] = a[x0:x1, y0:y1].astype(np.uint8)
            pygame.surfarray.pixels_alpha(surf)[:] = alpha[x0:x1, y0:y1]
            out.append(DesktopIcon(i, name, surf, pygame.Rect(l + x0, t + y0, x1 - x0, y1 - y0)))
        return out

    def build_palette(self):
        pal = {}
        for tt, name in TILE_SHEET.items():
            s = img(name)
            pal[tt] = [s.get_at((18 + i * 3, 20 + i * 2))[:3] for i in range(5)]
        pal[TRUNK] = [self.trunk_tex.get_at((6 + i, 8 + i))[:3] for i in range(4)]
        pal[PLANT] = [(40, 180, 60), (30, 140, 50)]
        pal[TORCH] = [(255, 200, 80), (255, 120, 40)]
        pal[PLATFORM] = pal[WOOD]
        return pal

    def build_player_art(self):
        def t(i, c):
            return tinted(img(f"Player_0_{i}"), c)
        self.P = {0: t(0, SKIN), 1: t(1, (255, 255, 255)), 2: t(2, EYE), 3: t(3, SKIN), 4: t(4, UNDER), 5: t(5, SKIN),
                  6: t(6, SHIRT), 7: t(7, SKIN), 9: t(9, SKIN), 10: t(10, SKIN), 11: t(11, PANTS), 12: t(12, SHOES),
                  13: t(13, UNDER)}
        self.hair = tinted(img("Player_Hair_1"), HAIR)
        self.pcache = {}

    def player_sprite(self, leg, arm, flip):
        key = (leg, arm, flip)
        if key not in self.pcache:
            P = self.P
            s = pygame.Surface((40, 56), pygame.SRCALPHA)
            bob = -2 if leg in (7, 8, 9, 14, 15, 16) else 0
            for i in (7, 4):
                s.blit(P[i], (0, bob), (7 * 40, 0, 40, 56))
            for i in (10, 11, 12):
                s.blit(P[i], (0, 0), (0, leg * 56, 40, 56))
            for i in (3, 13, 4, 6):
                s.blit(P[i], (0, bob), (0, 0, 40, 56))
            for i in (0, 1, 2):
                s.blit(P[i], (0, bob), (0, 0, 40, 56))
            s.blit(self.hair, (0, bob), (0, 0, 40, 56))
            ax, ay = arm
            for i in (7, 4, 5, 9):
                s.blit(P[i], (0, bob), (ax * 40, ay * 56, 40, 56))
            if flip:
                s = pygame.transform.flip(s, True, False)
            self.pcache[key] = s
        return self.pcache[key]

    def find_spawn(self):
        w = self.world
        x = w.w // 2
        for y in range(w.h):
            if w.solid(x, y):
                return x * TS + 8 - PW / 2, y * TS - PH - 1
        return x * TS, 0

    # -- inventory
    def add_item(self, key, count):
        stack = ITEMS[key].get("stack", 999)
        for s in self.inv:
            if s and s[0] == key and s[1] < stack:
                take = min(count, stack - s[1]); s[1] += take; count -= take
                if not count:
                    return 0
        for i, s in enumerate(self.inv):
            if s is None:
                take = min(count, stack)
                self.inv[i] = [key, take]; count -= take
                if not count:
                    return 0
        return count

    def count_item(self, key):
        return sum(s[1] for s in self.inv if s and s[0] == key)

    def take_item(self, key, n):
        for i, s in enumerate(self.inv):
            if s and s[0] == key:
                k = min(n, s[1]); s[1] -= k; n -= k
                if s[1] <= 0:
                    self.inv[i] = None
                if not n:
                    return

    def held(self):
        s = self.inv[self.sel]
        return s[0] if s else None

    def msg(self, text, color=(255, 255, 255)):
        self.messages.append([text, color, 360])
        self.messages = self.messages[-6:]

    # -- world interaction
    def mouse_world(self):
        mx, my = pygame.mouse.get_pos()
        return mx, my + self.cam_y

    def in_range(self, wx, wy):
        p = self.player
        cx, cy = p.x + PW / 2, p.y + PH / 2
        return abs(wx - cx) <= TS * 5 + PW / 2 and abs(wy - cy) <= TS * 4 + PH / 2

    def icon_at(self, wx, wy):
        for ic in reversed(self.world.icons):
            if ic.rect.collidepoint(wx, wy):
                return ic
        return None

    def burst(self, x, y, colors, n=8, spread=2.5):
        for _ in range(n):
            self.particles.append(Particle(x, y, random.choice(colors), spread))

    def break_tile(self, tx, ty, drop=True):
        w = self.world
        tt = w.get(tx, ty)
        if tt == AIR:
            return
        w.set(tx, ty, AIR)
        self.burst(tx * TS + 8, ty * TS + 8, self.palette.get(tt, [(150, 150, 150)]), 10)
        if drop and tt in TILE_DROP:
            self.drops.append(Drop(TILE_DROP[tt], 1, tx * TS + 2, ty * TS + 2))
        # unsupported decorations above
        above = w.get(tx, ty - 1)
        if above == PLANT:
            self.break_tile(tx, ty - 1)
        for nx, ny in ((tx, ty - 1), (tx - 1, ty), (tx + 1, ty)):
            if w.get(nx, ny) == TORCH and not self.torch_supported(nx, ny):
                self.break_tile(nx, ny)

    def torch_supported(self, x, y):
        w = self.world
        return w.has_wall(x, y) or w.solid(x, y + 1) or w.solid(x - 1, y) or w.solid(x + 1, y)

    def hit_tile(self, tx, ty, kind):
        w = self.world
        tt = w.get(tx, ty)
        if ty >= w.h - 1 or tt == AIR:
            return False
        if tt == TRUNK:
            if kind != "axe":
                return False
            return self.chop_tree(tx, ty)
        if kind != "pick":
            return False
        # can't dig the block directly under a tree
        if w.get(tx, ty - 1) == TRUNK:
            return False
        (self.snd.tink if tt in TINK else self.snd.dig)()
        hits = w.damage.get((tx, ty), 0) + 1
        if tt == GRASS and hits < TILE_HITS[DIRT] + 1:
            w.set(tx, ty, DIRT)
            self.burst(tx * TS + 8, ty * TS + 4, self.palette[GRASS], 5)
            w.damage[(tx, ty)] = 1
            return True
        if hits >= TILE_HITS.get(tt, 2):
            w.damage.pop((tx, ty), None)
            self.break_tile(tx, ty)
        else:
            w.damage[(tx, ty)] = hits
            self.burst(tx * TS + 8, ty * TS + 8, self.palette.get(tt, [(150, 150, 150)]), 3, 1.5)
        return True

    def chop_tree(self, tx, ty):
        w = self.world
        for tr in w.trees:
            if tr[0] == tx and tr[1] <= ty <= tr[2]:
                key = ("tree", tx)
                hits = w.damage.get(key, 0) + 1
                self.snd.dig()
                self.burst(tx * TS + 8, ty * TS + 8, self.palette[TRUNK], 4)
                if hits < 4:
                    w.damage[key] = hits
                    return True
                w.damage.pop(key, None)
                for y in range(tr[1], tr[2] + 1):
                    w.set(tx, y, AIR)
                    self.burst(tx * TS + 8, y * TS + 8, self.palette[TRUNK], 4)
                self.burst(tx * TS + 8, tr[1] * TS - 30, [(30, 150, 40), (20, 110, 30), (60, 190, 60)], 40, 3)
                n = tr[2] - tr[1] + 1 + self.rng.randint(2, 5)
                self.drops.append(Drop("wood", n, tx * TS + 2, tr[2] * TS - 10))
                w.trees.remove(tr)
                return True
        return False

    def hit_icon(self, ic):
        ic.hits += 1
        ic.shake = 8
        self.snd.tink()
        self.burst(ic.rect.centerx, ic.rect.centery, self.icon_colors(ic), 6)
        if ic.hits >= 4:
            self.world.icons.remove(ic)
            self.snd.play("Shatter")
            self.burst(ic.rect.centerx, ic.rect.centery, self.icon_colors(ic), 40, 3.5)
            self.drops.append(Drop(f"icon{ic.idx}", 1, ic.rect.centerx - 6, ic.rect.centery - 6))
            self.msg(f"You mined '{ic.name}' off your desktop!", (255, 240, 120))
            self.world.light_dirty = True

    def icon_colors(self, ic):
        if not hasattr(ic, "colors"):
            s = ic.surf
            w, h = s.get_size()
            cols = []
            for _ in range(24):
                c = s.get_at((random.randrange(w), random.randrange(max(1, h * 2 // 3))))
                if c.a > 100:
                    cols.append(tuple(c)[:3])
            ic.colors = cols or [(200, 200, 200)]
        return ic.colors

    def try_place(self, key, wx, wy):
        w = self.world
        d = ITEMS[key]
        p = self.player
        if d["kind"] == "icon":
            ic = self.icon_by_idx[d["icon"]]
            r = ic.surf.get_rect()
            r.topleft = (int((wx - r.w / 2) // TS * TS), int((wy - r.h / 2) // TS * TS))
            if r.left < 0 or r.right > w.w * TS or r.top < 0 or r.bottom > w.h * TS:
                return False
            if collides(w, r) or r.colliderect(p.rect):
                return False
            ic.rect = r
            ic.hits = 0
            w.icons.append(ic)
            self.snd.dig()
            return True
        tx, ty = int(wx // TS), int(wy // TS)
        if not (0 <= tx < w.w and 0 <= ty < w.h - 1):
            return False
        cur = w.get(tx, ty)
        if cur not in (AIR, PLANT):
            return False
        tr = pygame.Rect(tx * TS, ty * TS, TS, TS)
        if any(ic.rect.colliderect(tr) for ic in w.icons):
            return False
        place = d["place"]
        if place in SOLID:
            if tr.colliderect(p.rect) or any(s.rect.colliderect(tr) for s in self.slimes):
                return False
        neighbors = [w.get(tx + dx, ty + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        anchored = w.has_wall(tx, ty) or any(n in SOLID or n == PLATFORM for n in neighbors)
        if place == TORCH:
            anchored = self.torch_supported(tx, ty)
        if not anchored:
            return False
        if cur == PLANT:
            self.break_tile(tx, ty, drop=False)
        w.set(tx, ty, place)
        if w.get(tx, ty + 1) == GRASS and place in SOLID:
            w.set(tx, ty + 1, DIRT)
        self.snd.dig()
        return True

    # -- update
    def update(self):
        self.tick += 1
        keys = pygame.key.get_pressed()
        p = self.player
        w = self.world

        if p.dead:
            p.dead -= 1
            if p.dead == 0:
                p.x, p.y = self.spawn
                p.vx = p.vy = 0
                p.hp = p.max_hp
                p.fall_start = p.y
                p.immune = 120
        else:
            self.update_player(keys)

        for s in self.slimes[:]:
            self.update_slime(s)
        for d in self.drops[:]:
            self.update_drop(d)
        for pt in self.particles[:]:
            pt.vy += 0.12; pt.x += pt.vx; pt.y += pt.vy; pt.vx *= 0.96
            pt.life -= 1
            if pt.life <= 0 or w.solid(int(pt.x // TS), int(pt.y // TS)):
                self.particles.remove(pt)
        for ic in w.icons:
            if ic.shake:
                ic.shake -= 1

        self.spawn_timer -= 1
        if self.spawn_timer <= 0:
            self.spawn_timer = self.rng.randint(400, 900)
            if len(self.slimes) < 3:
                self.spawn_slime()
        self.grow()

        # camera follows the player vertically (the desktop is the top screen of the world)
        cy = p.y + PH / 2 - self.cam_y
        lo, hi = self.SH * 0.3, self.SH * 0.9
        if cy > hi:
            self.cam_y += (cy - hi)
        elif cy < lo:
            self.cam_y -= (lo - cy)
        self.cam_y = max(0.0, min(self.cam_y, w.h * TS - self.SH))

        for m in self.messages:
            m[2] -= 1
        self.messages = [m for m in self.messages if m[2] > 0]

    def update_player(self, keys):
        p, w = self.player, self.world
        left = keys[pygame.K_a] or keys[pygame.K_LEFT]
        right = keys[pygame.K_d] or keys[pygame.K_RIGHT]
        jump = keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP]
        down = keys[pygame.K_s] or keys[pygame.K_DOWN]

        if left and not right:
            if p.vx > -MAX_RUN:
                p.vx -= RUN_SLOW if p.vx > 0 else RUN_ACCEL
                p.vx = max(p.vx, -MAX_RUN)
            if not p.use_timer:
                p.dir = -1
        elif right and not left:
            if p.vx < MAX_RUN:
                p.vx += RUN_SLOW if p.vx < 0 else RUN_ACCEL
                p.vx = min(p.vx, MAX_RUN)
            if not p.use_timer:
                p.dir = 1
        else:
            if p.vx > 0:
                p.vx = max(0.0, p.vx - RUN_SLOW)
            elif p.vx < 0:
                p.vx = min(0.0, p.vx + RUN_SLOW)

        if jump:
            if p.jump > 0:
                p.vy = -JUMP_SPEED
                p.jump -= 1
            elif p.on_ground and not getattr(p, "jump_held", False):
                p.vy = -JUMP_SPEED
                p.jump = JUMP_HEIGHT
        else:
            p.jump = 0
        p.jump_held = jump

        p.vy = min(p.vy + GRAVITY, MAX_FALL)
        was_ground = p.on_ground
        _, hit_y = p.move(w, step_up=True, drop=down)
        if hit_y and p.vy == 0 and not p.on_ground:
            p.jump = 0
        p.gfx_off = max(0.0, p.gfx_off - 2.5)

        if p.on_ground:
            fall_tiles = (p.y - p.fall_start) / TS
            if not was_ground and fall_tiles > 25:
                self.hurt_player(int((fall_tiles - 25) * 10), 0, fall=True)
            p.fall_start = p.y
        elif p.vy <= 0:
            p.fall_start = p.y

        # animation
        if not p.on_ground:
            p.leg_frame = 5
        elif abs(p.vx) > 0.1:
            p.leg_counter += abs(p.vx) * 1.3
            if p.leg_counter > 8:
                p.leg_counter = 0
                p.leg_frame = 6 if p.leg_frame < 6 or p.leg_frame >= 19 else p.leg_frame + 1
        else:
            p.leg_frame = 0
            p.leg_counter = 0

        if p.immune:
            p.immune -= 1
        p.since_hurt += 1
        if p.since_hurt > 300 and self.tick % 30 == 0 and p.hp < p.max_hp:
            p.hp += 1

        # item use
        if p.use_timer:
            p.use_timer -= 1
            self.swing_damage()
        mouse = pygame.mouse.get_pressed()
        if mouse[0] and not p.use_timer and not self.ui_blocks_mouse():
            self.use_item()

        if p.y > w.h * TS:
            self.hurt_player(9999, 0)

    def ui_blocks_mouse(self):
        if self.mouse_item:
            return True
        mx, my = pygame.mouse.get_pos()
        return self.slot_at(mx, my) is not None or (self.inv_open and self.inv_panel().collidepoint(mx, my))

    def use_item(self):
        p = self.player
        key = self.held()
        if not key:
            return
        d = ITEMS[key]
        wx, wy = self.mouse_world()
        p.dir = 1 if wx >= p.x + PW / 2 else -1
        if d["kind"] in ("sword", "pick", "axe"):
            p.use_timer = p.use_max = d["use"]
            p.use_item = key
            p.swing_hit = set()
            self.snd.play("Item_1")
            if d["kind"] in ("pick", "axe") and self.in_range(wx, wy):
                ic = self.icon_at(wx, wy)
                if ic and d["kind"] == "pick":
                    self.hit_icon(ic)
                else:
                    self.hit_tile(int(wx // TS), int(wy // TS), d["kind"])
        elif d["kind"] in ("tile", "icon"):
            if self.in_range(wx, wy) and self.try_place(key, wx, wy):
                self.take_item(key, 1)
                p.use_timer = p.use_max = 10
                p.use_item = key
            else:
                p.use_timer = 4
                p.use_max = 4
                p.use_item = None

    def swing_geometry(self):
        """Return (rotated item surface, rect, rotation) for the current swing, or None."""
        p = self.player
        key = p.use_item
        if not key or not p.use_timer or ITEMS[key]["kind"] not in ("sword", "pick", "axe"):
            return None
        ratio = p.use_timer / p.use_max
        rot = (ratio - 0.5) * -p.dir * 3.5 - p.dir * 0.3  # Terraria useStyle 1 swing
        tex = self.item_tex[key]
        if p.dir < 0:
            tex = pygame.transform.flip(tex, True, False)
        hx = p.x + PW / 2 + p.dir * 4
        hy = p.y + 22 + p.gfx_off
        tw, th = tex.get_size()
        pivot = pygame.math.Vector2(0 if p.dir > 0 else tw, th)
        center = pygame.math.Vector2(tw / 2, th / 2)
        off = (center - pivot).rotate_rad(rot)
        rs = pygame.transform.rotate(tex, -math.degrees(rot))
        rect = rs.get_rect(center=(hx + off.x, hy + off.y))
        return rs, rect, rot

    def swing_damage(self):
        geo = self.swing_geometry()
        if not geo:
            return
        _, rect, _ = geo
        d = ITEMS[self.player.use_item]
        for s in self.slimes[:]:
            if id(s) not in self.player.swing_hit and rect.colliderect(s.rect):
                self.player.swing_hit.add(id(s))
                self.damage_slime(s, d["dmg"], d["kb"])

    def damage_slime(self, s, dmg, kb):
        dmg = max(1, int(dmg * self.rng.uniform(0.85, 1.15)))
        crit = self.rng.random() < 0.04
        if crit:
            dmg *= 2
        s.hp -= dmg
        s.vx = kb * self.player.dir * 0.9
        s.vy = -3
        s.on_ground = False
        self.floaters.append([str(dmg), s.x + 15, s.y - 6, 50, (255, 100, 30) if crit else (255, 160, 60)])
        self.burst(s.x + 15, s.y + 11, [s.color], 6)
        if s.hp <= 0:
            self.slimes.remove(s)
            self.snd.play("NPC_Killed_1")
            self.burst(s.x + 15, s.y + 11, [s.color, (255, 255, 255)], 25, 3)
            self.drops.append(Drop("gel", self.rng.randint(1, 2), s.x + 10, s.y + 4))
        else:
            self.snd.play("NPC_Hit_1")

    def hurt_player(self, dmg, kb_dir, fall=False):
        p = self.player
        if p.dead or (p.immune and not fall):
            return
        p.hp -= dmg
        p.since_hurt = 0
        p.immune = 40
        self.floaters.append([str(dmg), p.x + PW / 2, p.y - 8, 50, (255, 60, 60)])
        self.burst(p.x + PW / 2, p.y + PH / 2, [(200, 20, 20), (150, 10, 10)], 10)
        if kb_dir:
            p.vx = 4.5 * kb_dir
            p.vy = -3.5
        if p.hp <= 0:
            p.hp = 0
            p.dead = 180
            self.snd.play("Player_Killed")
            self.burst(p.x + PW / 2, p.y + PH / 2, [(200, 20, 20), SKIN, SHIRT], 50, 4)
            self.msg("You were slain...", (225, 25, 25))
        else:
            self.snd.play("Player_Hit_0", "Player_Hit_1", "Player_Hit_2")

    def spawn_slime(self):
        w, p = self.world, self.player
        for _ in range(20):
            x = self.rng.randrange(2, w.w - 2)
            if abs(x * TS - p.x) < 25 * TS:
                continue
            for y in range(1, w.h - 1):
                if w.solid(x, y):
                    break
            else:
                continue
            r = pygame.Rect(x * TS, y * TS - 24, 30, 22)
            if collides(w, r):
                continue
            self.slimes.append(Slime(r.x, r.y, self.rng.random() < 0.3, self.rng))
            return

    def update_slime(self, s):
        p, w = self.player, self.world
        s.vy = min(s.vy + GRAVITY, MAX_FALL)
        if s.on_ground:
            s.vx *= 0.8
            s.timer -= 1
            s.anim += 1
            if s.timer <= 0:
                d = 1 if p.x > s.x else -1
                if p.dead:
                    d = self.rng.choice((-1, 1))
                big = self.rng.random() < 0.35
                s.vy = -8 if big else -6
                s.vx = d * (2 + self.rng.random() * 1.2)
                s.on_ground = False
                s.timer = self.rng.randint(60, 140)
        s.move(w)
        if s.immune:
            s.immune -= 1
        if not p.dead and s.rect.colliderect(p.rect):
            self.hurt_player(s.dmg, 1 if p.x > s.x else -1)
        if s.y > w.h * TS:
            self.slimes.remove(s)

    def update_drop(self, d):
        p, w = self.player, self.world
        if d.delay:
            d.delay -= 1
        dx = p.x + PW / 2 - (d.x + 6)
        dy = p.y + PH / 2 - (d.y + 6)
        dist = math.hypot(dx, dy)
        if not p.dead and not d.delay and dist < 84 and self.can_take(d.key):
            d.vx += dx / dist * 0.6
            d.vy += dy / dist * 0.6
            sp = math.hypot(d.vx, d.vy)
            if sp > 6:
                d.vx, d.vy = d.vx / sp * 6, d.vy / sp * 6
            d.x += d.vx; d.y += d.vy
            if dist < 18:
                left = self.add_item(d.key, d.count)
                self.snd.play("Grab")
                got = d.count - left
                self.floaters.append([f"{ITEMS[d.key]['name']} ({got})" if got > 1 else ITEMS[d.key]["name"],
                                      p.x + PW / 2, p.y - 10, 70, (255, 255, 255)])
                if left:
                    d.count = left
                else:
                    self.drops.remove(d)
            return
        d.vy = min(d.vy + 0.15, 7)
        d.vx *= 0.95
        d.move(w)

    def can_take(self, key):
        stack = ITEMS[key].get("stack", 999)
        return any(s is None or (s[0] == key and s[1] < stack) for s in self.inv)

    def grow(self):
        w = self.world
        if self.tick % 20:
            return
        for _ in range(12):
            x = self.rng.randrange(w.w)
            y = self.rng.randrange(w.h - 1)
            tt = w.get(x, y)
            if tt == DIRT and w.get(x, y - 1) in (AIR, PLANT) and not w.has_wall(x, y - 1):
                if any(w.get(x + dx, y + dy) == GRASS for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    w.set(x, y, GRASS)
            elif tt == GRASS and w.get(x, y - 1) == AIR and self.rng.random() < 0.15:
                r = pygame.Rect(x * TS, (y - 1) * TS, TS, TS)
                if not any(ic.rect.colliderect(r) for ic in w.icons) and not w.has_wall(x, y - 1):
                    w.set(x, y - 1, PLANT)
            elif tt == GRASS and w.solid(x, y - 1):
                w.set(x, y, DIRT)

    # -- UI geometry
    def hotbar_origin(self):
        return (self.SW - 10 * 50) // 2, 22

    def slot_rect(self, i):
        ox, oy = self.hotbar_origin()
        return pygame.Rect(ox + (i % 10) * 50, oy + (i // 10) * 50 + (8 if i >= 10 else 0), 46, 46)

    def inv_panel(self):
        ox, oy = self.hotbar_origin()
        return pygame.Rect(ox - 10, oy - 10, 10 * 50 + 20, 5 * 50 + 30 + 40 + len(RECIPES) * 50)

    def slot_at(self, mx, my):
        n = 50 if self.inv_open else 10
        for i in range(n):
            if self.slot_rect(i).collidepoint(mx, my):
                return i
        return None

    def recipe_rects(self):
        ox, oy = self.hotbar_origin()
        y = oy + 5 * 50 + 8 + 30
        return [pygame.Rect(ox, y + i * 50, 10 * 50 - 4, 46) for i in range(len(RECIPES))]

    def exit_rect(self):
        p = self.inv_panel()
        return pygame.Rect(p.right + 12, p.top, 160, 40)

    def handle_click(self, button, pos):
        if not self.inv_open:
            i = self.slot_at(*pos)
            if i is not None and button == 1:
                self.sel = i
                self.snd.play("Menu_Tick")
            return
        if button == 1 and self.exit_rect().collidepoint(pos):
            self.running = False
            return
        for r, (key, n, ingr) in zip(self.recipe_rects(), RECIPES):
            if r.collidepoint(pos) and button == 1:
                if all(self.count_item(k) >= c for k, c in ingr) and self.can_take(key):
                    for k, c in ingr:
                        self.take_item(k, c)
                    self.add_item(key, n)
                    self.snd.play("Grab")
                return
        i = self.slot_at(*pos)
        if i is None:
            if self.mouse_item and not self.inv_panel().collidepoint(pos) and button == 1:
                p = self.player
                self.drops.append(Drop(self.mouse_item[0], self.mouse_item[1], p.x + p.dir * 24, p.y + 10))
                self.drops[-1].delay = 90
                self.mouse_item = None
            return
        slot = self.inv[i]
        if button == 1:
            if self.mouse_item and slot and slot[0] == self.mouse_item[0]:
                stack = ITEMS[slot[0]].get("stack", 999)
                take = min(stack - slot[1], self.mouse_item[1])
                slot[1] += take
                self.mouse_item[1] -= take
                if self.mouse_item[1] <= 0:
                    self.mouse_item = None
            else:
                self.inv[i], self.mouse_item = self.mouse_item, slot
            self.snd.play("Grab")
        elif button == 3 and slot and (self.mouse_item is None or self.mouse_item[0] == slot[0]):
            if self.mouse_item is None:
                self.mouse_item = [slot[0], 0]
            if self.mouse_item[1] < ITEMS[slot[0]].get("stack", 999):
                self.mouse_item[1] += 1
                slot[1] -= 1
                if slot[1] <= 0:
                    self.inv[i] = None

    # -- drawing
    def draw(self):
        scr, w, p = self.screen, self.world, self.player
        cam = int(self.cam_y)
        scr.fill((14, 10, 8))
        if cam < self.SH:
            scr.blit(self.bg, (0, -cam))
        view = pygame.Rect(0, cam, self.SW, self.SH)
        scr.blit(w.layer, (0, 0), view)

        ty0, ty1 = cam // TS - 6, (cam + self.SH) // TS + 2
        # decorations
        for ty in range(max(0, ty0), min(w.h, ty1)):
            row = w.t[ty * w.w:(ty + 1) * w.w]
            for tx, tt in enumerate(row):
                if tt == PLANT:
                    v = w.var[ty * w.w + tx] % 11
                    scr.blit(self.plant_tex, (tx * TS, ty * TS - 4 - cam), (v * 18, 0, 16, 20))
                elif tt == TRUNK:
                    v = w.var[ty * w.w + tx] % 3
                    scr.blit(self.trunk_tex, (tx * TS - 2, ty * TS - 2 - cam), (0, v * 22, 20, 20))
                elif tt == TORCH:
                    scr.blit(self.torch_tex, (tx * TS - 2, ty * TS - 2 - cam), (0, 0, 20, 20))
        for tr in w.trees:
            x, top = tr[0], tr[1]
            if ty0 - 6 <= top <= ty1 + 6:
                scr.blit(self.tops_tex, (x * TS + 8 - 40, top * TS - 80 + 4 - cam), (tr[3] * 82, 0, 80, 80))

        for ic in w.icons:
            r = ic.rect.move(0, -cam)
            if r.colliderect(scr.get_rect()):
                if ic.shake:
                    r.x += random.randint(-2, 2)
                scr.blit(ic.surf, r)
                if ic.hits:
                    shade = pygame.Surface(r.size, pygame.SRCALPHA)
                    shade.fill((0, 0, 0, 30 * ic.hits))
                    scr.blit(shade, r)

        for d in self.drops:
            tex = self.item_tex[d.key]
            bob = math.sin((self.tick + id(d) % 60) * 0.08) * 1.5
            scr.blit(tex, (d.x + 6 - tex.get_width() / 2, d.y + 12 - tex.get_height() + bob - cam))

        for s in self.slimes:
            fr = 1 if not s.on_ground else (s.anim // 10) % 2
            key = (s.color, fr)
            if key not in self.slime_cache:
                t = tinted(self.slime_tex.subsurface((0, fr * 26, 32, 26)), s.color, 190)
                self.slime_cache[key] = t
            scr.blit(self.slime_cache[key], (s.x - 1, s.y - 4 - cam))

        if not p.dead and not (p.immune and (self.tick // 3) % 2):
            geo = self.swing_geometry()
            arm = (2, 0)
            if geo:
                rot = geo[2] * p.dir
                arm = (3, 0) if rot < -1.1 else (4, 0) if rot < -0.3 else (5, 0) if rot < 0.6 else (6, 0)
            elif not p.on_ground:
                arm = (2, 1)
            elif p.leg_frame >= 6:
                arm = ([3, 3, 4, 4, 5, 5, 6, 6, 5, 5, 4, 4, 3, 3][p.leg_frame - 6], 1)
            spr = self.player_sprite(p.leg_frame, arm, p.dir < 0)
            sx = p.x + PW / 2 - 20
            sy = p.y + PH - 56 + 2 + p.gfx_off - cam
            scr.blit(spr, (round(sx), round(sy)))
            if geo:
                scr.blit(geo[0], geo[1].move(0, -cam))

        for pt in self.particles:
            scr.fill(pt.color, (pt.x - pt.size / 2, pt.y - pt.size / 2 - cam, pt.size, pt.size))

        self.draw_darkness(cam)

        for f in self.floaters:
            self.txt.draw(scr, f[0], (f[1], f[2] - cam), 16, f[4], center=True)

        self.draw_cursor_target(cam)
        self.draw_ui()

    def draw_darkness(self, cam):
        w = self.world
        if w.light_dirty and self.tick % 3 == 0:
            w.compute_light()
            self.dark_cache = None
        ty0 = max(0, cam // TS - 1)
        ty1 = min(w.h, (cam + self.SH) // TS + 2)
        key = (ty0, ty1, id(w.light))
        if self.dark_cache is None or self.dark_cache[0] != key:
            L = w.light[ty0:ty1]
            if float(L.min()) > 0.97:
                self.dark_cache = (key, None)
            else:
                a = ((1.0 - np.clip(L, 0, 1)) * 255).astype(np.uint8).T  # (w, h)
                small = pygame.Surface((w.w, ty1 - ty0), pygame.SRCALPHA)
                small.fill((0, 0, 0, 255))
                pygame.surfarray.pixels_alpha(small)[:] = a
                big = pygame.transform.smoothscale(small, (w.w * TS, (ty1 - ty0) * TS))
                self.dark_cache = (key, big)
        if self.dark_cache[1] is not None:
            self.screen.blit(self.dark_cache[1], (0, ty0 * TS - cam))

    def draw_cursor_target(self, cam):
        key = self.held()
        if not key or self.player.dead or self.inv_open:
            return
        d = ITEMS[key]
        wx, wy = self.mouse_world()
        if not self.in_range(wx, wy):
            return
        if d["kind"] == "icon":
            ic = self.icon_by_idx[d["icon"]]
            r = ic.surf.get_rect()
            r.topleft = (int((wx - r.w / 2) // TS * TS), int((wy - r.h / 2) // TS * TS))
            ghost = ic.surf.copy()
            ghost.set_alpha(130)
            self.screen.blit(ghost, r.move(0, -cam))
        elif d["kind"] in ("pick", "tile"):
            ic = self.icon_at(wx, wy) if d["kind"] == "pick" else None
            if ic:
                r = ic.rect.move(0, -cam)
            else:
                r = pygame.Rect(int(wx // TS) * TS, int(wy // TS) * TS - cam, TS, TS)
            pygame.draw.rect(self.screen, (255, 255, 255), r, 1)

    def draw_item_in_slot(self, key, count, rect):
        tex = self.item_tex[key]
        if tex.get_width() > 32 or tex.get_height() > 32:
            tex = self.fit(tex, 32)
        self.screen.blit(tex, tex.get_rect(center=rect.center))
        if count > 1:
            self.txt.draw(self.screen, str(count), (rect.x + 6, rect.bottom - 22), 14)

    def draw_ui(self):
        scr = self.screen
        p = self.player
        mx, my = pygame.mouse.get_pos()
        if self.tick < 300:
            lg = self.logo.copy()
            lg.set_alpha(max(0, min(255, (300 - self.tick) * 3)))
            scr.blit(lg, lg.get_rect(center=(self.SW // 2, self.SH // 3)))
        if self.inv_open:
            panel = self.inv_panel()
            bg = pygame.Surface(panel.size, pygame.SRCALPHA)
            bg.fill((40, 50, 120, 170))
            scr.blit(bg, panel)
            pygame.draw.rect(scr, (20, 25, 60), panel, 2)
        n = 50 if self.inv_open else 10
        for i in range(n):
            r = self.slot_rect(i)
            if i == self.sel:
                scr.blit(pygame.transform.smoothscale(self.slot_sel, r.size), r)
            else:
                scr.blit(pygame.transform.smoothscale(self.slot, r.size) if r.w != 44 else self.slot, r)
            if i < 10:
                self.txt.draw(scr, str((i + 1) % 10), (r.x + 4, r.y + 1), 14)
            if self.inv[i]:
                self.draw_item_in_slot(self.inv[i][0], self.inv[i][1], r)
        ox, oy = self.hotbar_origin()
        name = ITEMS[self.held()]["name"] if self.held() else "Items"
        self.txt.draw(scr, name if not self.inv_open else "Inventory", (ox + 250, oy - 24), 16, center=True)

        if self.inv_open:
            rr = self.recipe_rects()
            self.txt.draw(scr, "Crafting", (rr[0].x, rr[0].y - 28), 20)
            for r, (key, n_out, ingr) in zip(rr, RECIPES):
                ok = all(self.count_item(k) >= c for k, c in ingr)
                pygame.draw.rect(scr, (60, 80, 170) if ok else (45, 45, 70), r, border_radius=6)
                if r.collidepoint(mx, my) and ok:
                    pygame.draw.rect(scr, (255, 230, 120), r, 2, border_radius=6)
                self.draw_item_in_slot(key, n_out, pygame.Rect(r.x, r.y, 46, 46))
                parts = ", ".join(f"{c} {ITEMS[k]['name']}" for k, c in ingr)
                self.txt.draw(scr, f"{ITEMS[key]['name']}  <-  {parts}", (r.x + 56, r.y + 12), 16,
                              (255, 255, 255) if ok else (150, 150, 150))
            er = self.exit_rect()
            pygame.draw.rect(scr, (150, 40, 40) if er.collidepoint(mx, my) else (100, 30, 30), er, border_radius=6)
            self.txt.draw(scr, "Exit to Desktop", er.center[0:1] + (er.y + 9,), 20, center=True)

        # life
        hx = self.SW - 10 * 26 - 30
        self.txt.draw(scr, f"Life: {max(0, p.hp)}/{p.max_hp}", (hx + 130, 4), 16, center=True)
        for i in range(p.max_hp // 20):
            frac = max(0.0, min(1.0, (p.hp - i * 20) / 20))
            if frac <= 0:
                continue
            h = self.heart if frac >= 1 else pygame.transform.smoothscale(
                self.heart, (max(1, int(22 * (0.5 + frac / 2))), max(1, int(22 * (0.5 + frac / 2)))))
            scr.blit(h, h.get_rect(center=(hx + 26 * i + 11, 36)))

        # messages
        y = self.SH - 60
        for text, color, t in reversed(self.messages):
            surf = self.txt.render(text, 20, color)
            surf.set_alpha(min(255, t * 4))
            scr.blit(surf, (20, y))
            y -= 26

        if p.dead:
            self.txt.draw(scr, "You were slain...", (self.SW // 2, self.SH // 2 - 40), 48, (225, 25, 25), center=True)

        if self.tick < 900 and not self.inv_open:
            tips = "A/D move   Space jump   S drop   LMB use   1-0 / wheel hotbar   Esc inventory & exit"
            self.txt.draw(scr, tips, (self.SW // 2, oy + 60), 16, (230, 230, 230), center=True)

        # hover name and mouse item
        if self.mouse_item:
            r = pygame.Rect(mx + 6, my + 6, 46, 46)
            self.draw_item_in_slot(self.mouse_item[0], self.mouse_item[1], r)
        else:
            i = self.slot_at(mx, my)
            if i is not None and self.inv[i]:
                self.txt.draw(scr, ITEMS[self.inv[i][0]]["name"], (mx + 18, my + 16), 16)
            elif not self.inv_open:
                wx, wy = self.mouse_world()
                ic = self.icon_at(wx, wy)
                if ic:
                    self.txt.draw(scr, ic.name, (mx + 18, my + 16), 16)
                for s in self.slimes:
                    if s.rect.collidepoint(wx, wy):
                        self.txt.draw(scr, f"{'Blue' if s.color[2] > 200 else 'Green'} Slime: {s.hp}",
                                      (mx + 18, my + 16), 16)
        scr.blit(self.cursor, (mx, my))

    # -- main loop
    def run(self):
        while self.running:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE:
                        self.inv_open = not self.inv_open
                        self.snd.play("Menu_Open" if self.inv_open else "Menu_Close")
                        if not self.inv_open and self.mouse_item:
                            left = self.add_item(*self.mouse_item)
                            self.mouse_item = [self.mouse_item[0], left] if left else None
                    elif e.key == pygame.K_q and (e.mod & pygame.KMOD_CTRL):
                        self.running = False
                    elif pygame.K_1 <= e.key <= pygame.K_9 or e.key == pygame.K_0:
                        self.sel = 9 if e.key == pygame.K_0 else e.key - pygame.K_1
                        self.snd.play("Menu_Tick")
                elif e.type == pygame.MOUSEWHEEL:
                    self.sel = (self.sel - e.y) % 10
                    self.snd.play("Menu_Tick")
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 3):
                    if self.inv_open or self.slot_at(*e.pos) is not None:
                        self.handle_click(e.button, e.pos)
            self.update()
            for f in self.floaters:
                f[2] -= 0.6
                f[3] -= 1
            self.floaters = [f for f in self.floaters if f[3] > 0]
            self.draw()
            pygame.display.flip()
            self.clock.tick(60)


def main():
    if not os.path.exists(os.path.join(ASSETS, "Images_Tiles_0.png")):
        print("Assets missing - run setup.bat first (it exports textures from your Terraria install).")
        sys.exit(1)
    snap = desktop.capture(minimize="--no-minimize" not in sys.argv)
    try:
        game = Game(snap)
        game.run()
    finally:
        pygame.quit()
        desktop.restore_windows()


if __name__ == "__main__":
    main()
