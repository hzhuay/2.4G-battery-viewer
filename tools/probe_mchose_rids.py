# -*- coding: utf-8 -*-
"""迈从 K87S：只读枚举各集合的输入/输出报告 ID 与长度（不发一个字节）。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hid_win as hw
from hid_win import HidDevice, HidError

VID = 0x3837


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    for d in [x for x in hw.enumerate_hid() if x.vid == VID]:
        print(f"\n=== {d.vid_pid}  up=0x{d.usage_page:04X} us=0x{d.usage:04X} "
              f"in={d.input_len} out={d.output_len} reserved={d.reserved}")
        try:
            dev = HidDevice(d.path, write=False)
        except HidError as e:
            print("   打开失败:", e)
            continue
        try:
            c = dev.caps
            print(f"   caps: in={c.InputReportByteLength} out={c.OutputReportByteLength} "
                  f"feat={c.FeatureReportByteLength} "
                  f"inValCaps={c.NumberInputValueCaps} outValCaps={c.NumberOutputValueCaps} "
                  f"featValCaps={c.NumberFeatureValueCaps}")
            for label, rt in (("IN ", hw.HidP_Input), ("OUT", hw.HidP_Output),
                              ("FEAT", hw.HidP_Feature)):
                caps = dev.value_caps(rt)
                if not caps:
                    print(f"   {label}: (无)")
                    continue
                ids = {}
                for vc in caps:
                    ids.setdefault(vc.ReportID, []).append((vc.UsagePage, vc.u.Range.UsageMin))
                desc = ", ".join(f"RID=0x{k:02X}({len(v)}个值)" for k, v in sorted(ids.items()))
                print(f"   {label}: {desc}")
        except HidError as e:
            print("   读能力表失败:", e)
        finally:
            dev.close()


if __name__ == "__main__":
    main()
