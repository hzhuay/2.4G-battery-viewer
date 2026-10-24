# 交接文档 —— 2.4G 电量查看器（三台设备）

> 最后更新：2026-10-25
> 项目：`D:\workspace\2.4G-battery-viewer`（fork 自 yszyszsz233/2.4G-battery-viewer）
> 目标机器：Windows 11 / Python 3.10+ / 纯 ctypes，零第三方依赖

---

## 0. 一句话现状

| 设备 | 状态 | 电量 |
|---|---|---|
| 漫步者 HECATE G3 Max | ✅ **完全可用** | 79%（官方软件同时报 80%，误差 1%） |
| 雷柏 VT3S | ✅ **完全可用** | 100%，附带 DPI 1600 / 信号强度 |
| 迈从 MCHOSE K87S | 🟡 **只能靠充电插拔触发推送** | 已实测 74%（`FA FB 07`）；有效期 1 小时，过期需再拔插一次 |

面板（`python my_devices.py`）和托盘（`python tray_app.py`）都已经改成**注册表驱动**，
加设备只要改 `devices.py` 一处。

> 另有致动 ZD-S32 手柄（超级传奇卓越版）调查过一次，结论是 2.4G 下没有任何电量通道，
> 已放弃接入，详见 §10。

---

## 1. 目录结构

```
hid_win.py        ctypes 实现的 Windows HID 访问层（枚举 / Feature Report / 异步 Input Report / 能力表）
battery.py        原项目的通用框架 + ATK 鼠标策略（本项目新增设备没走它）
darkrim_proto.py  原项目的杰理 DARKRIM 耳机协议（TLV + CRC16-CCITT）
bt_battery.py     蓝牙 HFP 电量（未公开 PnP 属性 {104EA319-…} 2）

devices.py        ★ 设备注册表：加设备 = 加一条 profile，界面和托盘自动跟着变
edifier_proto.py  漫步者 G3 Max（杰理私有协议）         ✅ 可用
rapoo_proto.py    雷柏 VT3S（被动状态帧）               ✅ 可用
mchose_proto.py   迈从 K87S（杰理 AT 通道）             🟡 见 §4
my_devices.py     简洁面板（GUI）
tray_app.py       托盘常驻
tray_common.py / tray_config.json / win_*.py   托盘公共部分

scan.py           只读盘点本机所有 HID 接口（不发一个字节）
watch.py          并行监听指定 VID 的接口  →  python watch.py 24AE 3837 --seconds 130

tools/            逆向过程用的一次性探测脚本（下面 §6 有清单）
mchose_capture.log  最近一次 15 分钟的迈从抓包日志（只有 2 帧）
```

---

## 2. 漫步者 G3 Max —— ✅ 已完成

**协议来源**：HECATE 官方软件日志（`%APPDATA%\HECATE\log\*.log`），它把每次 HID 收发都打成十六进制。

* 厂商集合 `0xFF02:0x0002`，**输出报告 ID `0xD0`**，报告长 64 字节
* 查询帧：线上字节 `35 BB 01 00`（日志里的 `D0 35 BB 01 00` 中 `D0` 是报告 ID）
* 回包：`35 BB 0A 00 01 <电量%> <充电标志> 01 02 01 01 01 07 …`
* 解析：`edifier_proto.parse_frame()`，电量在 `report[6]`，充电标志在 `report[7]`

**Windows 上的两个坑**（详见 §5）：

* `HidD_SetOutputReport` 会把缓冲区第 0 字节当报告 ID **剥掉**，Linux hidraw 不会 → 照抄 Linux 抓包要多补一个占位字节
* 写入长度必须**正好等于** `OutputReportByteLength`（64），写短了 err=87，一个字节都发不出去

**已知行为**：耳机没开机 / 没连上接收器时，官方日志里是 `0A 00 00 00 00`（电量 0），
所以本项目对 `level == 0` 特殊处理，报「耳机没开机或没连上接收器」而不是显示 0%。

---

## 3. 雷柏 VT3S —— ✅ 已完成

