"""Locate the local Terraria install (env var, Steam libraries, then common paths)."""
import os
import re
import sys


def _steam_roots():
    roots = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            roots.append(winreg.QueryValueEx(k, name)[0])
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    roots += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    libs = []
    for r in roots:
        r = os.path.normpath(r)
        libs.append(r)
        vdf = os.path.join(r, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf):
            text = open(vdf, encoding="utf-8", errors="ignore").read()
            libs += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', text)]
    return libs


def find_terraria():
    env = os.environ.get("TERRARIA_DIR")
    candidates = [env] if env else []
    candidates += [os.path.join(lib, "steamapps", "common", "Terraria") for lib in _steam_roots()]
    candidates += [rf"{d}:\SteamLibrary\steamapps\common\Terraria" for d in "CDEFGH"]
    candidates += [r"C:\GOG Games\Terraria", r"C:\Program Files (x86)\GOG Galaxy\Games\Terraria"]
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "Content", "Images", "Tiles_0.xnb")):
            return os.path.normpath(c)
    return None


if __name__ == "__main__":
    path = find_terraria()
    if not path:
        sys.exit(1)
    print(path)
