# -*- coding: utf-8 -*-
"""watch.py —— 并行监听多个厂商的所有 HID 接口（只读）

用于「设备只在有动作时才上报电量」的场景：雷柏的电量是鼠标上报时捎带的，
迈从的键盘同理。所以要一边监听一边动设备。

用法：
    python watch.py 24AE 3837 --seconds 90
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("vids", nargs="+", help="十六进制 VID 列表")
    ap.add_argument("--seconds", type=float, default=60.0)
    args = ap.parse_args()

    vids = {int(v, 16) for v in args.vids}
    items = [x for x in hw.enumerate_hid() if x.vid in vids]
    if not items:
        print("没有匹配的设备")
        return

    devs = []
    for it in items:
        if not it.input_len:
            continue
        try:
            devs.append((f"{it.vid_pid} {it.describe_usage()}",
                         HidDevice(it.path, write=False)))
        except HidError as e:
            print(f"打开 {it.describe_usage()} 失败：{e}")
    print(f"监听 {len(devs)} 个接口，{args.seconds:.0f} 秒 —— 请动一动鼠标/键盘！")

    end = time.monotonic() + args.seconds
    count = 0
    seen: dict[str, bytes] = {}
    while time.monotonic() < end:
        for tag, dev in devs:
            r = dev.read_input(timeout_ms=40)
            if not r:
                continue
            count += 1
            key = tag + r.hex()
            if key in seen:
                continue
            seen[key] = r
            print(f"  [{tag}] len={len(r)}  {r.hex(' ')}", flush=True)
    print(f"共收到 {count} 条，去重后 {len(seen)} 条")
    for _, d in devs:
        d.close()


if __name__ == "__main__":
    main()
