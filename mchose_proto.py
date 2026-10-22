# -*- coding: utf-8 -*-
"""mchose_proto.py —— 迈从（MCHOSE）K87S 2.4G 接收器电量

协议来源
--------
官方网页驱动 https://www.mchose.com.cn/cizhou/ 的 JS bundle（反混淆后读出来的）：

1) **Qhw 通道**（class J，K87S 走的就是这套）
   线上字节 = ``[报告ID][version=1][flags=3][length][cmdLo][cmdHi][biz=0][seq][payload…][cs]``
   ``cs`` = 帧里从 version 开始的**异或**（不含报告 ID）。
   命令号（官方 Channel:QhwKeyboard）：

       2304 getBaseInfo      2305 getFwVersion    2308 getBattery
       517  getProfileConfig 2310  switchProfile  2324  heartbeat
       34   broadcastEvent

   ``getBattery()`` 的回包数据 = ``[充电状态, 电量%]``。

2) **AT 通道**（老款键盘的 class P，帧头 0x55/0xAA）
   ``[55][cmd][00][cs][size][offLo][offHi][00][payload…]``，cs = XOR(size, offLo, offHi, 0, payload)
   —— 社区项目对 K99 V3 用的就是这套，这台 K87S 不回。

实测行为（K87S / VID 3837 PID 3033）
------------------------------------
* 命令通道：usage page ``0x0001`` / usage ``0x0000``，输入输出都是 65 字节，报告 ID 只有 ``0x00``。
* 键盘会**主动广播** AT 帧（在这条通道上，同一帧也会镜像到 0xFF31:0x0074）：

      ``FA FB 07 <电量%> <充电标志>``   —— 电量（只在充/断电切换时广播）
      ``FA FB 06 01``                   —— 键盘已连上接收器
      ``FA FB 06 00``                   —— 键盘断开

  官方 JS 的分发器就是这么写的：
  ``FA FB 07`` 且 t[4]==0 → "stopCharging" + updateBattery{battery: t[3]}``。
* **回复是异步的**：查询包发出去后，设备过一会儿才用 AT 帧推回来，不是一问一答。

所以读取方式是：常驻监听 + 缓存；读的时候再补发一次 getBattery 查询刺激设备推一次。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

import hid_win as hw
from hid_win import HidDevice, HidError

VID = 0x3837                 # 迈从 MCHOSE
CHANNEL = (0x0001, 0x0000)   # usage page / usage —— Qhw 命令通道
REPORT_LEN = 65             # 这台接收器的输出报告长度

# ---- 官方 Qhw 协议参数（class J）----
QHW_REPORT_ID = 0x00         # Windows 侧这个集合只有 RID 0x00
QHW_VERSION = 1
QHW_FLAGS = 3
QHW_BIZ = 0

CMD_GET_BASE_INFO = 2304
CMD_GET_FW_VERSION = 2305
CMD_GET_BATTERY = 2308

# AT 帧（设备 → 主机）
AT_BATTERY_CMD = 0x07        # FA FB 07 <电量%> <充电>
AT_COMMS_CMD = 0x06         # FA FB 06 <0=断开 1=连上>

CACHE_TTL = 3600.0
QUERY_INTERVAL = 30.0       # 常驻线程每隔多久补发一次查询


@dataclass
class MchoseReading:
    online: bool = False
    battery: Optional[int] = None
    charging: Optional[bool] = None
    wired: Optional[bool] = None
    raw: bytes = b""
    detail: str = ""
    vid_pid: str = ""
    ts: float = 0.0


_last: Optional[MchoseReading] = None
_lock = threading.Lock()


def _remember(r: MchoseReading) -> None:
    global _last
    with _lock:
        _last = r


def _recall(max_age: float = CACHE_TTL) -> Optional[MchoseReading]:
    with _lock:
        r = _last
    if r is None or (time.monotonic() - r.ts) > max_age:
        return None
    return r


# --------------------------------------------------------------------------
# 组帧 / 解析
# --------------------------------------------------------------------------
def build_qhw(command: int, payload: bytes = b"", seq: int = 0) -> bytes:
    """官方 class J 的协议帧（**不含**报告 ID）。

    线上 = [RID] + version, flags, length, cmdLo, cmdHi, biz, seq, payload…, cs
    """
    header = [QHW_VERSION, QHW_FLAGS, len(payload),
              command & 0xFF, (command >> 8) & 0xFF, QHW_BIZ, seq & 0xFF]
    body = header + list(payload)
    cs = 0
    for b in body[1:]:
        cs ^= b
    return bytes(body + [cs])


def build_output(frame: bytes, report_id: int = QHW_REPORT_ID,
                 length: int = REPORT_LEN) -> bytes:
    """拼 Windows 的输出报告缓冲：第 0 字节是报告 ID，后面补零到报告长度。"""
    payload = bytes([report_id]) + frame
    if len(payload) < length:
        payload += bytes(length - len(payload))
    return payload


def find_interface() -> Optional[hw.HidInterface]:
    """Qhw 命令通道：usage page 0x0001 / usage 0x0000。"""
    for d in hw.enumerate_hid():
        if (d.vid == VID and d.usage_page == CHANNEL[0] and d.usage == CHANNEL[1]
                and d.output_len and not d.reserved):
            return d
    return None


def parse_at(raw: bytes) -> Optional[MchoseReading]:
    """解析设备推过来的 AT 帧（FA FB …）。返回 None 表示不是电量帧。"""
    # raw[0] 是报告 ID（0x00），真正的 AT 帧从 raw[1] 开始
    for off in (1, 0):
        b = raw[off:]
        if len(b) >= 5 and b[0] == 0xFA and b[1] == 0xFB:
            if b[2] == AT_BATTERY_CMD:
                pct = b[3]
                if 0 <= pct <= 100:
                    return MchoseReading(online=True, battery=pct,
                                         charging=bool(b[4]), raw=raw,
                                         detail="设备推送 FA FB 07")
            elif b[2] == AT_COMMS_CMD:
                r = MchoseReading(online=(b[3] == 1), raw=raw,
                                  detail="键盘已连上接收器" if b[3] == 1
                                  else "键盘已断开")
                return r
    return None


# --------------------------------------------------------------------------
# 常驻监听线程
# --------------------------------------------------------------------------
_listener_thread: Optional[threading.Thread] = None
_listener_lock = threading.Lock()
_seq = [0]


def _next_seq() -> int:
    _seq[0] = (_seq[0] + 1) & 0xFF
    return _seq[0]


def _send_query(dev: HidDevice, command: int = CMD_GET_BATTERY,
                payload: bytes = b"") -> bool:
    frame = build_qhw(command, payload, seq=_next_seq())
    buf = build_output(frame, length=dev.caps.OutputReportByteLength or REPORT_LEN)
    try:
        dev.write_output(buf)
        return True
    except HidError:
        return False


def _listener_loop(iface: hw.HidInterface) -> None:
    """常驻：收 AT 帧 + 定时补发查询。"""
    try:
        dev = HidDevice(iface.path, write=True)
    except HidError:
        return
    last_query = 0.0
    try:
        while True:
            now = time.monotonic()
            if now - last_query > QUERY_INTERVAL:
                last_query = now
                _send_query(dev)
            data = dev.read_input(timeout_ms=250)
            if not data:
                continue
            r = parse_at(data)
            if r is not None and r.battery is not None:
                r.ts = time.monotonic()
                r.vid_pid = iface.vid_pid
                _remember(r)
            elif r is not None and r.online:
                with _lock:
                    if _last is not None:
                        _last.online = True
    except HidError:
        pass
    except Exception:
        pass
    finally:
        dev.close()


def start_listener() -> bool:
    """启动常驻监听线程（幂等）。返回是否成功启动。"""
    global _listener_thread
    with _listener_lock:
        if _listener_thread and _listener_thread.is_alive():
            return True
        iface = find_interface()
        if iface is None:
            return False
        t = threading.Thread(target=_listener_loop, args=(iface,), daemon=True)
        t.start()
        _listener_thread = t
        return True


# --------------------------------------------------------------------------
# 对外接口（devices.py 注册表用）
# --------------------------------------------------------------------------
def read(wait: float = 4.0) -> "object":
    """给 devices.py 注册表用的入口。

    常驻线程负责收；这里补发一次 getBattery 查询，催设备推一次。
    """
    from devices import Reading

    r = Reading("迈从 K87S", "2.4G 接收器")
    if not start_listener():
        r.error = "没找到迈从接收器命令通道（VID 3837 / usage 0x0001:0x0000）"
        return r

    deadline = time.monotonic() + max(wait, 0.5)
    # 先等缓存里有没有（上次推过的值）
    cached = _recall()
    if cached is not None and cached.battery is not None:
        # 再补发一次查询，等更新的值
        iface = find_interface()
        if iface is not None:
            try:
                with HidDevice(iface.path, write=True) as wdev:
                    _send_query(wdev)
            except HidError:
                pass

    while time.monotonic() < deadline:
        cur = _recall()
        if cur is not None and cur.battery is not None:
            r.level = cur.battery
            r.status = "充电中" if cur.charging else "放电中"
            r.detail = cur.detail
            r.extra = cur.vid_pid
            return r
        time.sleep(0.2)

    if cached is not None and cached.battery is not None:
        r.level = cached.battery
        r.status = "充电中" if cached.charging else "放电中"
        r.detail = f"{cached.detail}（{int((time.monotonic() - cached.ts) / 60)} 分钟前的读数）"
        r.extra = cached.vid_pid
        return r

    r.error = ("设备在线，但没收到电量推送"
               "（迈从键盘只在充电/断电时广播 FA FB 07，"
               "插拔一下充电线即可触发）")
    return r


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    it = find_interface()
    print("命令通道：", f"{it.vid_pid} 0x{it.usage_page:04X}:0x{it.usage:04X} "
                        f"in={it.input_len} out={it.output_len}" if it else "没找到")
    print("getBattery 查询包:", build_output(build_qhw(CMD_GET_BATTERY, seq=1)).hex(" "))
    start_listener()
    t0 = time.monotonic()
    while time.monotonic() - t0 < 30:
        time.sleep(0.5)
        c = _recall()
        if c and c.battery is not None:
            print(f"电量: {c.battery}%  充电={c.charging}  ({c.detail})")
