# -*- coding: utf-8 -*-
"""迈从 K87S：发一包官方 CZ 电量查询（55 30），听回复。

帧来自官方驱动：e[0..10] = 00 55 30 a5 0b 2e 01 01 01 00 00，其余补零到 65。
期望回复：AA 30 ... 第 8 字节电量、第 9 字节充电标志。

只发这一包。用法：python tools/probe_mchose_battery30.py --seconds 20
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hid_win as hw
from hid_win import HidDevice, HidError

VID = 0x3837
FRAME = bytes([0x00, 0x55, 0x30, 0xA5, 0x0B, 0x2E, 0x01, 0x01, 0x01, 0x00, 0x00])
REPORT_LEN = 65


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--hidd", action="store_true", help="用 HidD_SetOutputReport（默认 WriteFile）")
    args = ap.parse_args()

    target = next((d for d in hw.enumerate_hid()
                   if d.vid == VID and d.usage_page == 0x0001 and d.usage == 0x0000
                   and d.output_len and not d.reserved), None)
    if target is None:
        print("找不到命令通道")
        return

    payload = FRAME + bytes(REPORT_LEN - len(FRAME))
    print(f"发送：{payload.hex(' ')}")

    readers = []
    for d in hw.enumerate_hid():
        if d.vid != VID or not d.input_len:
            continue
        try:
            readers.append((d, HidDevice(d.path, write=False)))
        except HidError:
            pass

    try:
        dev = HidDevice(target.path, write=True)
    except HidError as e:
        print("写句柄失败：", e)
        return
    try:
        dev.write_output(payload, use_hidd=args.hidd)
        print("已发出，开始监听…\n")
    except HidError as e:
        print("发送失败：", e)
        dev.close()
        return

    t0 = time.monotonic()
    seen = {}
    try:
        while time.monotonic() - t0 < args.seconds:
            for d, rd in readers:
                data = rd.read_input(timeout_ms=25)
                if not data:
                    continue
                ts = time.monotonic() - t0
                key = data
                seen[key] = seen.get(key, 0) + 1
                print(f"  +{ts:5.1f}s 0x{d.usage_page:04X}:0x{d.usage:04X} "
                      f"{data[:14].hex(' ')}")
    finally:
        dev.close()
        for _, rd in readers:
            rd.close()

    print()
    if seen:
        print(f"去重 {len(seen)} 帧")
        for k, v in seen.items():
            if k[1] == 0xAA and k[2] == 0x30:
                print(f"★ AA 30 电量帧：{k.hex(' ')}  -> 电量={k[8]} 充电={k[9]}")
    else:
        print("零回包")


if __name__ == "__main__":
    main()