* VID `24AE`，厂商集合 `0xFF00:0x0002`，**纯被动**：鼠标有动作时才上报 19 字节状态帧
* 帧布局（已交叉验证社区文档）：

  | 偏移 | 含义 |
  |---|---|
  | 3-4 | DPI X（小端） |
  | 5-6 | DPI Y |
  | 7 | 充电标志 |
  | **8** | **电量 %** |
  | 12 | 配置槽 |
  | 18 | 连接位 + 信号强度 |

* 解析时做了**强制校验**（电量 ≤100、DPI 100..32000、配置槽 ≤15），任一不合理整帧丢弃，
  防止把别的帧误读成电量
* 鼠标不动就不上报 → `rapoo_proto` 里做了 `CACHE_TTL = 300s` 的缓存，缓存命中时直接返回上次读数
* 实测帧：`07 10 01 40 06 40 06 01 64 00 03 01 00 11 46 01 02 02 b5`
  → 电量 100%、DPI 1600、充电中、第 18 字节随鼠标移动递增（信号/计数）

---

## 4. 迈从 K87S —— 🟡 协议解出来了，但读不到稳定值

这是唯一还没收尾的设备。下面是**已经确证的事实**，不要再重复逆向。

### 4.1 设备信息

* VID `3837` / PID `3033`（2.4G 接收器；键盘本体 USB 是 `3837:200E`）
* 命令通道：`usage page 0x0001` / `usage 0x0000`，输入输出都是 **65 字节，报告 ID 只有 `0x00`**
* 其它可写集合：`0xFF31:0x0074`、`0xFF70:0x0071`（也是 65 字节 RID 0x00，
  而且 `0x0001:0x0000` 和 `0xFF31:0x0074` 会收到**内容完全相同**的帧）
* 系统独占（不能写、只能读属性）：`0x0001:0x0006`（键盘）、`0x0001:0x0002`、`0x000C:0x0001` 等

### 4.2 官方 JS 里挖出来的协议（来源：<https://www.mchose.com.cn/cizhou/> 的 JS bundle）

> 抓取方法：Next.js 站点，`_next/static/chunks/` 下 76 个 chunk。
> **协议代码在 `2233-a1ac28ebe5f04af2.js` 和 `1288-c2b19e148e36df3c.js`**
> （页面自己 `<script>` 引的那些，webpack map 里的 `id.hash.js` 是另一批，只下 map 会漏）。
> 设备清单在 `1288` 的 `ALL_DEVICE_DATA`；K87S 条目：
> `hidFilters:[{usagePage:1,usage:0},{usagePage:65280,usage:1,boot:!0}]`，
> 2.4G 接收器是它的 `spread` 变体（`0x3837_0x3033_MCHOSE K87S 2.4G`）。

**通道 A：class P（老协议，K87S 走的就是这套，官方叫 "Channel:Keyboard"）**

```
线上字节 = [0x55][cmd][0x00][cs][size][offLo][offHi][0x00][payload…]
cs = XOR(size, offLo, offHi, 0, payload…)
命令：3=getInfo(读 56 字节 @ offset 0)  4=getBase  5/6=读写功能配置
      7/8=按键矩阵  14=写 base  160=按键触发
```

社区项目对 K99 V3 用的 `55 03 00 38 38 00 00 00` **就是** `getInfo`（size=56、offset=0、cs=56），
组帧没错，但**实测零回包**（社区试了 492 帧官方格式的 getInfo/getBase，无一回复）。

**通道 B：class J（"Channel:QhwKeyboard"，M 帧）——K87S 不用这套**

```
线上字节 = [RID][version=1][flags=3][length][cmdLo][cmdHi][biz=0][seq][payload…][cs]
cs = XOR(帧[1:])（从 version 开始，不含报告 ID）
命令：2304 getBaseInfo  2305 getFwVersion  2308 getBattery  517 读写配置
      2310 切配置  2324 心跳  34 广播事件
getBattery 回包 data = [充电状态, 电量%]
J.REPORT_ID = 77 (0x4D)，但**接收器上根本没有 0x4D 这个报告 ID**
```

> ⚠️ `flags` 官方是 **3**（社区按鼠标那份抄成了 1）；`seq` 官方是**自增**的；
> `ee` 类（`AA 55 AA 55 AA 55`）是 **bootloader** 用��，绝对不要发。

