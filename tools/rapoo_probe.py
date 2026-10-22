# -*- coding: utf-8 -*-
"""rapoo_probe.py —— 雷柏接收器（VID 24AE）只读探测

两部分：
  1. Feature Report 全量扫描：把 0x00~0xFF 的报告 ID 都读一遍
     （ HidD_GetFeature 只会对**描述符里存在**的报告 ID 成功，其它直接报错）
  2. 并行监听所有接口的 Input Report —— 需要你在监听期间动一下鼠标，
     因为雷柏的电量是「鼠标上报时捎带」发出来的（Linux 内核 hid-rapoo 驱动就是这么做的：
     电量在键盘接口的 13 字节报文第 8 字节）。

不发送任何数据。
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

RAPOO_VID = 0x24AE


def scan_features(iface) -> None:
    if not iface.feature_len:
        return
    print(f"  [Feature 扫描] {iface.describe_usage()} 长度={iface.feature_len}")
    try:
        with HidDevice(iface.path, write=False) as dev:
            for rid in range(0x00, 0x100):
                try:
                    data = dev.get_feature_report(rid)
                except HidError:
                    continue
                payload = data[1:]
                pct = [i for i, b in enumerate(payload) if 1 <= b <= 100]
                print(f"    RID 0x{rid:02X}: {data[:24].hex(' ')}"
                      f"   （1~100 的字节位置：{pct[:10]}）")
    except HidError as e:
        print(f"    打开失败：{e}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--no-features", action="store_true")
    args = ap.parse_args()

    items = [x for x in hw.enumerate_hid() if x.vid == RAPOO_VID]
    if not items:
        print("没找到雷柏设备")
        return

    if not args.no_features:
        print("=== Feature Report 全量扫描 ===")
        for it in items:
            scan_features(it)

    print(f"\n=== 并行监听 {args.seconds:.0f} 秒（请动一动鼠标！） ===")
    devs = []
    for it in items:
        if not it.input_len:
            continue
        try:
            devs.append((it.describe_usage(), HidDevice(it.path, write=False)))
        except HidError as e:
            print(f"  打开 {it.describe_usage()} 失败：{e}")

    end = time.monotonic() + args.seconds
    count = 0
    while time.monotonic() < end:
        for tag, dev in devs:
            r = dev.read_input(timeout_ms=40)
            if not r:
                continue
            count += 1
            print(f"  [{tag}] len={len(r)}  {r.hex(' ')}")
    print(f"共收到 {count} 条报文")
    for _, d in devs:
        d.close()


if __name__ == "__main__":
    main()
