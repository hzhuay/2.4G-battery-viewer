# -*- coding: utf-8 -*-
"""edifier_proto.py —— 漫步者 HECATE G3 Max（杰理方案 2.4G 接收器）电量读取

协议**不是猜的**，是直接从 HECATE 官方软件自己的日志里抄出来的
（``%APPDATA%\\HECATE\\log\\*.log``，官方把每次 HID 收发都打成十六进制）：

    [DeviceConnecter.cpp 59] HID write[05]: D0 35 BB 01 00
    [DeviceConnecter.cpp 82] HID read[64]: D0 35 BB 0A 00 01 64 00 01 02 01 01 01 07 00…00 06

传输层
------
HID 厂商接口：VID ``0x35BB`` PID ``0xA226``（G3 Max 无线版），
UsagePage ``0xFF02`` Usage ``0x0002``，输出/输入各 64 字节。
这个 dongle 上有 **3 个完全一样的厂商集合**（Col02 / Col03 / Col04），
官方软件往其中之一发命令，收到回复的也是它。

报文
----
    写（查询状态）:  D0 35 BB 01 00
    读（电量回复）:  D0 35 BB 0A 00 01 <battery%> <charging> 01 02 01 01 01 07 00…00
                        ↑ 第6字节=电量百分比   ↑ 第7字节=充电标志(0/1)

写入格式（Windows HID 的两个坑）
--------------------------------
1. **输出报告 ID = 0x02**。hidapi 发送时会把报告 ID 放在缓冲区第 0 字节，
   官方日志只打了协议帧、没打这个 ID，是靠「错误码探针」试出来的：
   RID 0x02 → 发送成功；RID 0x01 → err=1（是别的类型的报告）；
   其余 RID → err=87（不存在，**一个字节都不会下发到设备**）。
2. **长度必须写满 64 字节**。写 6 字节 → err=87（被 Windows 拒掉），
   所以要把协议帧后面补零到 OutputReportByteLength。

另外注意：dongle 同一时刻只服务一个客户端。官方 HECATE 软件开着的时候，
我们发出去的查询**收不到回复**（固件把命令给了官方软件那个会话）。
要读电量得先关掉官方软件。

其它官方命令（暂未用到，留档）::

    ED 01                  -> ED 35 BB 09 00 01 02 05 04 00 FF FF FF …   （设备信息）
    ED 35 BB 01 00         -> ED 35 BB 09 00 01 02 05 05 00 00 99 …
    D0 35 BB 01 02         -> D0 35 BB 07 02 6C 16 29 4E 80 C2 …          （空间音效参数）
    D0 35 BB 02 06 <ch>    -> D0 35 BB 02 06 00 00 …                        （EQ 通道）

关于末字节
----------
回复最后一字节大多数是 ``0x06``，但既不是累加和也不是异或（电量在变、它不变），
个别帧是 ``0x00 / 0x41 / 0x99``。实测**不依赖它**：靠魔数 ``35 BB`` + 命令字识别即可，
所以本实现不校验末字节。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import hid_win as hw
from hid_win import HidDevice, HidError, HidInterface

VID = 0x35BB
PID = 0xA226

USAGE_PAGE = 0xFF02
USAGE = 0x0002
REPORT_LEN = 64

# 官方软件发的查询命令。**注意**：官方日志里的 "D0 35 BB 01 00" 这 5 字节里，
# 第 1 个字节 0xD0 是 HID 的**输出报告 ID**，真正的协议数据是后面的 "35 BB 01 00"。
QUERY_FRAME = bytes([0x35, 0xBB, 0x01, 0x00])

# 输出报告 ID（三个集合各不相同，靠错误码探针试出来的）：
#   col02 = 0x02（第三条通道）、col03 = 0xD0（耳机侧，电量在这里）、col04 = 0xED（设备信息）
REPORT_ID_BATTERY = 0xD0

MAGIC = (0x35, 0xBB)

CMD_STATUS = 0x0A        # 电量/状态回复
CMD_INFO = 0x09          # 设备信息回复
CMD_SPATIAL = 0x07       # 空间音效参数回复
CMD_EQ = 0x02            # EQ 回复


@dataclass
class Frame:
    raw: bytes
    kind: int = 0         # 第 3 字节：命令字
    channel: int = 0      # 第 0 字节：0xD0 / 0xED
    battery: Optional[int] = None      # 电量百分比
    charging: Optional[bool] = None    # 充电标志

    @property
    def is_status(self) -> bool:
        return self.kind == CMD_STATUS


def parse_frame(report: bytes) -> Optional[Frame]:
    """把一帧原始报文解析成 Frame；不是本协议返回 None。"""
    if not report or len(report) < 6:
        return None
    if (report[1], report[2]) != MAGIC:
        return None
    f = Frame(raw=report, kind=report[3], channel=report[0])
    if report[3] == CMD_STATUS and len(report) >= 8:
        level = report[6]
        f.battery = level if level <= 100 else None
        f.charging = bool(report[7])
    return f


def find_interfaces() -> list[HidInterface]:
    """列出 G3 Max dongle 的所有厂商集合（Col02/Col03/Col04）。"""
    out = []
    for d in hw.enumerate_hid():
        if d.vid == VID and d.usage_page == USAGE_PAGE and d.usage == USAGE:
            out.append(d)
    return out


def _col_name(path: str) -> str:
    """从设备路径里取出 ColXX，方便区分三个厂商集合。"""
    low = path.lower()
    i = low.find("&col")
    if i < 0:
        return "?"
    j = low.find("#", i)
    return path[i + 1:j] if j > 0 else path[i + 1:]


def build_output(frame: bytes, report_id: int = REPORT_ID_BATTERY) -> bytes:
    """拼成 Windows HID 要的输出报文：[报告ID][协议帧][补零到64字节]。

    长度必须正好等于 OutputReportByteLength（64），写短了 Windows 会拒收（err=87）。
    """
    payload = bytes([report_id]) + frame
    if len(payload) < REPORT_LEN:
        payload += bytes(REPORT_LEN - len(payload))
    return payload


def query_status(dev: HidDevice, timeout: float = 1.5,
                 report_id: int = REPORT_ID_BATTERY) -> list[Frame]:
    """发一次官方查询命令，把这一轮收到的所有帧收回来。"""
    frames: list[Frame] = []
    dev.drain()
    dev.write_output(build_output(QUERY_FRAME, report_id))
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        r = dev.read_input(timeout_ms=150)
        if not r:
            continue
        f = parse_frame(r)
        if f:
            frames.append(f)
    return frames


def find_battery_interface() -> Optional[HidInterface]:
    """找出电池所在的厂商集合。

    dongle 上三个厂商集合各自有自己的输出报告 ID（0x02 / 0xD0 / 0xED），
    电量在 **0xD0** 那条通道上。Windows 只接受该集合真正声明的 RID，
    所以「用 RID 0xD0 写一次，看会不会被拒」就能把它认出来 ——
    被拒的集合一个字节都不会下发到设备。
    """
    for d in find_interfaces():
        try:
            with HidDevice(d.path, write=True) as dev:
                dev.write_output(build_output(QUERY_FRAME, REPORT_ID_BATTERY))
                return d
        except HidError:
            continue
    return None


def read_battery(iface: Optional[HidInterface] = None,
                 timeout: float = 1.5) -> tuple[Optional[int], Optional[bool], str]:
    """读取电量。

    返回 (电量百分比, 是否充电, 说明)。
    iface 为 None 时自动找电池所在的那个集合。
    """
    if iface is None:
        iface = find_battery_interface()
        if iface is None:
            return None, None, "没找到 G3 Max 接收器（VID 35BB / UsagePage FF02）"
    try:
        with HidDevice(iface.path, write=True) as dev:
            frames = query_status(dev, timeout=timeout)
    except HidError as e:
        return None, None, f"收发失败：{e}"

    for f in frames:
        if f.is_status and f.battery is not None:
            if f.battery == 0:
                # 官方日志里耳机没开机/没连上时就是 0A 00 00 00 00（电量为 0）
                return 0, False, f"{_col_name(iface.path)} 电量=0（耳机没开机或没连上）"
            state = "充电中" if f.charging else "放电中"
            return f.battery, f.charging, f"{_col_name(iface.path)} 电量={f.battery}% {state}"
    if frames:
        kinds = ", ".join(f"0x{f.kind:02X}" for f in frames)
        return None, None, f"收到 {len(frames)} 帧但没有电量帧（命令字：{kinds}）"
    return None, None, (f"{_col_name(iface.path)} 没有回复"
                        "（耳机可能没开机/没连上，或 HECATE 官方软件正占着 dongle）")


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ifaces = find_interfaces()
    print(f"找到 {len(ifaces)} 个厂商集合：")
    for i, it in enumerate(ifaces):
        print(f"  [{i}] {_col_name(it.path)}  {it.path}")
    if not ifaces:
        raise SystemExit(0)
    print()
    lvl, chg, detail = read_battery()
    print(f"电量={lvl}%  充电={chg}  {detail}")
