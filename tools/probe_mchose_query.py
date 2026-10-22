# -*- coding: utf-8 -*-
"""迈从 K87S：逐个集合发官方 getBattery（cmd 2308），听 20 秒看有没有 FA FB 07 回来。

官方协议（mchose.com.cn/cizhou JS 的 class J）：
    线上 = [RID][version=1][flags=3][length=0][cmdLo=04][cmdHi=09][biz=0][seq][cs]
    cs = XOR(帧[1:])
回复是异步推送：FA FB 07 <电量%> <充电标志>
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
LISTEN_SECONDS = 20.0


def mframe(command: int, payload: bytes = b"", seq: int = 0,
           version: int = 1, flags: int = 3, biz: int = 0) -> bytes:
    header = [version, flags, len(payload),
              command & 0xFF, (command >> 8) & 0xFF, biz & 0xFF, seq & 0xFF]
    body = header + list(payload)
    cs = 0
    for b in body[1:]:
        cs ^= b
    return bytes(body + [cs])


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ifaces = [d for d in hw.enumerate_hid()
              if d.vid == VID and d.output_len and not d.reserved
              and (d.usage_page, d.usage) in CHANNELS]
    readers, writers = [], []
    for d in ifaces:
        try:
            readers.append((d, HidDevice(d.path, write=False)))
        except HidError:
            pass
        try:
            writers.append((d, HidDevice(d.path, write=True)))
        except HidError:
            pass

    def listen(seconds: float, label: str) -> list:
        out = []
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            for d, dev in readers:
                try:
                    data = dev.read_input(timeout_ms=30)
                except HidError:
                    continue
                if not data:
                    continue
                t = data[1:] if data and data[0] == 0x00 else data
                if len(t) >= 3 and t[0] == 0xFA and t[1] == 0xFB:
                    if t[2] == 0x07:
                        print(f"   ★[{label}] 电量推送: {t[:6].hex(' ')} "
                              f"-> {t[3]}%  充电={t[4]}")
                    else:
                        print(f"    [{label}] AT 帧: {t[:6].hex(' ')}")
                out.append((d, data))
        return out

    frame = bytes([0x00]) + mframe(2308)
    print("getBattery 查询包:", frame.hex(" "))
    try:
        # 先静听 5 秒，作为基线
        print("\n--- 基线静听 5 秒（不发包）---")
        listen(5.0, "基线")

        for d, dev in writers:
            print(f"\n--- 发到 0x{d.usage_page:04X}:0x{d.usage:04X}，"
                  f"然后听 {LISTEN_SECONDS:.0f} 秒 ---")
            payload = frame + bytes(d.output_len - len(frame))
            try:
                dev.write_output(payload)
                print("   写入成功")
            except HidError as e:
                print("   写入失败:", e)
                continue
            listen(LISTEN_SECONDS, f"0x{d.usage_page:04X}:0x{d.usage:04X}")
    finally:
        for _, dev in readers + writers:
            try:
                dev.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
