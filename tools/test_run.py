"""Headless smoke test: builds the world from the real desktop, simulates input, saves screenshots."""
import os
import sys
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pygame
import game
import desktop

OUT = os.path.dirname(os.path.abspath(__file__))
held = set()


class FakeKeys:
    def __getitem__(self, k):
        return k in held


pygame.key.get_pressed = lambda: FakeKeys()
mouse = {"pos": (960, 900), "btn": (False, False, False)}
pygame.mouse.get_pos = lambda: mouse["pos"]
pygame.mouse.get_pressed = lambda num_buttons=3: mouse["btn"]

snap = desktop.capture(minimize="--min" in sys.argv)
desktop.restore_windows()
print("icons", len(snap.icons), "size", snap.size, "work", snap.work)
t = time.time()
g = game.Game(snap)
print("init", round(time.time() - t, 2), "s; sounds", len(g.snd.s))


def step(n):
    t0 = time.time()
    for _ in range(n):
        g.update()
        for f in g.floaters:
            f[2] -= 0.6; f[3] -= 1
        g.floaters = [f for f in g.floaters if f[3] > 0]
        g.draw()
    return (time.time() - t0) / n * 1000


def shot(name):
    pygame.image.save(g.screen, os.path.join(OUT, name))


print("idle ms/frame", round(step(60), 2))
shot("shot_spawn.png")
held.add(pygame.K_d)
print("walk ms/frame", round(step(40), 2))
held.add(pygame.K_SPACE)
step(10)
held.discard(pygame.K_SPACE)
step(5)
p = g.player
mouse["pos"] = (int(p.x + 10), int(p.y + 60 - g.cam_y))
shot("shot_walk.png")
held.clear()
step(20)
# dig straight down
g.sel = 1
mouse["btn"] = (True, False, False)
for i in range(30):
    p = g.player
    mouse["pos"] = (int(p.x + 10), int(p.y + PH + 8 - g.cam_y)) if (PH := 42) else None
    step(8)
mouse["btn"] = (False, False, False)
print("after dig: player y tiles", round(g.player.y / 16, 1), "cam", g.cam_y, "inv", [s for s in g.inv if s])
shot("shot_dig.png")
# place a torch
g.sel = 3
mouse["btn"] = (True, False, False)
mouse["pos"] = (int(g.player.x + 30), int(g.player.y + 10 - g.cam_y))
step(3)
mouse["btn"] = (False, False, False)
print("light ms/frame", round(step(20), 2))
shot("shot_torch.png")
# spawn a slime next to player and swing sword
g.sel = 0
g.slimes.append(game.Slime(g.player.x + 30, g.player.y + 10, False, g.rng))
mouse["btn"] = (True, False, False)
mouse["pos"] = (int(g.player.x + 60), int(g.player.y + 20 - g.cam_y))
step(8)
shot("shot_swing.png")
step(40)
mouse["btn"] = (False, False, False)
print("slimes", len(g.slimes), "hp", g.player.hp)
g.inv_open = True
step(2)
shot("shot_inv.png")
pygame.quit()
