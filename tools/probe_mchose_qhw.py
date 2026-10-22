# -*- coding: utf-8 -*-
"""迈从 K87S：按官方 Qhw 协议（class J）发查询包，看有没有回包。

官方组帧（来自 mchose.com.cn/cizhou 的 JS）：
    线上字节 = [报告ID][version=1][flags=3][length][cmdLo][cmdHi][biz=0][seq][payload…][cs]
    cs = XOR(帧[1:])          # 从 version 开始异或，不含报告 ID
    整个包补零到 HID 输出报告长度

命令（官方 Channel:QhwKeyboard）：
    2304 getBaseInfo / 2305 getFwVersion / 2308 getBattery
    getBattery 回包 data = [充电状态, 电量%]

Windows 侧的集合只有 RID 0x00（长 65），所以先按 RID=0x00 发；
同时也试官方写的 RID=0x4D（Windows 大概率会拒，err=87，不会下发）。
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hid_win as hw
from hid_win import HidDevice, HidError

VID = 0x3837
CHANNELS = [(0x0001, 0x0000), (0xFF31, 0x0074), (0xFF70, 0x0071)]


def mframe(command: int, payload: bytes = b"", seq: int = 0,
           version: int = 1, flags: int = 3, biz: int = 0) -> bytes:
    """官方 class J 的协议帧（不含报告 ID）。"""
    header = [version, flags, len(payload),
              command & 0xFF, (command >> 8) & 0xFF, biz & 0xFF, seq & 0xFF]
    body = header + list(payload)
    cs = 0
    for b in body[1:]:
        cs ^= b
    return bytes(body + [cs])


CANDIDATES = [
    ("getBattery  cmd=2308 (RID=0x00)", bytes([0x00]) + mframe(2308)),
    ("getBaseInfo cmd=2304 (RID=0x00)", bytes([0x00]) + mframe(2304)),
    ("getFwVer    cmd=2305 (RID=0x00)", bytes([0x00]) + mframe(2305, b"\x00")),
    ("getBattery  cmd=2308 (RID=0x4D)", bytes([0x4D]) + mframe(2308)),
]


def dump(data: bytes) -> None:
    for i in range(0, min(len(data), 24), 8):
        print(f"        {i:3d}: " + " ".join(f"{b:02x}" for b in data[i:i + 8]))


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ifaces = [d for d in hw.enumerate_hid()
              if d.vid == VID and d.output_len and not d.reserved
              and (d.usage_page, d.usage) in CHANNELS]
    readers = []
    writers = []
    for d in ifaces:
        try:
            readers.append((d, HidDevice(d.path, write=False)))
        except HidError as e:
            print("读句柄失败", e)
        try:
            writers.append((d, HidDevice(d.path, write=True)))
        except HidError as e:
            print("写句柄失败", e)

    def drain(tag: str, seconds: float = 1.5) -> None:
        end = time.monotonic() + seconds
        got = False
        while time.monotonic() < end:
            for d, dev in readers:
                try:
                    data = dev.read_input(timeout_ms=40)
                except HidError:
                    continue
                if not data:
                    continue
                got = True
                print(f"      << [{tag}] 0x{d.usage_page:04X}:0x{d.usage:04X} len={len(data)}")
                dump(data)
        if not got:
            print(f"      << [{tag}] (无回包)")

    try:
        for label, frame in CANDIDATES:
            print(f"\n===== {label} =====")
            print("   线上字节:", frame.hex(" "))
            for d, dev in writers:
                payload = frame + bytes(max(0, d.output_len - len(frame)))
                print(f"   -> 集合 0x{d.usage_page:04X}:0x{d.usage:04X} "
                      f"(补零到 {d.output_len} 字节)")
                try:
                    dev.write_output(payload)
                    print("      写入成功")
                except HidError as e:
                    print("      写入失败:", e)
                    continue
                drain(label, 1.5)
    finally:
        for _, dev in readers + writers:
            try:
                dev.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
