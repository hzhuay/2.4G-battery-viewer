# -*- coding: utf-8 -*-
"""迈从 K87S：发官方握手帧（cmd3 getInfo / cmd4 getBase），把设备所有回应按索引完整 dump。

只发社区/官方已在使用的两条握手帧（0x55 0x03 ... / 0x55 0x04 ...），
不写系统独占的键鼠接口，不改设备配置。
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hid_win as hw
from hid_win import HidDevice, HidError

VID = 0x3837

# 官方握手帧（社区项目同款）
Z_GET3 = bytes([0x55, 0x03, 0x00, 0x38, 0x38, 0x00, 0x00, 0x00])
Z_GET4 = bytes([0x55, 0x04, 0x00, 0x38, 0x38, 0x00, 0x00, 0x00])


def dump(data: bytes) -> None:
    print("      " + " ".join(f"{b:02x}" for b in data))
    for i in range(0, len(data), 8):
        print(f"   {i:3d}: " + " ".join(f"{b:02x}" for b in data[i:i + 8]))


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ifaces = [d for d in hw.enumerate_hid() if d.vid == VID]
    print("=== 迈从接收器接口 ===")
    for d in ifaces:
        print(f"  {d.vid_pid} up=0x{d.usage_page:04X} us=0x{d.usage:04X} "
              f"in={d.input_len} out={d.output_len} reserved={d.reserved} {d.path}")

    # 只在能写的厂商集合上开句柄
    targets = [d for d in ifaces
               if d.output_len and not d.reserved and d.usage_page != 0x0001 or
               (d.output_len and not d.reserved and d.usage == 0x0000)]
    targets = [d for d in ifaces if d.output_len and not d.reserved]
    print("\n可写集合：", [(d.usage_page, d.usage, d.output_len) for d in targets])

    readers = []
    for d in ifaces:
        if not d.input_len:
            continue
        try:
            readers.append((d, HidDevice(d.path, write=False)))
        except HidError as e:
            print("  打开读句柄失败", d.usage_page, d.usage, e)

    writers = []
    for d in targets:
        try:
            writers.append((d, HidDevice(d.path, write=True)))
        except HidError as e:
            print("  打开写句柄失败", d.usage_page, d.usage, e)

    def drain(tag: str, seconds: float = 1.5) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            for d, dev in readers:
                try:
                    data = dev.read_input(timeout_ms=40)
                except HidError:
                    continue
                if not data:
                    continue
                print(f"\n  << {tag} [{d.usage_page:04X}:{d.usage:04X}] len={len(data)}")
                dump(data)

    try:
        for label, frame in (("cmd3 getInfo", Z_GET3), ("cmd4 getBase", Z_GET4)):
            print(f"\n===== 发 {label}: {frame.hex(' ')} =====")
            for d, dev in writers:
                payload = bytes([0x00]) + frame
                payload += bytes(d.output_len - len(payload))
                print(f"  -> 集合 0x{d.usage_page:04X}:0x{d.usage:04X}  "
                      f"共 {d.output_len} 字节")
                try:
                    dev.write_output(payload)
                    print("     写入成功")
                except HidError as e:
                    print("     写入失败:", e)
            drain(label, 2.0)
    finally:
        for _, dev in readers + writers:
            try:
                dev.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