**设备 → 主机 的 AT 帧（杰理通道，65 字节，第 0 字节是报告 ID 0x00）**

```
00 FA FB 07 <电量%> <充电标志>     ← 电量！
00 FA FB 06 01                     ← 键盘已连上接收器
00 FA FB 06 00                     ← 键盘断开
```

官方 JS 的分发器原文（`2233` chunk，约 46480 位置）：

```js
if(250==t[0]&&251==t[1]&&7==t[2]&&1==t[4]) → emit("charging")
if(250==t[0]&&251==t[1]&&7==t[2]&&0==t[4]) → emit("stopCharging"),
                                                emit("updateBattery",{battery:t[3]})
if(250==t[0]&&251==t[1]&&6==t[2]&&0==t[3]) → emit("stopCommunication")
if(250==t[0]&&251==t[1]&&6==t[2]&&1==t[3]) → emit("startCommunication")
```

注意 `t` 是**去掉报告 ID 之后**的数据（WebHID 的 input report 不含报告 ID）。

**另外**：class P 通道里**没有任何电量查询命令**——官方 JS 的 `refreshChargingStatus()` 是空实现，
只改本地状态。所以**杰理通道的电量就是纯推送**。

### 4.3 实测结论

* ✅ 电量帧：`FA FB 07 <电量%> <充电标志>`（第 4 字节电量、第 5 字节充电）
  * 2026-10-23 复现：插拔充电线时连发两帧 `00 fa fb 07 4a 01` / `00 fa fb 07 4a 00` = **74%**，
    先 charging=1 后 charging=0；两帧都只在 `0x0001:0x0000` 上出现，**没有**镜像到 `0xFF31:0x0074`
  * 早前还抓到过 `FA FB 07 48` = 72%
* ❌ 15 分钟被动监听只收到 2 帧，**只在充/断电切换时广播**；敲键盘只会收到 `FA FB 06 01`（连上）
* ⚠️ `FA FB 06` 帧第 20 字节之后是**固件未初始化缓冲区**（`20 F2 74 00 …` 这类指针值，两条镜像通道上还不一样），
  只解析前 5 字节，不要试图从尾部取字段
* ❌ 官方 M 帧 `getBattery`（cmd 2308）在接收器上**完全无回包**（RID 0x00/0x4D × 长度 9/32/33/64/65 × flags 1/3 全试过）
* ❌ class P 的 `getInfo`（cmd 3）**无回包**
* ❌ **强制走 `WriteFile`** 重发 class-P `getInfo`（`00 55 03 00 38 38 00 00 00` 补零到 65 字节，2026-10-23 实测）：
  `WriteFile` 返回成功，但 9 个接口 **30 秒零回包**。至此「写入方式」这个变量也排除了
  （工具：`tools/probe_mchose_classp.py`）
* ❌ **写入长度扫描已证伪**：Windows 的 `HidD_SetOutputReport` 与 `WriteFile` 都要求长度
  **正好等于 `OutputReportByteLength`(65)**，短一个字节直接 err=87，字节根本不下发。
  所以「扫 8..65 看哪个长度能换来回包」在 Windows 上不可能有任何结果，不要再花时间
* ❌ **class-P 的应答其实存在**：官方网页驱动连上 K87S 后，会持续收到 `aa 03/04/05/07/08/0c/f1/f2`
  （getInfo / base / 配置 / 键位表 / 灯效 / 宏 JSON）。我们自己的 `55 03` 探测零回包，
  说明**探测时机或设备唤醒状态**有差别，但这条通道本身是通的
* ❌ **网页驱动的电量不是查出来的**：2026-10-23 用多线程监听（`tools/capture_mchose_mt.py`）
  在页面刷新 + 重新连接的全过程抓了 3 轮（97 / 196 / 37 帧），**没有一帧含电量**，
  也没有 `aa 30` / `aa 4a` / `aa 0a` 这类姿势
* ❌ **官方 CZ 电量命令 `55 30 a5 0b 2e 01 01 01 00 00` 打给键盘：零回包**
  （该命令来自官方鼠标 app：`AA 30` 第 8 字节电量、第 9 字节充电；工具 `tools/probe_mchose_battery30.py`）
