# -*- coding: utf-8 -*-
"""last_state.py —— 三台设备共用的「上次读数」落盘缓存

为什么要它：
    漫步者/雷柏/迈从都有读不到的时候（耳机没开机、鼠标不动、键盘没推送）。
    这时候应该显示「上次读到多少、什么时候读到的」，而不是一片空白。

存哪：
    exe / 脚本同目录的 `device_last.json`（已 gitignore）。
    打包成 exe 后取 exe 所在目录，不会落到临时解包目录。

格式：
    {"edifier": {"level": 79, "status": "放电中", "detail": "...", "extra": "...",
                 "ts": 1761177600.0}, ...}
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Optional

BASE_DIR = (os.path.dirname(os.path.abspath(sys.executable))
            if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(BASE_DIR, "device_last.json")

# 超过这个时长就不再当作"当前电量"，只写进报错文本里
CACHE_TTL = 24 * 3600.0

_lock = threading.Lock()


def _read_all() -> dict:
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_all(data: dict) -> None:
    tmp = CACHE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def save(key: str, level: int, status: str = "", detail: str = "",
         extra: str = "", ts: Optional[float] = None) -> None:
    """记下一次成功读数（线程安全）。"""
    now = time.time() if ts is None else float(ts)
    with _lock:
        data = _read_all()
        data[key] = {"level": int(level), "status": status, "detail": detail,
                     "extra": extra, "ts": now}
        _write_all(data)


def get(key: str) -> Optional[dict]:
    """取上次读数；没有就返回 None。"""
    with _lock:
        item = _read_all().get(key)
    if not isinstance(item, dict):
        return None
    try:
        item["level"] = int(item["level"])
        item["ts"] = float(item["ts"])
    except (KeyError, TypeError, ValueError):
        return None
    if not 0 <= item["level"] <= 100 or item["ts"] <= 0:
        return None
    return item


def is_expired(ts: float) -> bool:
    return (time.time() - ts) > CACHE_TTL


def clock(ts: float) -> str:
    """把时间戳格式化成 HH:MM（当天）或 MM-DD HH:MM（更早）。"""
    lt = time.localtime(ts)
    if time.localtime().tm_yday == lt.tm_yday and time.localtime().tm_year == lt.tm_year:
        return time.strftime("%H:%M", lt)
    return time.strftime("%m-%d %H:%M", lt)


def age_text(ts: float) -> str:
    """「刚刚 / 12 分钟前 / 3 小时前」。"""
    sec = max(0, int(time.time() - ts))
    if sec < 60:
        return "刚刚"
    if sec < 3600:
        return f"{sec // 60} 分钟前"
    if sec < 86400:
        return f"{sec // 3600} 小时前"
    return f"{sec // 86400} 天前"


def stamp(ts: float) -> str:
    """「14:32 更新（12 分钟前）」——界面/托盘上显示的就是这句。"""
    return f"{clock(ts)} 更新（{age_text(ts)}）"


def stamp_brief(ts: float) -> str:
    """嵌进报错文本用，避免括号套括号：14:32，12 分钟前。"""
    return f"{clock(ts)}，{age_text(ts)}"

