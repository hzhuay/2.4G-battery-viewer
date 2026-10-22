# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## 项目性质

Windows 10/11 上读取 2.4G 无线外设（漫步者 G3 Max / 雷柏 VT3S / 迈从 K87S）电量的桌面小工具。
**纯标准库 + ctypes（GUI 用 tkinter），零第三方依赖**：不要引入 hidapi / pywin32 / pystray / Pillow。
`hid_win.py` 在非 win32 平台会直接 `raise RuntimeError`，所有功能都只能在 Windows 上跑。

无构建、无 lint、无测试框架、无 requirements.txt——改完直接跑脚本验证。

## 常用命令

```bash
python my_devices.py                 # 简洁面板（默认自动刷新）
python my_devices.py --once          # 命令行读一次，最快的冒烟测试
python my_devices.py --autostart status      # 开机自启状态（on / off / status）
python my_devices.py --install-links         # 重建桌面链接

python tray_app.py                   # 托盘常驻（pythonw 启动，无控制台）
python tray_app.py --debug           # 前台运行并打印日志（唯一会输出日志的方式）
python tray_app.py --status          # 打印配置 / 自启 / 单实例状态
python tray_app.py --quit            # 通知正在运行的托盘退出

python scan.py                       # 只读盘点本机所有 HID 接口（不发一个字节）
python scan.py --json
python watch.py 24AE 3837 --seconds 90       # 并行监听指定 VID 的输入报告

python edifier_proto.py              # 各协议模块可单独运行自测
python rapoo_proto.py
python mchose_proto.py
```

控制台默认 GBK，脚本统一 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`，新脚本沿用这个做法。

## 架构

分层单向依赖：传输层 → 设备协议 → 注册表 → 界面/托盘。

```
hid_win.py          ctypes 封装 setupapi/hid/kernel32：枚举接口、Feature Report、
                    异步 Input Report（独立 overlapped 读句柄 + 事件超时 + CancelIoEx）、HidP 能力表
   ↑
edifier_proto.py    漫步者（杰理私有协议，RID 0xD0，一问一答）
rapoo_proto.py      雷柏（厂商 0xFF00 被动 19 字节状态帧 + 300s 缓存）
mchose_proto.py     迈从（常驻监听线程 + 被动 FA FB 07 推送 + 3600s 缓存）
   ↑
devices.py          ★ 设备注册表：Reading / DeviceProfile / PROFILES / read_all()
   ↑                     read_all() 用 ThreadPoolExecutor 并行读三个设备
my_devices.py       简洁面板（tkinter，queue + after() 从后台线程回传结果）
tray_app.py         托盘常驻（纯 Win32 SetTimer + NOTIFYICONDATAW，图标数量由 PROFILES 决定）
```

- **加/换设备只改 `devices.py`**：加一条 `DeviceProfile(key, title, reader, note, plate)`，
  reader 返回 `Reading`（`level=None` 表示读不到，`error` 写原因）。托盘图标 `TRAY_ICONS`
  和面板卡片都由 `PROFILES` 生成，不需要动 UI 代码。
- **读不到电量返回 `None` 并缓存上一次的值，绝不填充猜测的数字**；缓存过期就如实报错。
- 支撑模块：`tray_common.py`（配置 / 单实例 PID / 自启 .lnk / 桌面链接 / 僵尸进程清理）、
  `win_icon.py`（运行时用 GDI 画数字图标）、`win_link.py`（符号链接/junction/硬链接）、
  `win_shell.py`（纯 ctypes 创建 .lnk）。
- **上游 fork 遗留、不在当前读取链路里**：`app.py`（完整调试 GUI）、`battery.py`（通用多策略框架）、
  `darkrim_proto.py`、`bt_battery.py`。`tray_app.py` 仍 import 了 `battery`/`darkrim_proto` 但未使用。
  新设备不要接到 `battery.py` 的策略链上，走 `devices.py` 注册表。
- `tools/` 是一次性逆向探测脚本，只读为主，结论见 `HANDOVER.md` §6，不要把它们当生产代码改。

## Windows HID 硬约束（违反就会静默失败或杀掉进程）

1. `HidD_SetOutputReport` 把缓冲区第 0 字节当**报告 ID 剥掉**（Linux hidraw 不会）。
   照抄 Linux 抓包要补一个占位字节。
2. 写入长度必须**正好等于该报告 ID 的 `OutputReportByteLength`**，短一个字节就 err=87，一个字节都不下发。
3. 错误码即探针：err=87 = RID 不存在 / 长度不对；err=1 = RID 存在但不是输出报告。
4. **绝不在同一句柄上并发"阻塞读 + 写"**——实测直接杀掉进程。用 `HidDevice` 的内部 overlapped 读句柄。
5. 系统独占集合（鼠标 `0x0001:0x0001/2`、键盘 `0x0001:0x0006/7`、笔、触摸屏，见
   `hid_win.SYSTEM_RESERVED_USAGES`）只能用 `dwDesiredAccess=0` 打开：可读属性/Feature Report，
   不能发指令。**绝不向这些接口写数据。**
6. 固件常常只在特定时机上报（充电插拔、模式切换、鼠标移动），所以协议层带缓存，面板要提示"动一下鼠标"。

## 三台设备的协议事实（已确证，不要重新逆向）

| 设备 | 通道 | 读法 |
|---|---|---|
| 漫步者 G3 Max `35BB:A226` | `0xFF02:0x0002`，RID `0xD0`，64 字节 | 发 `35 BB 01 00`，回 `35 BB 0A 00 01 <电量%> <充电>`；电量 0 视为"耳机没开机/没连上"；HECATE 官方软件开着时 dongle 不回复 |
| 雷柏 VT3S `24AE:1411` | `0xFF00`，19 字节输入 | 纯被动状态帧，第 8 字节电量、第 7 字节充电、3-4/5-6 DPI、18 信号；字段不合理整帧丢弃 |
| 迈从 K87S `3837:3033` | `0x0001:0x0000`，65 字节，RID 仅 `0x00` | 只靠固件推送 `FA FB 07 <电量%> <充电>`；官方 getBattery/getInfo 查询实测零回包。未收尾，详见 `HANDOVER.md` §4 |

## 与用户协作的硬规则

- **发任何写包（Output Report）前，先把完整十六进制字节贴出来让用户逐包确认**；默认全程只读。
  用户日常在用这套键鼠，乱发报文可能弄坏设备。
- 只读操作（枚举、监听、读 Feature Report）可直接跑，无需确认。
- 探索协议优先用「Windows 错误码当探针」，而不是真的把包发给设备。
- 修复迈从电量前先读 `HANDOVER.md` §4.4（未试过的方向）和 §9（建议顺序），避免重复已证伪的尝试。

## 运行时产物（均已 gitignore）

`tray_config.json`（刷新间隔 / 自启开关）、`tray_pid.txt`（单实例 PID）、
`device_last.json`（三台设备的上次读数，由 `last_state.py` 统一落盘）、`*_capture.log`、`__pycache__/`。
默认不写任何日志文件；排查托盘问题用 `python tray_app.py --debug` 前台跑。