* ❌ 所有接口的 Feature Report 均为 0（`HidD_GetFeature` 全部失败），排除 Feature 查询
* ✅ **官方驱动那个百分比是「过期值」，不是实时读数**（2026-10-23 定论）：
  * 用 CDP 连上 MCHOSE HUB 的 Electron 渲染进程后确认：设备句柄 `opened=true`，
    但整段拔插过程中 **一条 inputreport 都没收到**，`sendReport` 也一次没调
  * 界面显示 **70%**，而设备同一时刻推送的是 **68%**（`FA FB 07 44`）；
    `localStorage["listTempAfter"]` 里存的也是 `batteryLevel: 68`
  * 也就是说：官方界面渲染的是启动时从缓存里取的历史值，插拔充电线后**不会刷新**
  * **我们的读法才是对的** —— 只要收到 `FA FB 07` 就是设备当前真实值
* 💡 值得抄的一点：官方会把最后一次读数**持久化**（`listTempAfter`），所以重开还有数字。
  我们目前只有内存缓存，进程重启就没了。要改善体验可以在 `mchose_proto` 里落盘（带时间戳）

### 4.4 还没试过的可能（下次从这里继续）

1. ~~写入长度不对~~ —— **已排除**：Windows 会校验长度，短写 err=87 且不下发（见 §4.3）。
2. ~~WriteFile vs SetOutputReport~~ —— **已排除**：强制 `WriteFile` 同样零回包（见 §4.3）。
3. **collection 选错**：K87S 官方 hidFilter 是 usagePage 1 / usage 0，和我们选的一致，但三个可写集合都试过了。
4. **键盘休眠**：查询要靠键盘（另一端）应答，键盘睡着就不回。可以让用户持续按键盘再试。
5. **蓝牙路线**（社区的兜底方案）：K87S 支持蓝牙，Windows 会把 BLE HID 的电量写进未公开 PnP 属性
   `{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2`。
   本机目前只配对了 IQUNIX MG65 BT1，**迈从还没配对**——需要用户在 Windows 里配对 K87S 的蓝牙。
   社区的 PowerShell 扫描代码在 `hxw-dream/MCHOSE-Battery` 的 `battery.py`（`_PS_BLE` 变量）。

### 4.5 临时可用状态

`mchose_proto.py` 已按最终结论重写，并在真机上验证过（2026-10-23）：

* `parse_at()` 解析 `FA FB 07` / `FA FB 06`（只看前 5 字节）
* 常驻监听线程 `_listener_loop()`：**纯被动**，以 `write=False` 打开句柄，物理上不可能发包
* `read()` 有缓存直接返回（带「N 分钟前的读数 · 插拔充电线可刷新」），没缓存才等 `wait` 秒
* 最后一次读数**落盘**到 `mchose_last.json`（gitignore），进程重启后仍能显示；超过 1 小时按过期处理，
  报错里带「上次读数 xx%，N 小时前」
* 已真机验证：插拔充电线 → `FA FB 07 4A` → 面板显示 74% 充电中（解析/缓存/读取链路全通）

**当前交付形态**：面板/托盘显示最近一次推送值（1 小时有效），并提示「插拔充电线可刷新」。
要拿到实时电量只剩**蓝牙路线**（用户配对 K87S 蓝牙后用 PnP 属性读）。

---

## 5. 逆向这几个协议时踩到的坑（Windows vs Linux）

1. **Windows 的 `HidD_SetOutputReport` 把缓冲区第 0 字节当「报告 ID」剥掉**，
   Linux 的 hidraw 是原样发送。照抄别人（Linux）抓到的报文常常要**多补一个占位字节**。
2. **写入长度必须正好等于该报告 ID 的长度**，写短了 Windows 拒绝（err=87），一个字节都不下发。
3. **错误码可以当探针**：err=87 = 报告 ID 不存在 / 长度不对；err=1 = ID 存在但不是输出报告。
   → 安全地枚举「哪个集合用哪个报告 ID」（`tools/find_rid.py`）。
