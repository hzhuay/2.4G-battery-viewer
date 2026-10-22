# 设备电量查看器（雷柏 / 迈从 / 漫步者）

Windows 上读取 2.4G 无线外设电量的小工具。**纯 ctypes 调系统 DLL，零第三方依赖**——
不用 hidapi、不用 pystray、不用 Pillow、不用 pywin32，装了 Python 就能跑。

这是 [yszyszysz233/2.4G-battery-viewer](https://github.com/yszyszysz233/2.4G-battery-viewer) 的 fork，
原项目针对作者的 ATK 鼠标 + DARKRIM 耳机；这里换成了自己的三台设备，并把「设备写死」的
上层改成了**配置驱动**。

## 支持的设备

| 设备 | VID:PID | 怎么读 |
|---|---|---|
| **漫步者 HECATE G3 Max** | `35BB:A226` | 杰理方案。厂商集合 `0xFF02:0x0002`，**输出报告 ID `0xD0`**；发 `35 BB 01 00` 问状态，回 `35 BB 0A 00 01 <电量%> <充电标志>` |
| **雷柏 VT3S** | `24AE:1411` | 厂商集合 `0xFF00:0x0002`，**被动**上报 19 字节状态帧，**第 8 字节是电量**（附带 DPI、信号强度） |
| **迈从 K87S** | `3837:3033` | 命令通道 `0x0001:0x0000`，**固件主动推送** `FA FB 07 <电量%> <充电标志>` / MANUAL_REPORT / baseInfo。⚠️ 这个接收器**不回应任何查询**（官方格式的 getInfo/getBase/getBattery 累计发了 500+ 帧，`HidD_SetOutputReport` 和 `WriteFile` 两种写法都试过，零回复），所以只能常驻监听接推送；插拔充电线能立刻触发一次，读数缓存 1 小时 |

三台的协议来源都写在各自的 `*_proto.py` 文件头注释里。

## 使用方法

```bash
python my_devices.py            # 打开面板（默认自动刷新）
python my_devices.py --once     # 命令行读一次就退出
python scan.py                  # 只读盘点本机所有 HID 接口（不发一个字节）
python watch.py 24AE 3837       # 并行监听指定 VID 的接口（设备只在有动作时才上报时用）
```

面板里每台设备一张卡片，显示百分比 + 进度条 + 数据来源；底部可以改刷新间隔。

## 架构

```
hid_win.py        ctypes 实现的 Windows HID 访问层（枚举 / Feature Report / 异步 Input Report / 能力表）
battery.py        多策略电量读取 + 厂商协议表（通用框架）
devices.py        ★ 设备注册表：加设备 = 加一条 profile，界面和托盘自动跟着变
edifier_proto.py  漫步者 G3 Max（杰理私有协议）
rapoo_proto.py    雷柏（被动状态帧）
mchose_proto.py   迈从（固件推送）
bt_battery.py     蓝牙耳机 HFP 电量
my_devices.py     简洁面板
tray_app.py       托盘常驻（图标数量由注册表决定）
tools/            逆向过程用的一次性探测脚本
```

## 逆向这几个协议时踩到的坑

1. **Windows 的 `HidD_SetOutputReport` 会把第 0 字节当「报告 ID」剥掉**，
   而 Linux 的 hidraw 是原样发送。照抄别人（Linux）抓到的报文时，
   常常要**多补一个字节**才对得上，否则设备完全不响应。
2. **长度必须正好等于 `OutputReportByteLength`**，写短了 Windows 直接拒绝（err=87），
   一个字节都不会下发。
3. **Windows 会在下发前校验报告 ID**：
   - err=87 → 这个报告 ID 不存在
   - err=1 → 这个 ID 存在，但不是输出报告（多半是输入报告）
   拿错误码当探针，可以安全地把「哪个集合用哪个报告 ID」试出来。
4. **同一 HID 句柄上并发「阻塞读 + 写」会直接杀掉进程**（连异常栈都没有）。
   正确做法是独立的、带 `FILE_FLAG_OVERLAPPED` 的读句柄 + 事件超时 + `CancelIoEx`。
5. **系统独占的顶层集合**（鼠标/键盘/笔/触摸屏）只能用 `dwDesiredAccess=0` 打开，
   能读属性和 Feature Report，但不能发指令 —— 所以本项目永远不会写坏键鼠。
6. **官方软件的日志是最好的协议来源**：HECATE 把每次 HID 收发都打成十六进制，
   直接抄，比盲猜快十倍。
7. **固件可能只在特定时机上报**（充电、切换模式、鼠标移动）。
   读不到就返回空并缓存上一次的值，**绝不显示猜的数字**。

## 环境要求

- Windows 10 / 11
- Python 3.10+（需要 `tkinter`，官方安装包默认自带）

## 隐私

- **不联网**：没有任何 http / socket / urllib / 遥测调用，所有读取都在本地 HID 层完成。
- **不写日志**：默认不产生任何日志文件；只有 `--debug` 时才往控制台打印。
- **不上传**：设备序列号、地址等信息只在内存里用，不落盘。

## 说明

私有协议部分是通过逆向厂商软件 + 抓包分析得到的，仅供学习与个人使用。
