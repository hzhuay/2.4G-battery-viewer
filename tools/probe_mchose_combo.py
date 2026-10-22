# -*- coding: utf-8 -*-
"""迈从 K87S：getBattery 查询包组合测试。

变量：报告 ID(0x00/0x4D) × 写入长度(9/32/33/64/65) × flags(1/3)，
序号 seq 每次自增（官方 obtainSequenceId 就是自增的）。
每个组合连发 3 次、每次间隔 1.5 秒，期间持续监听所有集合。
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
RIDS = [0x00, 0x4D]
LENGTHS = [9, 32, 33, 64, 65]
FLAGS = [3, 1]
REPEATS = 3

_seq = [0]


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

    stop = False
    hits = []

    def pump() -> None:
        nonlocal stop
        while not stop:
            for d, dev in readers:
                try:
                    data = dev.read_input(timeout_ms=20)
                except HidError:
                    continue
                if not data:
                    continue
                t = data[1:] if data[0] == 0x00 else data
                if len(t) >= 3 and t[0] == 0xFA and t[1] == 0xFB:
                    kind = ("电量 %d%% 充电=%d" % (t[3], t[4])) if t[2] == 0x07 \
                        else ("cmd 0x%02X" % t[2])
                    print(f"   ★ 收到 AT 帧 [{t[:6].hex(' ')}] {kind}  "
                          f"(来自 0x{d.usage_page:04X}:0x{d.usage:04X})", flush=True)
                    hits.append(t)

    import threading
    th = threading.Thread(target=pump, daemon=True)
    th.start()
    time.sleep(0.5)

    try:
        for rid in RIDS:
            for ln in LENGTHS:
                for flags in FLAGS:
                    for d, dev in writers:
                        if ln < 9:
                            continue
                        for _ in range(REPEATS):
                            _seq[0] = (_seq[0] + 1) & 0xFF
                            body = mframe(2308, seq=_seq[0], flags=flags)
                            frame = bytes([rid]) + body
                            if len(frame) > ln:
                                break
                            payload = frame + bytes(ln - len(frame))
                            try:
                                dev.write_output(payload)
                            except HidError:
                                break
                            time.sleep(1.5)
        print(f"\n总共收到 {len(hits)} 个 AT 帧")
    finally:
        stop = True
        time.sleep(0.3)
        for _, dev in readers + writers:
            try:
                dev.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
