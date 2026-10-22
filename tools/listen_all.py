# -*- coding: utf-8 -*-
"""listen_all.py —— 被动监听某个厂商的所有 HID 接口 + 转储 Feature Report

**只读**：不发送任何数据。分两部分：
  1. 监听各接口的 Input Report，看设备是否主动上报电量
  2. 有 Feature Report 的接口，把 Feature Report 全读一遍
     （标准 HID 电量字段就藏在这里，命中的话完全不需要发包）

用法：
    python listen_all.py 25A7        # 按 VID 过滤（十六进制，可省略）
    python listen_all.py 25A7 --seconds 15
"""

from __future__ import annotations

import argparse
import sys
import time

import hid_win as hw
from hid_win import HidDevice, HidError

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def listen(iface, seconds: float) -> int:
    n = 0
    end = time.monotonic() + seconds
    try:
        dev = HidDevice(iface.path, write=False)
    except HidError as e:
        print(f"    打开失败：{e}")
        return 0
    try:
        while time.monotonic() < end:
            r = dev.read_input(timeout_ms=200)
            if not r:
                continue
            n += 1
            print(f"    收到 [{len(r)}] {r[:40].hex(' ')}")
            if n >= 40:
                print("    （够了，停止监听）")
                break
    except HidError as e:
        print(f"    监听出错：{e}")
    finally:
        dev.close()
    return n


def dump_features(iface) -> None:
    if not iface.feature_len:
        return
    try:
        with HidDevice(iface.path, write=False) as dev:
            ids = sorted({c.ReportID for c in dev.value_caps(hw.HidP_Feature)}) or list(range(0, 9))
            for rid in ids:
                try:
                    data = dev.get_feature_report(rid)
                except HidError:
                    continue
                interesting = [i for i, b in enumerate(data[1:], 1) if 1 <= b <= 100]
                print(f"    Feature 0x{rid:02X}: {data[:32].hex(' ')}"
                      + (f"   （疑似百分值的字节位置：{interesting[:8]}）" if interesting else ""))
    except HidError as e:
        print(f"    Feature 读取失败：{e}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("vid", nargs="?", default=None, help="十六进制 VID")
    ap.add_argument("--seconds", type=float, default=8.0)
    args = ap.parse_args()

    vid = int(args.vid, 16) if args.vid else None
    items = hw.enumerate_hid()
    if vid:
        items = [x for x in items if x.vid == vid]
    if not items:
        print("没有匹配的 HID 接口")
        return

    groups: dict[str, list] = {}
    for it in items:
        groups.setdefault(it.group, []).append(it)

    for group, lst in groups.items():
        print(f"\n■ {hw.pick_device_name(lst)}  ({lst[0].vid_pid})")
        for it in lst:
            tag = "厂商接口" if it.is_vendor_page else ("系统独占" if it.reserved else "标准")
            print(f"  - {it.describe_usage()}  {tag}  "
                  f"in={it.input_len} out={it.output_len} feat={it.feature_len}  {it.product}")
            if it.input_len:
                print(f"    监听 {args.seconds:.0f} 秒…")
                n = listen(it, args.seconds)
                if not n:
                    print("    （没有主动上报）")
            dump_features(it)


if __name__ == "__main__":
    main()
