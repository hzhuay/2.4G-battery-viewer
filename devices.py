# -*- coding: utf-8 -*-
"""devices.py —— 设备注册表（配置驱动）

原来 ``my_devices.py`` / ``tray_app.py`` 把「ATK 鼠标 + DARKRIM 耳机」写死在代码里，
这里改成一张表：加设备 = 加一条 profile，界面卡片和托盘图标都会自动跟着变。

每条 profile 描述：
    key     内部标识（托盘图标 ID、配置文件用）
    title   界面上的名字
    reader  读取函数，返回一个 Reading
    note    备注（界面上不显示，给人看）
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import edifier_proto
import hid_win as hw


# --------------------------------------------------------------------------
# 读取结果
# --------------------------------------------------------------------------
@dataclass
class Reading:
    title: str
    subtitle: str = ""
    level: Optional[int] = None          # 0-100
    status: str = ""
    detail: str = ""
    error: str = ""
    extra: str = ""

    @property
    def ok(self) -> bool:
        return self.level is not None


@dataclass
class DeviceProfile:
    key: str
    title: str
    reader: Callable[[], Reading]
    note: str = ""
    plate: bool = False        # 托盘图标是否带深色底板（耳机用）


# --------------------------------------------------------------------------
# 各设备的读取函数
# --------------------------------------------------------------------------
def read_edifier() -> Reading:
    """漫步者 HECATE G3 Max（杰理方案 2.4G 接收器）。"""
    r = Reading("漫步者 G3 Max", "2.4G 接收器")
    level, charging, detail = edifier_proto.read_battery()
    if level is None:
        r.error = detail
        return r
    if level == 0:
        # 电量 0 = 耳机没开机或没连上 dongle（官方软件这时也是显示 0）
        r.error = "耳机没开机或没连上接收器"
        return r
    r.level = level
    r.status = "充电中" if charging else "放电中"
    r.detail = "杰理私有协议 · RID 0xD0 · TLV 0x0A"
    r.extra = detail
    return r


def read_rapoo() -> Reading:
    """雷柏 VT3S（2.4G 接收器）。"""
    r = Reading("雷柏 VT3S", "2.4G 接收器")
    try:
        import rapoo_proto
        return rapoo_proto.read()
    except ImportError:
        r.error = "协议还没摸清（rapoo_proto.py 未实现）"
        return r
    except Exception as e:
        r.error = f"读取出错：{e}"
        return r


def read_mchose() -> Reading:
    """迈从 K87S（2.4G 接收器）。"""
    r = Reading("迈从 K87S", "2.4G 接收器")
    try:
        import mchose_proto
        return mchose_proto.read()
    except ImportError:
        r.error = "协议还没摸清（mchose_proto.py 未实现）"
        return r
    except Exception as e:
        r.error = f"读取出错：{e}"
        return r


# --------------------------------------------------------------------------
# 设备表
# --------------------------------------------------------------------------
PROFILES: list[DeviceProfile] = [
    DeviceProfile("edifier", "漫步者 G3 Max", read_edifier,
                  note="杰理方案；协议来自 HECATE 官方软件日志", plate=True),
    DeviceProfile("rapoo", "雷柏 VT3S", read_rapoo,
                  note="VID 24AE；被动状态帧"),
    DeviceProfile("mchose", "迈从 K87S", read_mchose,
                  note="VID 3837；固件推送式"),
]


def read_all() -> list[Reading]:
    """按注册表顺序读一遍所有设备。

    各个设备的读取互不依赖（而且有的要等好几秒），所以并行跑，
    总耗时 = 最慢的那个，而不是加起来。
    """
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=max(1, len(PROFILES))) as pool:
        futures = [pool.submit(p.reader) for p in PROFILES]
        out = []
        for p, fut in zip(PROFILES, futures):
            try:
                out.append(fut.result())
            except Exception as e:
                out.append(Reading(p.title, error=f"读取异常：{e}"))
    return out
