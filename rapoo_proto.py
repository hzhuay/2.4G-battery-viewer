# -*- coding: utf-8 -*-
"""rapoo_proto.py —— 雷柏（Rapoo）2.4G 接收器电量读取（只听，不问）

协议
----
雷柏接收器在**厂商 HID 集合**上主动广播一条 19 字节状态帧：

    字节   值            含义
    0     report id(07)  固定
    1     协议(低4位)/传感器(高4位)
    2     CPI 档位
    3-4   X 轴 DPI（小端）
    5-6   Y 轴 DPI（小端）
    7     充电状态（1 = 未充电）
    8     **电量百分比 0-100**
    9-11  灯效 / 回报率 / 刷新标志
    12    配置槽
    13-14 usbPid（小端）
    15    按键 / 滚轮类型
    16    射频类型
    17    传感器模式
    18    连接标志(bit7) + 信号强度(低7位)

字段布局来自雷柏网页驱动（hub.rapoo.cn）前端 bundle 的
``VTLM20RTMouseDevice.parseUserCustomData``，并与真机交叉验证过
（官方驱动显示 21% 时该帧第 8 字节就是 0x15，DPI 也对得上）。

**只读**：一帧都不发。雷柏的电量是鼠标动一动/点一点时捎带上报的，
所以读的时候可能要等几秒；读不到就返回空，绝不显示猜的数字。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import hid_win as hw
from hid_win import HidDevice, HidError

VID = 0x24AE                 # 雷柏
USAGE_PAGE = 0xFF00          # 厂商集合
FRAME_LEN = 19

IDX_BATTERY = 8
IDX_CHARGING = 7
IDX_DPI_X = 3                # 小端 16 位
IDX_DPI_Y = 5
IDX_SLOT = 12
IDX_SIGNAL = 18

# 鼠标不动就不会有状态帧，所以把最近一次读数缓存一小段时间
CACHE_TTL = 300.0            # 秒
_last: Optional[RapooReading] = None
_last_ts = 0.0


def _remember(r: RapooReading) -> None:
    global _last, _last_ts
    r.ts = r.ts or time.time()
    _last, _last_ts = r, time.monotonic()


def _recall() -> Optional[RapooReading]:
    if _last is None or (time.monotonic() - _last_ts) > CACHE_TTL:
        return None
    return _last


@dataclass
class RapooReading:
    online: bool = False
    battery: Optional[int] = None
    charging: Optional[bool] = None
    dpi: Optional[int] = None
    signal: Optional[int] = None
    raw: bytes = b""
    detail: str = ""
    vid_pid: str = ""
    product: str = ""
    ts: float = 0.0              # 墙钟时间：这条读数是什么时候读到的


def find_interfaces() -> list[hw.HidInterface]:
    """找出雷柏接收器的厂商状态接口（0xFF00，19 字节输入）。"""
    out = []
    for d in hw.enumerate_hid():
        if d.vid == VID and d.usage_page == USAGE_PAGE and d.input_len == FRAME_LEN:
            out.append(d)
    return out


def find_interface() -> Optional[hw.HidInterface]:
    ifaces = find_interfaces()
    return ifaces[0] if ifaces else None


def parse_status(data: bytes) -> Optional[RapooReading]:
    """解析一条状态帧。字段不合理就整帧丢弃（宁可空着，也不显示猜的数字）。"""
    if len(data) < FRAME_LEN or data[0] != 0x07:
        return None

    level = data[IDX_BATTERY]
    dpi_x = data[IDX_DPI_X] | (data[IDX_DPI_X + 1] << 8)
    dpi_y = data[IDX_DPI_Y] | (data[IDX_DPI_Y + 1] << 8)
    slot = data[IDX_SLOT]

    # 强制校验：任一项不合理就整帧丢弃
    if level > 100:
        return None
    if not (100 <= dpi_x <= 32000) or not (100 <= dpi_y <= 32000):
        return None
    if slot > 15:
        return None

    r = RapooReading(online=True, battery=level, dpi=dpi_x, raw=data)
    r.charging = (data[IDX_CHARGING] != 0x01)     # 1 = 未充电
    r.signal = data[IDX_SIGNAL] & 0x7F
    return r


def read_battery(timeout: float = 6.0,
                 stop_flag=None,
                 on_raw=None) -> RapooReading:
    """读一次电量。

    雷柏是「鼠标动一动才上报」，所以可能要等几秒。
    """
    out = RapooReading()
    iface = find_interface()
    if iface is None:
        out.detail = "没找到雷柏接收器（请确认 2.4G 接收器插上、鼠标已开机）"
        return out

    out.vid_pid = iface.vid_pid
    out.product = iface.product or "Rapoo"

    try:
        dev = HidDevice(iface.path, write=False)
    except HidError as e:
        out.detail = f"无法打开设备：{e}"
        return out

    try:
        deadline = time.monotonic() + max(timeout, 0.5)
        while time.monotonic() < deadline:
            if stop_flag is not None and stop_flag():
                break
            data = dev.read_input(timeout_ms=400)
            if not data:
                continue
            if on_raw is not None:
                try:
                    on_raw(data)
                except Exception:
                    pass
            r = parse_status(data)
            if r is not None:
                r.vid_pid = out.vid_pid
                r.product = out.product
                r.detail = (f"被动状态帧 · DPI {r.dpi} · 信号 {r.signal}"
                            if r.dpi else "被动状态帧")
                _remember(r)
                return r
        out.detail = ("设备在线，但 %.0f 秒内没收到状态包"
                      "（动一下鼠标或点一下按键试试）" % timeout)
    except HidError as e:
        out.detail = f"读取出错：{e}"
    finally:
        dev.close()

    # 没等到新包：如果是最近刚读到过，就用缓存值（鼠标不动时不该显示 "--"）
    cached = _recall()
    if cached is not None:
        cached.detail = "被动状态帧（鼠标不动时用上次读数）"
        return cached
    return out


def read() -> "object":
    """给 devices.py 注册表用的入口，返回 devices.Reading。"""
    from devices import Reading

    r = Reading("雷柏 VT3S", "2.4G 接收器")
    res = read_battery(timeout=6.0)
    if res.battery is None:
        r.error = res.detail
        return r
    r.level = res.battery
    r.status = "充电中" if res.charging else "放电中"
    r.detail = "被动状态帧（0xFF00 / 19 字节）"
    bits = [f"{res.vid_pid}"]
    if res.dpi:
        bits.append(f"DPI {res.dpi}")
    if res.signal is not None:
        bits.append(f"信号 {res.signal}")
    r.extra = " · ".join(bits)
    r.ts = res.ts or None
    return r


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("查找雷柏设备…")
    it = find_interface()
    if it:
        print(f"  {it.vid_pid} usage=0x{it.usage_page:04X}:0x{it.usage:04X} "
              f"in={it.input_len} out={it.output_len} product={it.product!r}")
    else:
        print("  没找到")
    print("读取电量（最多等 8 秒，动一下鼠标）…")
    res = read_battery(timeout=8.0, on_raw=lambda d: print("  RAW", d.hex(" ")))
    if res.battery is not None:
        print(f"电量: {res.battery}%  充电={res.charging}  ({res.detail})")
    else:
        print("失败:", res.detail)
