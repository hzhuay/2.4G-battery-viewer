# -*- coding: utf-8 -*-
"""tools/probe_mchose_mframe.py —— 迈从 K87S 的 M 帧协议探测

背景
----
官方网页驱动（mchose.com.cn/cizhou）用的是「M 帧」：

    报文 = [4D] [version=01] [flags] [len] [cmdLo cmdHi] [biz] [seq] [data...] [cs]
    cs  = 除 version 字节以外全部 XOR

命令号：0x0900 = getBaseInfo（应答里 data[10]=连接状态、data[11]=充电、data[12]=**电量**）
        0x0904 = getBattery（应答 data[0]=充电状态、data[1]=**电量**）

坑
----
这些集合是**无编号报告**。Linux 用 hidraw 写多少字节，设备就收到多少字节；
但 Windows 的 HidD_SetOutputReport 会把**第 0 字节当报告 ID 剥掉**。
所以要把 Linux 那份报文原样送到设备，前面得补一个占位字节：

    Windows 写:  [00][4D 01 01 00 00 09 00 00 cs][补零到 65]
    设备收到:    4D 01 01 00 00 09 00 00 cs ...

只读探测：不碰键盘的标准输入接口（usage 0x0001:0x0006，系统独占），只写厂商集合。
"""

from __future__ import annotations

import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hid_win as hw
from hid_win import HidDevice, HidError

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VID = 0x3837
REPORT_LEN = 65
REPORT_ID = 0x4D


def mframe(cmd: int, flags: int = 1, data: bytes = b"") -> bytes:
    """构造 M 帧（不含报告 ID 前缀）。"""
    body = bytes([0x01, flags, len(data)]) + bytes([cmd & 0xFF, (cmd >> 8) & 0xFF]) \
        + bytes([0x00, 0x00]) + data
    cs = 0
    for b in body[1:]:
        cs ^= b
    return bytes([REPORT_ID]) + body + bytes([cs])


def build(frame: bytes, total: int = REPORT_LEN) -> bytes:
    """Windows 写缓冲：补一个占位字节给报告 ID。"""
    payload = bytes([0x00]) + frame
    return payload + bytes(max(0, total - len(payload)))


def send(dev, payload: bytes) -> tuple[bool, int]:
    buf = ctypes.create_string_buffer(payload, len(payload))
    ctypes.set_last_error(0)
    ok = hw.hid.HidD_SetOutputReport(dev.handle, buf, len(payload))
    return bool(ok), ctypes.get_last_error()


def main() -> None:
    items = [d for d in hw.enumerate_hid()
             if d.vid == VID and d.output_len and not d.reserved]
    devs = [(d.describe_usage(), d, HidDevice(d.path, write=True)) for d in items]
    print("集合：", [t for t, _, _ in devs])

    cands = []
    for flags in (1, 3):
        for cmd, name in ((0x0900, "getBaseInfo"), (0x0904, "getBattery")):
            cands.append((f"{name} flags={flags}", build(mframe(cmd, flags))))

    for tag, it, dev in devs:
        for label, payload in cands:
            for _, _, d in devs:
                d.drain()
            ok, err = send(dev, payload)
            end = time.monotonic() + 2.0
            got = []
            while time.monotonic() < end:
                for n2, _, d2 in devs:
                    r = d2.read_input(timeout_ms=60)
                    if r:
                        got.append((n2, r))
            print(f"[{tag}] {label}: {'发送成功' if ok else '失败 err=' + str(err)}"
                  f" → {len(got)} 条")
            for n2, r in got:
                print(f"     [{n2}] {r[:40].hex(' ')}")

    for _, _, d in devs:
        d.close()


if __name__ == "__main__":
    main()