4. **同一 HID 句柄上并发「阻塞读 + 写」会直接杀掉进程**（连异常栈都没有）。
   必须用独立的、带 `FILE_FLAG_OVERLAPPED` 的读句柄 + 事件超时 + `CancelIoEx`。
   本项目 `hid_win.HidDevice` 已经这么做了（`self._read_handle`）。
5. **系统独占的顶层集合**（鼠标/键盘/笔/触摸屏）只能用 `dwDesiredAccess=0` 打开，
   能读属性和 Feature Report，但发不了指令 —— 所以本项目永远不会写坏键鼠。
6. **官方软件的日志是最好的协议来源**：HECATE 把每次 HID 收发都打成十六进制；
   迈从的协议藏在网页驱动的 JS bundle 里（Next.js，chunk 文件名 `{id}.{hash}.js`）。
7. **固件可能只在特定时机上报**（充电、切换模式、鼠标移动）。读不到就返回空并缓存上一次的值，
   **绝不显示猜的数字**。

---

## 6. `tools/` 脚本清单

| 脚本 | 用途 |
|---|---|
| `scan.py`（在根目录） | 只读盘点本机所有 HID 接口 |
| `watch.py`（在根目录） | 并行监听指定 VID 的接口 |
| `probe_edifier.py` | 漫步者：打印真实错误码的写包探测 |
| `find_rid.py` | 漫步者：用错误码枚举输出报告 ID |
| `find_channel.py` / `matrix_probe.py` / `probe_full.py` | 漫步者：集合 × 报告 ID 矩阵探测 |
| `rapoo_probe.py` | 雷柏：抓被动状态帧 |
| `listen_all.py` | 全接口监听 |
| `probe_mchose_mframe.py` / `probe_mchose_sweep.py` / `probe_mchose_retry.py` | 迈从：早期 M 帧试探（结论：无效） |
| `probe_mchose_reply.py` | 迈从：发官方握手帧并把回包按索引 dump（结论：零回包） |
| `probe_mchose_rids.py` | 迈从：**只读**枚举各集合的报告 ID 和长度（结论：只有 RID 0x00，长 65） |
| `probe_mchose_qhw.py` | 迈从：按官方 class J 发 getBattery/getBaseInfo/getFwVersion（结论：零回包） |
| `probe_mchose_query.py` | 迈从：逐集合发查询 + 听 20 秒（结论：零回包） |
| `probe_mchose_combo.py` | 迈从：RID × 长度 × flags 全组合（结论：零回包） |
| `probe_mchose_poll.py` | 迈从：2 分钟内每 10 秒发一次查询（结论：零回包） |
| **`probe_mchose_len.py`** | **迈从：class-P 查询帧 + 写入长度扫描（还没跑成功，下次先跑这个）** |
| `capture_mchose.py` | 迈从：15 分钟全集合被动监听，完整 hex 存文件（已跑，抓到 2 帧电量） |

---

## 7. 工具链备忘（这台机器上踩过的坑）

* `git` / `curl` 需要 `--noproxy '*'`（本机配了个死代理 `127.0.0.1:18888`）
* WebFetch 访问 github.com / raw.githubusercontent.com / gitee.com 会被挡，
  改用 GitHub REST API（`api.github.com/repos/<owner>/<repo>/contents/<path>`，内容是 base64）
* Next.js chunk 文件名是 `{id}.{hash}.js`（点号），不是 `{id}-{hash}.js`；
  但 `webpack.js` 的 `p.u` 里有一批用横杠的特例，两种都要试
* Windows 控制台默认 GBK，中文输出会花屏 → 脚本里加
  `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`

---

## 8. 和用户协作的硬规则

1. **发任何写包前，先把要发的十六进制字节贴出来给用户确认，一包一包来**；默认全程只读。
   （他日常正在用这套键鼠，绝不能因为工具乱发报文把设备搞坏。）
2. 只读操作（枚举 / 监听 / 读 Feature Report）可以直接跑，不用问。
3. 写操作只落在厂商集合，**绝不写系统独占的键鼠标准接口**（`0x0001:0x0006` 等）。
4. 探索阶段优先用「Windows 错误码当探针」，避免真的把包发到设备上。

