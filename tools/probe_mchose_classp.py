# -*- coding: utf-8 -*-
"""迈从 K87S：单发一次 class-P getInfo，强制走 WriteFile，然后听 30 秒。

只发一包，65 字节：
    00 55 03 00 38 38 00 00 00 + 56 个 0x00
第 0 字节是 Windows 侧报告 ID（0x00），线上数据是 55 03 00 38 38 00 00 00。

发完把 30 秒内所有接口收到的原始帧按十六进制打出来（不筛 FA FB），
用来判断是「完全无回包」还是「回包格式不认识」。

用法：python tools/probe_mchose_classp.py [--seconds 30]
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
FRAME = bytes([0x00, 0x55, 0x03, 0x00, 0x38, 0x38, 0x00, 0x00, 0x00])
REPORT_LEN = 65


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=30.0)
    args = ap.parse_args()

    target = next((d for d in hw.enumerate_hid()
                   if d.vid == VID and d.usage_page == 0x0001 and d.usage == 0x0000
                   and d.output_len and not d.reserved), None)
    if target is None:
        print("找不到命令通道 0x0001:0x0000")
        return

    payload = FRAME + bytes(REPORT_LEN - len(FRAME))
    print(f"目标：{target.vid_pid} {target.describe_usage()} out={target.output_len}")
    print(f"发送（WriteFile）：{payload.hex(' ')}")

    readers = []
    for d in hw.enumerate_hid():
        if d.vid != VID or not d.input_len:
            continue
        try:
            readers.append((d, HidDevice(d.path, write=False)))
        except HidError as e:
            print(f"  监听 {d.describe_usage()} 打不开：{e}")
    print(f"监听 {len(readers)} 个接口 {args.seconds:.0f} 秒…\n")

    try:
        dev = HidDevice(target.path, write=True)
    except HidError as e:
        print("写句柄打开失败：", e)
        for _, r in readers:
            r.close()
        return

    try:
        dev.write_output(payload, use_hidd=False)
        print("  写入成功（WriteFile 返回 OK）\n")
    except HidError as e:
        print("  写入失败：", e)
        return
    finally:
        pass

    t0 = time.monotonic()
    seen: dict[bytes, int] = {}
    try:
        while time.monotonic() - t0 < args.seconds:
            for d, rd in readers:
                try:
                    data = rd.read_input(timeout_ms=25)
                except HidError:
                    continue
                if not data:
                    continue
                key = data
                seen[key] = seen.get(key, 0) + 1
                print(f"  +{time.monotonic() - t0:5.1f}s "
                      f"0x{d.usage_page:04X}:0x{d.usage:04X} "
                      f"len={len(data):3d}  {data.hex(' ') if len(data) <= 24 else data[:24].hex(' ') + ' …'}")
    finally:
        dev.close()
        for _, rd in readers:
            try:
                rd.close()
            except Exception:
                pass

    print()
    if seen:
        print(f"共收到 {sum(seen.values())} 条，去重 {len(seen)} 条")
    else:
        print("30 秒内零回包")


if __name__ == "__main__":
    main()
