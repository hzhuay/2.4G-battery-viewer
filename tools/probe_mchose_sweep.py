# -*- coding: utf-8 -*-
"""tools/probe_mchose_sweep.py —— 迈从 K87S 命令帧全排列扫描

官方网页驱动的 M 帧（WebHID）：
    sendReport(reportId=0x4D, data = [version=1][flags][len][cmdLo][cmdHi][biz][seq][cs])
    cs = 除 version 外全部 XOR
    命令 0x0900=getBaseInfo（data[10]=连接 data[11]=充电 data[12]=电量）
         0x0904=getBattery （data[0]=充电 data[1]=电量）

Windows 与 Linux 的差异：
    Linux(hidraw) 把整份报文原样送出；
    Windows(HidD_SetOutputReport) 会把第 0 字节当报告 ID 剥掉。
    所以有两种可能的线上形态：
        A) 缓冲 [4D][01 flags ... cs]      → 设备收到 [01 flags ... cs]
        B) 缓冲 [00][4D][01 flags ... cs]   → 设备收到 [4D 01 flags ... cs]

本脚本把 通道 × 形态 × flags × seq × 命令号 全试一遍，只写厂商集合
（绝不碰系统独占的键盘输入接口 usage 0x0001:0x0006）。
"""

from __future__ import annotations

import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hid_win as hw
from hid_win import HidDevice

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VID = 0x3837
REPORT_LEN = 65


def build_body(flags: int, cmd: int, seq: int) -> bytes:
    body = bytes([0x01, flags, 0x00, cmd & 0xFF, (cmd >> 8) & 0xFF, 0x00, seq])
    cs = 0
    for b in body[1:]:
        cs ^= b
    return body + bytes([cs])


def build(shape: str, body: bytes) -> bytes:
    payload = (bytes([0x4D]) + body) if shape == "A" else (bytes([0x00, 0x4D]) + body)
    return payload + bytes(max(0, REPORT_LEN - len(payload)))


def send(dev, payload):
    buf = ctypes.create_string_buffer(payload, len(payload))
    ctypes.set_last_error(0)
    ok = hw.hid.HidD_SetOutputReport(dev.handle, buf, len(payload))
    return bool(ok), ctypes.get_last_error()


def main() -> None:
    items = [d for d in hw.enumerate_hid()
             if d.vid == VID and d.output_len and not d.reserved]
    devs = [(d.describe_usage(), d, HidDevice(d.path, write=True)) for d in items]
    print("集合：", [t for t, _, _ in devs], flush=True)

    for tag, it, dev in devs:
        for shape in ("A", "B"):
            for flags in (1, 3):
                for seq in (0, 1):
                    for cmd in (0x0900, 0x0904):
                        for _, _, d in devs:
                            d.drain()
                        payload = build(shape, build_body(flags, cmd, seq))
                        ok, err = send(dev, payload)
                        end = time.monotonic() + 1.2
                        got = []
                        while time.monotonic() < end:
                            for n2, _, d2 in devs:
                                r = d2.read_input(timeout_ms=50)
                                if r:
                                    got.append((n2, r))
                        if got or not ok:
                            print(f"[{tag}] 形态{shape} flags={flags} seq={seq} "
                                  f"cmd=0x{cmd:04X}: "
                                  f"{'发送成功' if ok else '失败 err=' + str(err)}"
                                  f" → {len(got)} 条", flush=True)
                        for n2, r in got:
                            print(f"     [{n2}] {r[:48].hex(' ')}", flush=True)
    for _, _, d in devs:
        d.close()
    print("扫描结束", flush=True)


if __name__ == "__main__":
    main()
