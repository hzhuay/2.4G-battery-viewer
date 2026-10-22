# -*- coding: utf-8 -*-
"""迈从 K87S：持续发 getBattery 查询 2 分钟，全程监听 AT 帧，看回复是否延迟到达。"""
from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hid_win as hw
from hid_win import HidDevice, HidError

VID = 0x3837
DURATION = 120.0
PERIOD = 10.0

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

    ifaces = [d for d in hw.enumerate_hid() if d.vid == VID and d.output_len
              and not d.reserved]
    readers = []
    for d in ifaces:
        try:
            readers.append((d, HidDevice(d.path, write=False)))
        except HidError:
            pass

    target = next((d for d in ifaces
                   if (d.usage_page, d.usage) == (0x0001, 0x0000)), None)
    if target is None:
        print("找不到命令通道")
        return
    print("命令通道:", target.vid_pid, hex(target.usage_page), hex(target.usage),
          "out=", target.output_len)

    stop = False
    t0 = time.monotonic()

    def pump() -> None:
        while not stop:
            for d, dev in readers:
                try:
                    data = dev.read_input(timeout_ms=20)
                except HidError:
                    continue
                if not data:
                    continue
                t = data[1:] if data[0] == 0x00 else data
                ts = time.monotonic() - t0
                if len(t) >= 3 and t[0] == 0xFA and t[1] == 0xFB:
                    kind = (f"电量 {t[3]}% 充电={t[4]}" if t[2] == 0x07
                            else f"cmd 0x{t[2]:02X} arg={t[3]}")
                    print(f"  [{ts:7.2f}s] ★ AT 帧 {t[:8].hex(' ')}  {kind}"
                          f"  (0x{d.usage_page:04X}:0x{d.usage:04X})", flush=True)
                elif any(t[:6]):
                    print(f"  [{ts:7.2f}s]   其它帧 {t[:10].hex(' ')}"
                          f"  (0x{d.usage_page:04X}:0x{d.usage:04X})", flush=True)

    th = threading.Thread(target=pump, daemon=True)
    th.start()

    try:
        dev = HidDevice(target.path, write=True)
    except HidError as e:
        print("写句柄打开失败:", e)
        return
    try:
        n = int(DURATION / PERIOD)
        for i in range(n):
            _seq[0] = (_seq[0] + 1) & 0xFF
            frame = bytes([0x00]) + mframe(2308, seq=_seq[0])
            payload = frame + bytes(target.output_len - len(frame))
            try:
                dev.write_output(payload)
                print(f"[{time.monotonic()-t0:7.2f}s] 已发查询 #{i+1} "
                      f"seq={_seq[0]}  {frame.hex(' ')}", flush=True)
            except HidError as e:
                print("  写失败:", e)
            time.sleep(PERIOD)
    finally:
        stop = True
        time.sleep(0.3)
        dev.close()
        for _, d in readers:
            try:
                d.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
