# -*- coding: utf-8 -*-
"""probe_edifier.py —— 漫步者 G3 Max 接收器写入诊断（逐条发，逐条报告）

只发官方软件自己那条查询命令 ``D0 35 BB 01 00``，只是把**长度/补零方式**试几种，
用来搞清楚驱动到底要什么格式的写。每一种尝试都会打印 Windows 的真实错误码。

用法：
    python probe_edifier.py             # 依次试三个厂商集合
    python probe_edifier.py 0           # 只试第 0 个集合
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


def try_write(dev, payload: bytes, label: str) -> bool:
    """用 HidD_SetOutputReport 发一包，返回是否成功；失败时打印错误码。"""
    buf = ctypes.create_string_buffer(bytes(payload), len(payload))
    ctypes.set_last_error(0)
    ok = hw.hid.HidD_SetOutputReport(dev.handle, buf, len(payload))
    err = ctypes.get_last_error()
    print(f"    [{label}] 长度={len(payload)} 首字节=0x{payload[0]:02X} "
          f"-> {'成功' if ok else '失败 err=' + str(err)}")
    return bool(ok)


def probe(iface) -> None:
    name = ep._col_name(iface.path)
    print(f"\n=== {name}  {iface.path}")
    print(f"    OutputReportByteLength={iface.output_len} "
          f"InputReportByteLength={iface.input_len}")

    cmd = ep.QUERY_STATUS
    # 各种补零长度，从官方原始的 5 字节一直到整个报告长度
    variants = [
        ("原样5字节", cmd),
        ("补零到64", cmd + bytes(64 - len(cmd))),
        ("补零到63", cmd + bytes(63 - len(cmd))),
        ("补零到32", cmd + bytes(32 - len(cmd))),
        ("去掉首字节4字节", cmd[1:]),
        ("4字节+补零到64", cmd[1:] + bytes(60)),
    ]

    with HidDevice(iface.path, write=True) as dev:
        for label, payload in variants:
            dev.drain()
            if not try_write(dev, payload, label):
                continue
            end = time.monotonic() + 1.2
            got = []
            while time.monotonic() < end:
                r = dev.read_input(timeout_ms=150)
                if r:
                    got.append(r)
            print(f"      收到 {len(got)} 帧")
            for r in got:
                f = ep.parse_frame(r)
                if f:
                    print(f"        协议帧 kind=0x{f.kind:02X} "
                          f"battery={f.battery} charging={f.charging} "
                          f"| {r[:20].hex(' ')} …")
                else:
                    print(f"        非协议帧 | {r[:20].hex(' ')} …")
            if got:
                print("      → 有回复，停止本集合的尝试")
                return


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    ifaces = ep.find_interfaces()
    if not ifaces:
        print("没找到 G3 Max 接收器")
        return
    if args:
        probe(ifaces[int(args[0])])
    else:
        for it in ifaces:
            probe(it)


if __name__ == "__main__":
    main()
