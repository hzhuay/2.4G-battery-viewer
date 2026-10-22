# -*- coding: utf-8 -*-
"""迈从 K87S：全集合被动监听，把每帧完整 hex + 索引写进日志文件。

只读，不发任何字节。用法：
    python tools/capture_mchose.py --seconds 600 --out cap.log
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=600)
    ap.add_argument("--out", default="mchose_capture.log")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ifaces = [d for d in hw.enumerate_hid() if d.vid == VID and d.input_len]
    readers = []
    for d in ifaces:
        try:
            readers.append((d, HidDevice(d.path, write=False)))
        except HidError as e:
            print("打开失败", d.usage_page, d.usage, e)

    t0 = time.monotonic()
    n = 0
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(f"# 迈从监听 {len(readers)} 个接口，{args.seconds:.0f} 秒\n")
        while time.monotonic() - t0 < args.seconds:
            for d, dev in readers:
                try:
                    data = dev.read_input(timeout_ms=30)
                except HidError:
                    continue
                if not data:
                    continue
                n += 1
                ts = time.monotonic() - t0
                fh.write(f"\n[{ts:8.3f}s] 0x{d.usage_page:04X}:0x{d.usage:04X} len={len(data)}\n")
                for i in range(0, len(data), 8):
                    fh.write(f"  {i:3d}: " + " ".join(f"{b:02x}" for b in data[i:i + 8]) + "\n")
                fh.flush()
                print(f"[{ts:8.3f}s] 0x{d.usage_page:04X}:0x{d.usage:04X} "
                      f"len={len(data)} {data[:20].hex(' ')}")

    for _, dev in readers:
        try:
            dev.close()
        except Exception:
            pass
    print(f"共 {n} 帧 -> {args.out}")


if __name__ == "__main__":
    main()
