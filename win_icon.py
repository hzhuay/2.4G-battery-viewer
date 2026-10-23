# -*- coding: utf-8 -*-
"""win_icon.py —— 纯 Python 画托盘图标（不依赖 Pillow / 任何第三方库）

图标构成：上半部是设备剪影（耳机 / 鼠标 / 键盘），下半部是电池条。
精确百分比不进图标（12px 看不清），放在 tooltip 里。
"""

from __future__ import annotations

import ctypes
import os
import struct
import tempfile
from ctypes import wintypes

COLOR_OK = (93, 220, 138)
COLOR_MID = (245, 196, 81)
COLOR_LOW = (255, 107, 107)
COLOR_NONE = (120, 126, 136)

GLYPH = (232, 236, 242, 255)
DETAIL = (34, 37, 43, 255)
FRAME = (198, 204, 212, 255)
OUTLINE = (16, 17, 19, 190)


def level_color(level):
    if level is None:
        return COLOR_NONE
    if level >= 60:
        return COLOR_OK
    if level >= 30:
        return COLOR_MID
    return COLOR_LOW


def _put(px, size, x, y, rgba):
    if 0 <= x < size and 0 <= y < size:
        i = (y * size + x) * 4
        px[i:i + 4] = bytes(rgba)


def _alpha(px, size, x, y):
    if 0 <= x < size and 0 <= y < size:
        return px[(y * size + x) * 4 + 3]
    return 0


def _rect(px, size, x0, y0, x1, y1, rgba, r=0):
    if x1 < x0 or y1 < y0:
        return
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if r:
                cx, cy = min(x - x0, x1 - x), min(y - y0, y1 - y)
                if cx < r and cy < r:
                    dx, dy = r - cx, r - cy
                    if dx * dx + dy * dy > r * r:
                        continue
            _put(px, size, x, y, rgba)


def _vline(px, size, x, y0, y1, rgba):
    for y in range(y0, y1 + 1):
        _put(px, size, x, y, rgba)


def _hline(px, size, x0, x1, y, rgba):
    for x in range(x0, x1 + 1):
        _put(px, size, x, y, rgba)


def _glyph_headset(px, size, x0, y0, x1, y1):
    w, h = x1 - x0 + 1, y1 - y0 + 1
    cx = (x0 + x1) / 2
    cy = y0 + h * 0.60
    rad = min(w * 0.44, h * 0.56)
    thick = max(2.0, size * 0.10)
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if y <= cy and rad - thick <= d <= rad:
                _put(px, size, x, y, GLYPH)
    cup_w = max(2, int(w * 0.22))
    cup_h = max(3, int(h * 0.40))
    cup_y0 = int(cy - cup_h * 0.30)
    _rect(px, size, x0, cup_y0, x0 + cup_w - 1, cup_y0 + cup_h, GLYPH, 1)
    _rect(px, size, x1 - cup_w + 1, cup_y0, x1, cup_y0 + cup_h, GLYPH, 1)


