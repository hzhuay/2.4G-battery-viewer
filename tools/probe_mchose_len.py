# -*- coding: utf-8 -*-
"""迈从 K87S：class-P（Z 帧）getInfo 查询 + 写入长度扫描。

class P 组帧（官方）：
    [0x55][cmd][0x00][cs][size][offLo][offHi][0x00]
    cs = XOR(size, offLo, offHi, 0) = 56 → 55 03 00 38 38 00 00 00
怀疑设备真正的输出报告长度不是 65，所以把长度从 8 扫到 65。
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hid_win as hw
from hid_win import HidDevice, HidError

VID = 0x3837
FRAME = bytes([0x00, 0x55, 0x03, 0x00, 0x38, 0x38, 0x00, 0x00, 0x00])
LENGTHS = [8, 9, 10, 11, 12, 13, 16, 20, 24, 32, 33, 40, 48, 55, 56, 57,
           60, 62, 63, 64, 65]


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    target = next((d for d in hw.enumerate_hid()
                   if d.vid == VID and d.usage_page == 0x0001 and d.usage == 0x0000
                   and d.output_len and not d.reserved), None)
    if target is None:
        print("找不到命令通道")
        return
    readers = []
    for d in hw.enumerate_hid():
        if d.vid == VID and d.input_len:
            try:
                readers.append((d, HidDevice(d.path, write=False)))
            except HidError:
                pass

    def drain(seconds: float = 1.0) -> list:
        out = []
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            for d, dev in readers:
                try:
                    data = dev.read_input(timeout_ms=25)
                except HidError:
                    continue
                if data:
                    out.append((d, data))
        return out

    try:
        dev = HidDevice(target.path, write=True)
    except HidError as e:
        print("写句柄失败:", e)
        return
    try:
        for ln in LENGTHS:
            if ln < len(FRAME):
                continue
            payload = FRAME + bytes(ln - len(FRAME))
            try:
                dev.write_output(payload)
                status = "写入成功"
            except HidError as e:
                status = f"写入失败: {e}"
                print(f"  len={ln:3d}  {status}")
                continue
            got = drain(1.0)
            desc = ""
            if got:
                desc = "  ★ 收到: " + "; ".join(
                    f"0x{d.usage_page:04X}:0x{d.usage:04X} {x[:12].hex(' ')}"
                    for d, x in got)
            print(f"  len={ln:3d}  {status}{desc}")
    finally:
        dev.close()
        for _, d in readers:
            try:
                d.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
