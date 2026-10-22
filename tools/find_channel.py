# -*- coding: utf-8 -*-
"""find_channel.py —— 在 G3 Max 的三个厂商集合里找「能问出电量的那个通道」

已知：输出报告 ID = 0x02（Windows 只认这一个），协议帧 = D0 35 BB 01 00。
不确定的是：往哪个集合写、回复从哪个集合回来、写多长。

做法：三个集合同时打开，往其中一个写，同时在三个上各读一轮，看 0x0A 帧从哪来。
载荷始终是官方那条只读查询命令。
"""

from __future__ import annotations

import ctypes
import sys
import time

import hid_win as hw
import edifier_proto as ep
from hid_win import HidDevice

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RID = 0x02


def send(dev, frame: bytes, total_len: int) -> bool:
    payload = bytes([RID]) + frame
    if total_len and total_len > len(payload):
        payload = payload + bytes(total_len - len(payload))
    buf = ctypes.create_string_buffer(payload, len(payload))
    ctypes.set_last_error(0)
    ok = hw.hid.HidD_SetOutputReport(dev.handle, buf, len(payload))
    if not ok:
        print(f"      发送失败 err={ctypes.get_last_error()}（长度 {len(payload)}）")
    return bool(ok)


def main() -> None:
    ifaces = ep.find_interfaces()
    if not ifaces:
        print("没找到接收器")
        return
    devs = []
    for it in ifaces:
        try:
            devs.append((ep._col_name(it.path), HidDevice(it.path, write=True)))
        except Exception as e:
            print(f"打开 {ep._col_name(it.path)} 失败：{e}")
    print("已打开：", [n for n, _ in devs])

    try:
        for src_name, src_dev in devs:
            for total_len in (0, 64):     # 0 = 只发实际长度（6 字节）
                for n, d in devs:
                    d.drain()
                label = f"原长6字节" if not total_len else f"补零到{total_len}字节"
                print(f"\n--- 写入 {src_name}（{label}） ---")
                if not send(src_dev, ep.QUERY_STATUS, total_len):
                    continue
                deadline = time.monotonic() + 1.5
                while time.monotonic() < deadline:
                    for n, d in devs:
                        r = d.read_input(timeout_ms=60)
                        if not r:
                            continue
                        f = ep.parse_frame(r)
                        if f:
                            print(f"    [{n}] 协议帧 kind=0x{f.kind:02X} "
                                  f"batt={f.battery} chg={f.charging} "
                                  f"| {r[:16].hex(' ')}")
                        else:
                            print(f"    [{n}] 其它 {r[:16].hex(' ')}")
    finally:
        for _, d in devs:
            d.close()


if __name__ == "__main__":
    main()
