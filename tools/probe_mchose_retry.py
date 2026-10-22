# -*- coding: utf-8 -*-
"""tools/probe_mchose_retry.py —— 反复发 getInfo/getBase，等键盘醒着的时候应答

怀疑：无线键盘休眠时，dongle 问不到键盘本人 → 不回包。
所以这里每 0.5 秒重发一次官方查询帧，人为把键盘「叫醒」。

用法：
    python tools/probe_mchose_retry.py --seconds 90
"""

from __future__ import annotations

import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hid_win as hw
from hid_win import HidDevice

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VID = 0x3837
REPORT_LEN = 65


def zframe(command: int, size: int = 56, offset: int = 0) -> bytes:
    """官方 Z 帧：[55 cmd 00 cs size offLo offHi 00]"""
    lo, hi = offset & 0xFF, (offset >> 8) & 0xFF
    cs = size ^ lo ^ hi
    return bytes([0x55, command, 0x00, cs, size, lo, hi, 0x00])


def build(frame: bytes) -> bytes:
    # Windows 第 0 字节是报告 ID，被剥掉；补 0x00 占位
    payload = bytes([0x00]) + frame
    return payload + bytes(max(0, REPORT_LEN - len(payload)))


def send(dev, payload):
    buf = ctypes.create_string_buffer(payload, len(payload))
    ctypes.set_last_error(0)
    ok = hw.hid.HidD_SetOutputReport(dev.handle, buf, len(payload))
    return bool(ok), ctypes.get_last_error()


def main() -> None:
    seconds = 90.0
    if "--seconds" in sys.argv:
        seconds = float(sys.argv[sys.argv.index("--seconds") + 1])

    items = [d for d in hw.enumerate_hid()
             if d.vid == VID and d.output_len and not d.reserved]
    devs = [(d.describe_usage(), d, HidDevice(d.path, write=True)) for d in items]
    print("集合：", [t for t, _, _ in devs], flush=True)
    print("持续发 getInfo(3)/getBase(4)…，请按 K87S 的按键把它叫醒", flush=True)

    cmds = [zframe(3), zframe(4)]
    end = time.monotonic() + seconds
    n = 0
    while time.monotonic() < end:
        for tag, it, dev in devs:
            for frame in cmds:
                for _, _, d in devs:
                    d.drain()
                ok, err = send(dev, build(frame))
                n += 1
                t = time.monotonic() + 0.12
                while time.monotonic() < t:
                    for n2, _, d2 in devs:
                        r = d2.read_input(timeout_ms=25)
                        if r:
                            print(f"[{tag}] 收到[{n2}] {r[:48].hex(' ')}", flush=True)
        time.sleep(0.05)
    print(f"共发送 {n} 帧，结束", flush=True)
    for _, _, d in devs:
        d.close()


if __name__ == "__main__":
    main()