def _glyph_mouse(px, size, x0, y0, x1, y1):
    w, h = x1 - x0 + 1, y1 - y0 + 1
    bw = max(4, int(w * 0.50))
    bh = max(6, int(h * 0.94))
    bx = (x0 + x1) // 2 - bw // 2
    by = y0 + (h - bh) // 2
    _rect(px, size, bx, by, bx + bw - 1, by + bh - 1, GLYPH, max(2, bw // 2))
    mid = bx + bw // 2
    _vline(px, size, mid, by + 1, by + max(2, bh // 3), DETAIL)


def _glyph_keyboard(px, size, x0, y0, x1, y1):
    w, h = x1 - x0 + 1, y1 - y0 + 1
    bh = max(5, int(h * 0.64))
    by = y0 + (h - bh) // 2
    _rect(px, size, x0, by, x1, by + bh - 1, GLYPH, 1)
    inner_x0, inner_x1 = x0 + 1, x1 - 1
    cols = max(3, (inner_x1 - inner_x0 + 1) // 3)
    rows = 2 if bh < 8 else 3
    step = max(1, (bh - 2) // rows)
    for r in range(rows):
        ry = by + 1 + r * step
        if ry >= by + bh - 1:
            continue
        for c in range(cols):
            cxp = inner_x0 + c * 3
            if cxp <= inner_x1:
                _put(px, size, cxp, ry, DETAIL)


GLYPHS = {"headset": _glyph_headset, "mouse": _glyph_mouse,
          "keyboard": _glyph_keyboard}


def render_icon(kind, level, size):
    px = bytearray(size * size * 4)
    mx = max(1, round(size * 0.06))
    bar_h = max(3, round(size * 0.26))
    gap = 1 if size >= 20 else 0
    glyph_y1 = size - bar_h - gap - 1
    draw = GLYPHS.get(kind)
    if draw is not None:
        draw(px, size, mx, 0, size - 1 - mx, max(glyph_y1, 3))

    bx0, bx1 = mx, size - 1 - mx
    by0, by1 = size - bar_h, size - 1
    _hline(px, size, bx0, bx1, by0, FRAME)
    _hline(px, size, bx0, bx1, by1, FRAME)
    _vline(px, size, bx0, by0, by1, FRAME)
    _vline(px, size, bx1, by0, by1, FRAME)
    if level is not None and level > 0:
        ix0, ix1 = bx0 + 1, bx1 - 1
        iy0, iy1 = by0 + 1, by1 - 1
        inner_w = max(1, ix1 - ix0 + 1)
        fill = max(1, round(inner_w * min(level, 100) / 100))
        c = level_color(level)
        _rect(px, size, ix0, iy0, min(ix1, ix0 + fill - 1), iy1,
              (c[0], c[1], c[2], 255))

    edge = []
    for y in range(size):
        for x in range(size):
            if _alpha(px, size, x, y) == 0:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if _alpha(px, size, x + dx, y + dy) == 0:
                    edge.append((x + dx, y + dy))
    for x, y in edge:
        if _alpha(px, size, x, y) == 0:
            _put(px, size, x, y, OUTLINE)
    return bytes(px)


def build_ico(images):
    entries, blobs = [], []
    offset = 6 + 16 * len(images)
    for size, rgba in images:
        bih = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                          size * size * 4, 0, 0, 0, 0)
        xor = bytearray()
        for y in range(size - 1, -1, -1):
            row = rgba[y * size * 4:(y + 1) * size * 4]
            for x in range(size):
                r, g, b, a = row[x * 4:x * 4 + 4]
                xor += bytes((b, g, r, a))
        row_bytes = ((size + 31) // 32) * 4
        mask = bytes(row_bytes * size)
        blob = bih + bytes(xor) + mask
        blobs.append(blob)
        entries.append(struct.pack("<BBBBHHII", size if size < 256 else 0,
                                   size if size < 256 else 0, 0, 0, 1, 32,
                                   len(blob), offset))
        offset += len(blob)
    return (struct.pack("<HHH", 0, 1, len(images)) + b"".join(entries)
            + b"".join(blobs))


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
SM_CXSMICON = 49

user32.LoadImageW.restype = ctypes.c_void_p
user32.LoadImageW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.UINT,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.DestroyIcon.restype = wintypes.BOOL
user32.DestroyIcon.argtypes = [ctypes.c_void_p]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = [ctypes.c_int]

SIZES = (16, 20, 24, 32, 48)
_icon_cache = {}
_tmp_dir = None


def system_icon_size():
    try:
        s = user32.GetSystemMetrics(SM_CXSMICON)
        if 12 <= s <= 64:
            return s
    except Exception:
        pass
    return 16


def _ensure_tmp():
    global _tmp_dir
    if _tmp_dir is None:
        _tmp_dir = os.path.join(tempfile.gettempdir(), "device_battery_icons")
        os.makedirs(_tmp_dir, exist_ok=True)
    return _tmp_dir


def make_icon(kind, level):
    target = system_icon_size()
    q = None if level is None else int(round(level / 2.0) * 2)
    key = (kind, q, target)
    if key in _icon_cache:
        return _icon_cache[key]
    sizes = sorted(set(SIZES) | {target})
    images = [(s, render_icon(kind, q, s)) for s in sizes]
    ico = build_ico(images)
    tag = "na" if q is None else str(q)
    path = os.path.join(_ensure_tmp(), kind + "_" + tag + "_" + str(target) + ".ico")
    try:
        with open(path, "wb") as f:
            f.write(ico)
    except OSError:
        return 0
    h = user32.LoadImageW(None, path, IMAGE_ICON, target, target, LR_LOADFROMFILE)
    hicon = int(h) if h else 0
    _icon_cache[key] = hicon
    return hicon


def destroy_all():
    for h in _icon_cache.values():
        if h:
            try:
                user32.DestroyIcon(ctypes.c_void_p(h))
            except Exception:
                pass
    _icon_cache.clear()


def cleanup_files():
    global _tmp_dir
    if _tmp_dir and os.path.isdir(_tmp_dir):
        for name in os.listdir(_tmp_dir):
            try:
                os.remove(os.path.join(_tmp_dir, name))
            except OSError:
                pass
