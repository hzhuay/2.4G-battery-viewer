# -*- coding: utf-8 -*-
"""只读：导出各 HID 接口的报告描述符，列出每个报告 ID 的输入/输出长度。

用法：
    python tools/dump_hid_desc.py 3837
    python tools/dump_hid_desc.py 3837 --hex

不发任何数据：只用 IOCTL_HID_GET_REPORT_DESCRIPTOR 读描述符。
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hid_win as hw

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
IOCTL_HID_GET_REPORT_DESCRIPTOR = 0x000B0000


def read_descriptor(path: str) -> bytes:
    h = kernel32.CreateFileW(path, 0, 0x3, None, 3, 0, None)
    if h == ctypes.c_void_p(-1).value or not h:
        raise OSError(f"CreateFileW 失败 err={ctypes.get_last_error()}")
    try:
        buf = ctypes.create_string_buffer(4096)
        got = wintypes.DWORD(0)
        ok = kernel32.DeviceIoControl(
            h, IOCTL_HID_GET_REPORT_DESCRIPTOR, None, 0,
            buf, 4096, ctypes.byref(got), None)
        if not ok:
            raise OSError(f"DeviceIoControl 失败 err={ctypes.get_last_error()}")
        return buf.raw[: got.value]
    finally:
        kernel32.CloseHandle(h)


def parse(desc: bytes):
    """粗解析：返回 {report_id: {"in": bits, "out": bits, "feat": bits}}。"""
    out: dict[int, dict] = {}
    rid, rsize, rcount = 0, 0, 0
    i = 0
    while i < len(desc):
        b = desc[i]
        if b == 0xFE:                      # long item
            if i + 2 >= len(desc):
                break
            i += 3 + desc[i + 1]
            continue
        size = (0, 1, 2, 4)[b & 0x03]
        tag = b & 0xFC
        data = desc[i + 1: i + 1 + size]
        val = int.from_bytes(data, "little") if data else 0
        if tag == 0x84:                    # Report ID
            rid = val
        elif tag == 0x74:                  # Report Size
            rsize = val
        elif tag == 0x94:                  # Report Count
            rcount = val
        elif tag in (0x80, 0x90, 0xB0):    # Input / Output / Feature
            slot = {0x80: "in", 0x90: "out", 0xB0: "feat"}[tag]
            e = out.setdefault(rid, {"in": 0, "out": 0, "feat": 0})
            e[slot] += rsize * rcount
        i += 1 + size
    return out


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("vid", help="十六进制 VID，例如 3837")
    ap.add_argument("--hex", action="store_true", help="同时打印描述符原始字节")
    args = ap.parse_args()
    vid = int(args.vid, 16)

    for d in hw.enumerate_hid():
        if d.vid != vid:
            continue
        print(f"■ {d.vid_pid} {d.describe_usage()} "
              f"in={d.input_len} out={d.output_len} feat={d.feature_len}")
        try:
            desc = read_descriptor(d.path)
        except OSError as e:
            print(f"    描述符读取失败：{e}")
            continue
        reps = parse(desc)
        if not reps:
            print(f"    描述符 {len(desc)} 字节，没解析出报告")
        for rid in sorted(reps):
            e = reps[rid]
            print(f"    RID 0x{rid:02X}: in={e['in'] // 8}B out={e['out'] // 8}B "
                  f"feat={e['feat'] // 8}B")
        if args.hex:
            print("    desc:", desc.hex(" "))
        print()


if __name__ == "__main__":
    main()
