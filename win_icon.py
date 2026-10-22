# -*- coding: utf-8 -*-
"""win_icon.py —— 用纯 Python 画托盘图标（不依赖 Pillow / 任何第三方库）

做法：内置一套 3x5 点阵数字，按电量数值渲染成 RGBA 位图，
再手写 ICO 文件格式，最后交给 LoadImageW 变成 HICON。
支持 16/24/32 三种尺寸，Windows 会按 DPI 自动挑合适的那张。
"""

from __future__ import annotations

import ctypes
import os
import struct
import tempfile
from ctypes import wintypes
from typing import Optional

# ---- 3x5 点阵数字（每行 3 位，"1" 点亮）----
DIGITS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "001", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "%": ("101", "001", "010", "100", "101"),
}

GLYPH_W, GLYPH_H = 3, 5


def render_rgba(text: str, size: int, color: tuple[int, int, int]) -> bytes:
    """把文字渲染成 size×size 的 RGBA 像素（返回 size*size*4 字节，行优先）。

    关键点：**横向缩放和纵向缩放分开算**。
    三位数（100）如果等比例缩放会被压得很小，所以允许纵向拉高到与两位数齐平，
    代价只是数字看起来略瘦——比"变小一半"好看得多。
    """
    n = len(text)
    avail_w, avail_h = size - 2, size - 2
    gap = 1 if size >= 20 else 0

    sy = max(1, avail_h // GLYPH_H)                    # 纵向能放多大
    sx = max(1, (avail_w - (n - 1) * gap) // (GLYPH_W * n))   # 横向能放多大
    sx = min(sx, sy)
    # 避免拉得太夸张（比例超过 1.6 会变成"瘦高条"）
    sy = min(sy, max(sx, int(round(sx * 1.6))))

    gw, gh = GLYPH_W * sx, GLYPH_H * sy
    total_w = n * gw + (n - 1) * gap
    total_h = gh
    ox = (size - total_w) // 2
    oy = (size - total_h) // 2

    px = bytearray(size * size * 4)

    def put(x: int, y: int, rgba):
        if 0 <= x < size and 0 <= y < size:
            i = (y * size + x) * 4
            px[i:i + 4] = bytes(rgba)

    def get(x: int, y: int):
        i = (y * size + x) * 4
        return (px[i], px[i + 1], px[i + 2], px[i + 3])


    # 逐字画
    for k, ch in enumerate(text):
        glyph = DIGITS.get(ch)
        if not glyph:
            continue
        gx = ox + k * (gw + gap)
        for gy, row in enumerate(glyph):
            for gxx, bit in enumerate(row):
                if bit != "1":
                    continue
                for dy in range(sy):
                    for dx in range(sx):
                        put(gx + gxx * sx + dx, oy + gy * sy + dy,
                            (*color, 255))

    # 描一圈深色轮廓，保证在浅色/深色任务栏上都看得清
    outline = (16, 17, 19, 190)
    edge = []
    for y in range(size):
        for x in range(size):
            if get(x, y)[3] == 0:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < size and 0 <= ny < size and get(nx, ny)[3] == 0:
                    edge.append((nx, ny))
    for x, y in edge:
        if get(x, y)[3] == 0:
            put(x, y, outline)
    return bytes(px)


def build_ico(pngs: list[tuple[int, bytes]]) -> bytes:
    """把多张 RGBA 位图打包成 ICO 文件内容。"""
    entries = []
    blobs = []
    offset = 6 + 16 * len(pngs)
    for size, rgba in pngs:
        # BITMAPINFOHEADER
        bih = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                          size * size * 4, 0, 0, 0, 0)
        # XOR 位图：32bpp BGRA，自下而上
        xor = bytearray()
        for y in range(size - 1, -1, -1):
            row = rgba[y * size * 4:(y + 1) * size * 4]
            for x in range(size):
                r, g, b, a = row[x * 4:x * 4 + 4]
                # 预乘不必要，Windows 直接用 alpha
                xor += bytes((b, g, r, a))
        # AND 掩码：1bpp，每行按 4 字节对齐，全 0（靠 alpha 通道）
        row_bytes = ((size + 31) // 32) * 4
        mask = b"\x00" * (row_bytes * size)
        blob = bih + bytes(xor) + mask
        blobs.append(blob)
        entries.append(struct.pack("<BBBBHHII", size if size < 256 else 0,
                                   size if size < 256 else 0, 0, 0, 1, 32,
                                   len(blob), offset))
        offset += len(blob)
    return (struct.pack("<HHH", 0, 1, len(pngs)) + b"".join(entries)
            + b"".join(blobs))


# ---------------- HICON 缓存 ----------------
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010

user32.LoadImageW.restype = ctypes.c_void_p
user32.LoadImageW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.UINT,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.DestroyIcon.restype = wintypes.BOOL
user32.DestroyIcon.argtypes = [ctypes.c_void_p]

SIZES = (16, 20, 24, 32, 48)

SM_CXSMICON = 49
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = [ctypes.c_int]


def system_icon_size() -> int:
    """任务栏通知区当前用的图标像素尺寸（随 DPI 变化：16/20/24/32…）。"""
    try:
        s = user32.GetSystemMetrics(SM_CXSMICON)
        if 12 <= s <= 64:
            return s
    except Exception:
        pass
    return 16
_icon_cache: dict[tuple, int] = {}
_tmp_dir: Optional[str] = None


def _ensure_tmp() -> str:
    global _tmp_dir
    if _tmp_dir is None:
        _tmp_dir = os.path.join(tempfile.gettempdir(), "device_battery_icons")
        os.makedirs(_tmp_dir, exist_ok=True)
    return _tmp_dir


def make_hicon(text: str, color: tuple[int, int, int]) -> int:
    """按文字+颜色生成（带缓存的）HICON；失败返回 0。"""
    target = system_icon_size()
    key = (text, color, target)
    if key in _icon_cache:
        return _icon_cache[key]
    sizes = sorted(set(SIZES) | {target})
    images = [(s, render_rgba(text, s, color)) for s in sizes]
    ico = build_ico(images)
    path = os.path.join(_ensure_tmp(), f"ico_{text}_{color[0]:02x}{color[1]:02x}"
                                       f"{color[2]:02x}_{target}.ico")
    try:
        with open(path, "wb") as f:
            f.write(ico)
    except OSError:
        return 0
    # 明确要 target 尺寸，否则 Windows 会拿小图放大，字就糊成一团
    h = user32.LoadImageW(None, path, IMAGE_ICON, target, target, LR_LOADFROMFILE)
    hicon = int(h) if h else 0
    _icon_cache[key] = hicon
    return hicon


def destroy_all() -> None:
    for h in _icon_cache.values():
        if h:
            try:
                user32.DestroyIcon(ctypes.c_void_p(h))
            except Exception:
                pass
    _icon_cache.clear()


def cleanup_files() -> None:
    """清掉临时目录里的 ico 文件。"""
    global _tmp_dir
    if _tmp_dir and os.path.isdir(_tmp_dir):
        for name in os.listdir(_tmp_dir):
            try:
                os.remove(os.path.join(_tmp_dir, name))
            except OSError:
                pass


if __name__ == "__main__":
    # 生成几个样例，方便肉眼检查
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_icon_preview")
    os.makedirs(out, exist_ok=True)
    for text, color, name in (
        ("82", (93, 220, 138), "mouse82"),
        ("70", (93, 220, 138), "headset70"),
        ("9", (255, 107, 107), "mouse9"),
        ("100", (245, 196, 81), "headset100"),
        ("25", (245, 196, 81), "mouse25"),
    ):
        imgs = [(s, render_rgba(text, s, color)) for s in SIZES]
        p = os.path.join(out, name + ".ico")
        with open(p, "wb") as f:
            f.write(build_ico(imgs))
        print("生成", p)
