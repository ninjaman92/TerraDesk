"""Windows desktop capture: screenshots (with / without icons) and desktop icon geometry."""
import ctypes
import ctypes.wintypes as wt
import glob
import os
import time

import win32api
import win32con
import win32gui
import win32process
import win32ui

user32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32

LVM_GETITEMCOUNT = 0x1004
LVM_GETITEMRECT = 0x100E
LVM_GETITEMTEXTW = 0x1073
LVIR_BOUNDS = 0
LVIF_TEXT = 1

k32.OpenProcess.restype = ctypes.c_void_p
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.VirtualAllocEx.restype = ctypes.c_void_p
k32.VirtualAllocEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, wt.DWORD]
k32.VirtualFreeEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD]
k32.WriteProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
k32.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
k32.CloseHandle.argtypes = [ctypes.c_void_p]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t]


def set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def screen_size():
    return win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)


def work_area():
    mon = win32api.MonitorFromPoint((0, 0))
    return win32api.GetMonitorInfo(mon)["Work"]


def find_listview():
    progman = win32gui.FindWindow("Progman", None)
    defview = win32gui.FindWindowEx(progman, 0, "SHELLDLL_DefView", None) if progman else 0
    if not defview:
        found = []

        def cb(h, _):
            d = win32gui.FindWindowEx(h, 0, "SHELLDLL_DefView", None)
            if d:
                found.append(d)
            return True

        win32gui.EnumWindows(cb, None)
        defview = found[0] if found else 0
    if not defview:
        return 0
    return win32gui.FindWindowEx(defview, 0, "SysListView32", None)


def grab_screen(w, h):
    hdesk = win32gui.GetDesktopWindow()
    hdc = win32gui.GetWindowDC(hdesk)
    src = win32ui.CreateDCFromHandle(hdc)
    mem = src.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(src, w, h)
    mem.SelectObject(bmp)
    mem.BitBlt((0, 0), (w, h), src, (0, 0), win32con.SRCCOPY)
    bits = bmp.GetBitmapBits(True)
    mem.DeleteDC()
    src.DeleteDC()
    win32gui.ReleaseDC(hdesk, hdc)
    win32gui.DeleteObject(bmp.GetHandle())
    return bits  # BGRA, top-down


def _desktop_dirs():
    dirs = []
    for env in ("USERPROFILE", "PUBLIC"):
        base = os.environ.get(env)
        if base:
            dirs.append(os.path.join(base, "Desktop"))
            dirs.append(os.path.join(base, "OneDrive", "Desktop"))
    od = os.environ.get("OneDrive")
    if od:
        dirs.append(os.path.join(od, "Desktop"))
    return [d for d in dirs if os.path.isdir(d)]


def resolve_icon_path(name):
    for d in _desktop_dirs():
        exact = os.path.join(d, name)
        if os.path.exists(exact):
            return exact
        for p in glob.glob(os.path.join(d, glob.escape(name) + ".*")):
            return p
    return None


def read_icons(lv):
    """Return [(name, (left, top, right, bottom) in screen coords)] for each desktop icon."""
    if not lv:
        return []
    count = user32.SendMessageW(lv, LVM_GETITEMCOUNT, 0, 0)
    if count <= 0:
        return []
    _, pid = win32process.GetWindowThreadProcessId(lv)
    hproc = k32.OpenProcess(0x0008 | 0x0010 | 0x0020 | 0x0400, False, pid)
    if not hproc:
        return []
    remote = k32.VirtualAllocEx(hproc, None, 4096, 0x3000, 0x04)
    ox, oy = win32gui.ClientToScreen(lv, (0, 0))
    out = []
    try:
        for i in range(count):
            rect = (ctypes.c_long * 4)(LVIR_BOUNDS, 0, 0, 0)
            k32.WriteProcessMemory(hproc, remote, ctypes.byref(rect), 16, None)
            user32.SendMessageW(lv, LVM_GETITEMRECT, i, remote)
            k32.ReadProcessMemory(hproc, remote, ctypes.byref(rect), 16, None)

            item = (ctypes.c_ubyte * 88)()
            ctypes.memmove(ctypes.byref(item, 0), ctypes.byref(ctypes.c_uint(LVIF_TEXT)), 4)
            ctypes.memmove(ctypes.byref(item, 4), ctypes.byref(ctypes.c_int(i)), 4)
            ctypes.memmove(ctypes.byref(item, 24), ctypes.byref(ctypes.c_uint64(remote + 512)), 8)
            ctypes.memmove(ctypes.byref(item, 32), ctypes.byref(ctypes.c_int(260)), 4)
            k32.WriteProcessMemory(hproc, remote, ctypes.byref(item), 88, None)
            n = user32.SendMessageW(lv, LVM_GETITEMTEXTW, i, remote)
            buf = ctypes.create_unicode_buffer(261)
            k32.ReadProcessMemory(hproc, ctypes.c_void_p(remote + 512), buf, 520, None)
            name = buf.value if n > 0 else f"Icon {i + 1}"
            l, t, r, b = rect
            out.append((name, (l + ox, t + oy, r + ox, b + oy)))
    finally:
        k32.VirtualFreeEx(hproc, remote, 0, 0x8000)
        k32.CloseHandle(hproc)
    return out


class DesktopSnapshot:
    def __init__(self, with_icons, without_icons, icons, size, work):
        self.with_icons = with_icons
        self.without_icons = without_icons
        self.icons = icons
        self.size = size
        self.work = work


_shell = None


def capture(minimize=True):
    """Minimize windows, screenshot desktop with icons, hide icons, screenshot wallpaper."""
    global _shell
    w, h = screen_size()
    if minimize:
        try:
            import win32com.client
            _shell = win32com.client.Dispatch("Shell.Application")
            _shell.MinimizeAll()
            time.sleep(0.9)
        except Exception:
            _shell = None
    lv = find_listview()
    icons = read_icons(lv)
    with_icons = grab_screen(w, h)
    without = with_icons
    if lv:
        win32gui.ShowWindow(lv, win32con.SW_HIDE)
        try:
            time.sleep(0.35)
            without = grab_screen(w, h)
        finally:
            win32gui.ShowWindow(lv, win32con.SW_SHOW)
    icons = [(n, r) for n, r in icons if r[2] > 0 and r[3] > 0 and r[0] < w and r[1] < h]
    return DesktopSnapshot(with_icons, without, icons, (w, h), work_area())


def restore_windows():
    if _shell is not None:
        try:
            _shell.UndoMinimizeALL()
        except Exception:
            pass
