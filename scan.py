# -*- coding: utf-8 -*-
"""scan.py —— 只读盘点本机所有 HID 接口

**本脚本只读、绝不发送任何数据**：
enumerate_hid() 内部用 CreateFileW(dwDesiredAccess=0) 打开每个接口，
只读取产品名/能力表，不抢占系统对键鼠的控制权，也不写任何 Output/Feature Report。

用法：
    python scan.py           # 打印人类可读的清单
    python scan.py --json    # 输出 JSON（给后续自动化用）
"""

from __future__ import annotations

import argparse
import json
import sys

# Windows 控制台默认 GBK，中文输出会乱码；统一按 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import hid_win as hw
from hid_win import HidInterface


def flags(it: HidInterface) -> str:
    f = []
    if it.reserved:
        f.append("系统独占(不可写)")
    if it.is_vendor_page:
        f.append("厂商接口")
    if it.feature_len:
        f.append(f"Feature×{it.feature_len}")
    if it.output_len:
        f.append(f"Output×{it.output_len}")
    if it.input_len:
        f.append(f"Input×{it.input_len}")
    if not f:
        f.append("无报告")
    if it.error:
        f.append(f"错误:{it.error}")
    return " ".join(f)


def main() -> None:
    ap = argparse.ArgumentParser(description="只读列出所有 HID 接口")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    items = hw.enumerate_hid()

    if args.json:
        out = [
            {
                "vid": it.vid, "pid": it.pid,
                "vid_pid": it.vid_pid,
                "usage_page": it.usage_page, "usage": it.usage,
                "product": it.product, "manufacturer": it.manufacturer,
                "serial": it.serial,
                "input_len": it.input_len, "output_len": it.output_len,
                "feature_len": it.feature_len,
                "reserved": it.reserved, "vendor": it.is_vendor_page,
                "group": it.group, "path": it.path,
                "error": it.error,
            }
            for it in items
        ]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    # 按物理设备分组
    groups: dict[str, list[HidInterface]] = {}
    for it in items:
        groups.setdefault(it.group, []).append(it)

    print(f"共 {len(items)} 个 HID 接口，{len(groups)} 个物理设备\n")
    for group, lst in groups.items():
        name = hw.pick_device_name(lst)
        vid_pid = f"{lst[0].vid:04X}:{lst[0].pid:04X}"
        mfr = next((x.manufacturer for x in lst if x.manufacturer), "")
        print(f"■ {name}")
        print(f"    VID:PID={vid_pid}" + (f"  厂商={mfr}" if mfr else ""))
        for it in lst:
            print(f"    - UP=0x{it.usage_page:04X} USAGE=0x{it.usage:04X}  {flags(it)}")
        print()


if __name__ == "__main__":
    main()
