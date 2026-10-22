# -*- coding: utf-8 -*-
"""matrix_probe.py —— 在三个厂商集合上穷举「输出报告 ID × 数据排布」，找出能问出电量的组合

两个未知量：
  * 往哪个集合写（col02 / col03 / col04）
  * 输出报告 ID 是多少、协议帧里第一字节 0xD0 到底是 RID 还是数据

做法
----
第 1 步（探测合法 RID）：对每个集合，依次尝试一批候选 RID，
    用**全零载荷**发；Windows 只对合法 RID 放行（其它直接报错、一个字节都不下发），
    所以这一步最多只会向设备发出几个「全零帧」，风险极低。
第 2 步（试真实命令）：对每个合法 RID，试两种数据排布：
    A) [RID][D0 35 BB 01 00][补零]      —— 0xD0 当作数据
    B) [RID][35 BB 01 00][补零]         —— 0xD0 当作 RID

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

RID_CANDIDATES = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
                   0x09, 0x0A, 0x0B, 0x10, 0x11, 0x20, 0x21, 0x30, 0x40, 0x41,
                   0x50, 0x51, 0x60, 0x70, 0x80, 0x81, 0xA0, 0xC0, 0xD0, 0xD1,
                   0xE0, 0xED, 0xF0, 0xFE, 0xFF]


def send_raw(dev, payload: bytes) -> tuple[bool, int]:
    buf = ctypes.create_string_buffer(payload, len(payload))
    ctypes.set_last_error(0)
    ok = hw.hid.HidD_SetOutputReport(dev.handle, buf, len(payload))
    return bool(ok), ctypes.get_last_error()


def collect(devs, seconds: float, tag: str):
    end = time.monotonic() + seconds
    hits = []
    while time.monotonic() < end:
        for name, d in devs:
            r = d.read_input(timeout_ms=50)
            if not r:
                continue
            f = ep.parse_frame(r)
            hits.append((name, f, r))
            if f:
                print(f"      [{tag}][{name}] 协议帧 kind=0x{f.kind:02X} "
                      f"batt={f.battery} chg={f.charging} | {r[:18].hex(' ')}")
            else:
                print(f"      [{tag}][{name}] 原始 | {r[:18].hex(' ')}")
    return hits


def main() -> None:
    ifaces = ep.find_interfaces()
    if not ifaces:
        print("没找到接收器")
        return

    for it in ifaces:
        name = ep._col_name(it.path)
        print(f"\n{'='*60}\n集合 {name}")
        try:
            dev = HidDevice(it.path, write=True)
        except Exception as e:
            print(f"  打开失败：{e}")
            continue
        try:
            # ---- 第 1 步：找出合法的输出报告 ID ----
            good = []
            for rid in RID_CANDIDATES:
                ok, err = send_raw(dev, bytes([rid]) + bytes(63))
                if ok:
                    good.append(rid)
                    print(f"  RID=0x{rid:02X} 合法（全零载荷已下发）")
                elif err == 87:
                    pass                       # 不存在，未下发
                elif err == 1:
                    print(f"  RID=0x{rid:02X} 存在但不是输出报告（err=1）")
            print(f"  → 合法输出 RID: {[hex(r) for r in good]}")

            # ---- 第 2 步：试真实命令 ----
            for rid in good:
                for label, frame in (("A: D0当数据", bytes([0xD0, 0x35, 0xBB, 0x01, 0x00])),
                                     ("B: D0当RID", bytes([0x35, 0xBB, 0x01, 0x00]))):
                    payload = bytes([rid]) + frame
                    payload += bytes(64 - len(payload))
                    dev.drain()
                    ok, err = send_raw(dev, payload)
                    print(f"  → RID=0x{rid:02X} {label} 发送{'成功' if ok else '失败 err=%d' % err}")
                    if ok:
                        collect([(name, dev)], 1.5, f"0x{rid:02X}{label[0]}")
        finally:
            dev.close()


if __name__ == "__main__":
    main()