---

## 9. 下一步建议（按性价比排序）

1. ~~扫写入长度~~ / ~~强制 WriteFile~~ —— 已做，均零回包，方向封闭（§4.3）。
2. ~~迈从按「插拔充电线刷新 + 缓存」降级交付~~ —— 已实现并真机验证（§4.5）。
3. ~~雷柏面板补充电 / DPI / 信号~~ —— 已在 `rapoo_proto.read()` 的 `status` / `extra` 里。
4. ~~commit G3 Max + VT3S~~ —— 已完成（`d74c1a9`）。
5. 剩下唯一能让 K87S 电量实时化的：**蓝牙路线**——用户在 Windows 里配对 K87S 蓝牙，
   然后用未公开 PnP 属性 `{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2` 读（`bt_battery.py` 已有实现）。

---

## 10. 附：致动 ZD-S32 手柄（超级传奇卓越版）—— ❌ 2.4G 无电量通道

> 2026-10-25 调查，结论为「放弃」。下面是完整证据链，避免以后有人重走。

### 10.1 三条通道全部堵死

| 通道 | 实测结果 |
|---|---|
| 2.4G 接收器（`413D:2204`）厂商接口 | `0xFF7A` usage **1**、输入输出各 65 字节；写 `10 55 AA 50 01` 及唤醒包都不报错，但**从未回过一帧**；报告 ID `0x00`–`0x0F` 逐个扫过，零回包 |
| 关机重连瞬间 | 60 秒抓包 59332 帧，**全部来自 `0x0001:0x0005` 输入流**，厂商接口 0 帧 |
| XInput 电池 API | 返回 `type=WIRED / level=FULL` —— 接收器直接谎报“有线满电” |
| Windows PnP 电池属性 | 不存在 |
| 官方网页驱动 | <https://hub.zd2015.com/> 页面自己写「请用 USB 有线连接」；代码里接口判定是 `collections.usage === 2`，而接收器是 **usage 1**，驱动不认它 |

官方有线协议倒是解出来了（`js/hid-commands.js`）：发 `10 55 AA 50 01` 补零到 64 字节，
应答 `30 55 AA ...`，**第 10 字节是电量**。但插线就等于充电，数字没意义，所以没有实现。

### 10.2 蓝牙是双链路，但 Windows 连不上

* 手柄在 2.4G 模式下仍持续广播 `ZD-S32-28`（服务 `0xFF10`）
* 实测证明**双链路成立**：手机 App 显示 90% 的同一段时间里，XInput 数据包计数从 10.9 万持续涨到 15.7 万，2.4G 输入没断
* Android 能连能读；**Windows 连不上**：`BluetoothLEDevice` 返回 Success 但**服务数 0**，
  `pair_async` 返回 `FAILED(19)`，bleak 直接超时；把手机配对删掉、关掉手机蓝牙后重试仍是 0
* 从 APK（Flutter，`libapp.so`）里能读到 App 用的服务：`0000FF00/FF01/FF02` + `0x2902` 通知，
  广播里的 `FF10` 在 App 代码里根本不存在 → 2.4G 模式下那条广播只是“能被看见”，服务不可用

结论：Windows 的 BLE 栈与这颗芯片不兼容（本机蓝牙模块本身也常掉到 Code 45），
再往下需要 BLE 抓包器，成本过高。

### 10.3 现在怎么查电量

官方手册只写「连 App 查看」。因为双链路成立，**打游戏时用手机 App 看电量不影响 2.4G 使用**。

网上没有可靠说法能通过指示灯读电量。指示灯只表达「模式 / 配对 / 充电」状态：
蓝 = 有线或接收器、绿 = 蓝牙、红 = Switch、黄闪 = 配对中、连接成功后转自定义呼吸灯。
说明书未定义任何电量含义（只有低电量时可能变色的行业惯例，未经证实）。

### 10.4 相关文件已删除

放弃后删掉了 `zd_proto.py`、`tools/capture_zd.py`、`tools/ble_probe_zd.py`。
调查期间临时装的 `bleak` / `winsdk` 只在开发机上，项目代码不依赖它们。
