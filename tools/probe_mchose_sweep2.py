# -*- coding: utf-8 -*-
"""迈从 K87S：扫「报告长度 × 报告 ID」的组合，发官方 getBattery 查询包。

Windows 的 HidD_SetOutputReport 要求写入长度正好等于该报告 ID 的长度，
长度不对直接 err=87（一个字节都不会下发），所以扫长度是安全的。
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
LENGTHS = [9, 10, 24, 31, 32, 33, 63, 64, 65]
RIDS = [0x00, 0x4D]


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

    body = mframe(2308)          # getBattery，9 字节（含 cs）
    print("M 帧（不含报告 ID）:", body.hex(" "))

    def drain(seconds: float = 0.8) -> list:
        out = []
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            for d, dev in readers:
                try:
                    data = dev.read_input(timeout_ms=30)
                except HidError:
                    continue
                if data:
                    out.append((d, data))
        return out

    try:
        for rid in RIDS:
            for ln in LENGTHS:
                for d, dev in writers:
                    frame = bytes([rid]) + body
                    if len(frame) > ln:
                        continue
                    payload = frame + bytes(ln - len(frame))
                    try:
                        dev.write_output(payload)
                        err = 0
                    except HidError as e:
                        err = getattr(e, "winerror", 0) or 0
                        if err:
                            continue          # 长度不对，Windows 已拒绝，不算
                    got = drain(0.8)
                    tag = (f"RID=0x{rid:02X} len={ln} "
                           f"0x{d.usage_page:04X}:0x{d.usage:04X}")
                    if got:
                        print(f"★ 回包！{tag}")
                        for dd, data in got:
                            print(f"    [0x{dd.usage_page:04X}:0x{dd.usage:04X}] "
                                  f"{data[:24].hex(' ')}")
                    else:
                        print(f"  {tag} 发送成功，无回包")
    finally:
        for _, dev in readers + writers:
            try:
                dev.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
