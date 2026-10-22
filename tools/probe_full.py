# -*- coding: utf-8 -*-
"""probe_full.py —— G3 Max 完整写入探测（原始 hex 输出）

顺序：
  1. 被动听 3 秒（看 dongle 是否主动上报，顺便验证读通道正常）
  2. 发握手 ED 01，听 2 秒
  3. 发查询 D0 35 BB 01 00，听 3 秒

载荷全部取自官方软件日志；输出报告 ID = 0x02，长度必须写满 64 字节
（Windows 校验：RID=0x02 + 长度必须等于 OutputReportByteLength，否则拒绝下发）。
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
TOTAL = 64


def send(dev, frame: bytes) -> bool:
    payload = bytes([RID]) + frame
    payload = payload + bytes(TOTAL - len(payload))
    buf = ctypes.create_string_buffer(payload, len(payload))
    ctypes.set_last_error(0)
    ok = hw.hid.HidD_SetOutputReport(dev.handle, buf, len(payload))
    print(f"  发送 {payload[:8].hex(' ')} … "
          f"-> {'成功' if ok else '失败 err=' + str(ctypes.get_last_error())}")
    return bool(ok)


def listen(devs, seconds: float, tag: str) -> int:
    end = time.monotonic() + seconds
    n = 0
    while time.monotonic() < end:
        for name, d in devs:
            r = d.read_input(timeout_ms=50)
            if not r:
                continue
            n += 1
            f = ep.parse_frame(r)
            if f:
                print(f"  [{tag}][{name}] 协议帧 kind=0x{f.kind:02X} "
                      f"batt={f.battery} chg={f.charging} | {r[:20].hex(' ')}")
            else:
                print(f"  [{tag}][{name}] 原始 | {r[:20].hex(' ')}")
    if n == 0:
        print(f"  [{tag}] 什么都没收到")
    return n


def main() -> None:
    ifaces = ep.find_interfaces()
    if not ifaces:
        print("没找到接收器")
        return
    devs = []
    for it in ifaces:
        devs.append((ep._col_name(it.path), HidDevice(it.path, write=True)))
    try:
        print("【1】被动监听 3 秒")
        listen(devs, 3.0, "被动")

        print("\n【2】握手 ED 01")
        send(devs[0][1], bytes([0xED, 0x01]))
        listen(devs, 2.0, "握手")

        print("\n【3】查询 D0 35 BB 01 00")
        send(devs[0][1], ep.QUERY_STATUS)
        listen(devs, 3.0, "查询")
    finally:
        for _, d in devs:
            d.close()


if __name__ == "__main__":
    main()
