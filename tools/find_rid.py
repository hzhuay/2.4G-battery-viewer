# -*- coding: utf-8 -*-
"""find_rid.py —— 找出 G3 Max 接收器厂商集合的 **输出报告 ID**

背景：官方软件用 hidapi 写 HID，hidapi 会把报告 ID 放在缓冲区第 0 字节，
官方日志只打了协议帧本身（``D0 35 BB 01 00``），没打这个 ID。

安全说明
--------
Windows 的 HidD_SetOutputReport 会**先校验报告 ID**：
ID 不存在 → 直接失败，**一个字节都不会下发到设备**。
所以这里拿错误码当探针是安全的：只有合法的输出报告 ID 才可能真的发出去，
而我们下发的载荷始终是官方自己那条只读查询命令。

用法：
    python find_rid.py            # 依次试候选 ID
    python find_rid.py 0x00 0x01  # 只试指定的
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

# 常见报告 ID 优先：0（无编号报告时 Windows 期望 0）→ 1..8 → 其它
DEFAULT_CANDIDATES = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
                      0x09, 0x0A, 0x10, 0x11, 0x20, 0x21, 0x40, 0x41, 0x50,
                      0x51, 0x80, 0x81, 0xF0, 0xFE, 0xFF]


def try_rid(dev, rid: int, frame: bytes, wait: float = 1.0):
    """按 [RID][协议帧] 拼一包发出去，返回 (是否发送成功, 收到的帧列表, 错误码)。"""
    payload = bytes([rid]) + frame
    payload = payload + bytes(max(0, 64 - len(payload)))
    buf = ctypes.create_string_buffer(payload, len(payload))
    ctypes.set_last_error(0)
    ok = hw.hid.HidD_SetOutputReport(dev.handle, buf, len(payload))
    err = ctypes.get_last_error()
    if not ok:
        return False, [], err

    frames = []
    end = time.monotonic() + wait
    while time.monotonic() < end:
        r = dev.read_input(timeout_ms=120)
        if r:
            f = ep.parse_frame(r)
            frames.append(f if f else r)
    return True, frames, 0


def main() -> None:
    args = sys.argv[1:]
    candidates = ([int(a, 0) for a in args] if args else DEFAULT_CANDIDATES)
    ifaces = ep.find_interfaces()
    if not ifaces:
        print("没找到接收器")
        return
    iface = ifaces[0]
    print(f"接口：{ep._col_name(iface.path)}")
    print(f"协议帧：{ep.QUERY_STATUS.hex(' ')}")

    with HidDevice(iface.path, write=True) as dev:
        for rid in candidates:
            dev.drain()
            ok, frames, err = try_rid(dev, rid, ep.QUERY_STATUS)
            if not ok:
                print(f"  RID=0x{rid:02X} -> 失败 err={err}（未下发）")
                continue
            desc = ", ".join(
                (f"kind=0x{f.kind:02X} batt={f.battery} chg={f.charging}"
                 if isinstance(f, ep.Frame) else f"RAW {f[:8].hex(' ')}")
                for f in frames) or "无回复"
            print(f"  RID=0x{rid:02X} -> 发送成功，收到：{desc}")
            for f in frames:
                if isinstance(f, ep.Frame) and f.is_status and f.battery is not None:
                    print(f"  ★ 命中：RID=0x{rid:02X}，电量={f.battery}%，"
                          f"充电={f.charging}")
                    return


if __name__ == "__main__":
    main()
