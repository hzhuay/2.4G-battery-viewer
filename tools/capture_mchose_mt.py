# -*- coding: utf-8 -*-
"""迈从 K87S：每接口一条线程并行监听，避免串行轮询漏帧。

只读，不发任何字节。用法：
    python tools/capture_mchose_mt.py --seconds 150 --out mchose_capture.log
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hid_win as hw
from hid_win import HidDevice, HidError

VID = 0x3837


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=150)
    ap.add_argument("--out", default="mchose_capture.log")
    args = ap.parse_args()

    ifaces = [d for d in hw.enumerate_hid() if d.vid == VID and d.input_len]
    stop = threading.Event()
    lock = threading.Lock()
    fh = open(args.out, "w", encoding="utf-8")
    fh.write(f"# 多线程监听 {len(ifaces)} 个接口，{args.seconds:.0f} 秒\n")
    fh.flush()
    t0 = time.monotonic()
    total = [0]

    def worker(d: hw.HidInterface) -> None:
        try:
            dev = HidDevice(d.path, write=False)
        except HidError as e:
            with lock:
                fh.write(f"# 打开失败 0x{d.usage_page:04X}:0x{d.usage:04X} {e}\n")
                fh.flush()
            return
        try:
            while not stop.is_set():
                try:
                    data = dev.read_input(timeout_ms=120)
                except HidError:
                    continue
                if not data:
                    continue
                ts = time.monotonic() - t0
                with lock:
                    total[0] += 1
                    fh.write(f"\n[{ts:8.3f}s] 0x{d.usage_page:04X}:0x{d.usage:04X} len={len(data)}\n")
                    for i in range(0, len(data), 8):
                        fh.write(f"  {i:3d}: " + " ".join(f"{b:02x}" for b in data[i:i + 8]) + "\n")
                    fh.flush()
                    print(f"[{ts:8.3f}s] 0x{d.usage_page:04X}:0x{d.usage:04X} "
                          f"len={len(data)} {data[:20].hex(' ')}", flush=True)
        finally:
            dev.close()

    threads = [threading.Thread(target=worker, args=(d,), daemon=True) for d in ifaces]
    for t in threads:
        t.start()
    try:
        while time.monotonic() - t0 < args.seconds:
            time.sleep(0.2)
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=1.0)
        fh.write(f"\n# 共 {total[0]} 帧\n")
        fh.close()
    print(f"共 {total[0]} 帧 -> {args.out}")


if __name__ == "__main__":
    main()
