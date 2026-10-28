# NetPilot · 应用分流管家

让**指定的应用程序走指定的网络通道**：快橙（国际外网）、SecoClient（公司内网）、WiFi/有线（公网直连），三通道同时在线、互不干扰。

## 组成

| 部分 | 说明 | 是否需要管理员 |
|---|---|---|
| 管理界面 `app/gui.py` | PySide6，规则 / 实时连接 / VPN / 日志四个页签，托盘常驻 | 否 |
| 核心服务 `app/agent.py` | 本地 HTTP 代理（127.0.0.1:19090，令牌认证），管理 sing-box、修复路由、看门狗 | 是（首次 UAC） |
| 分流内核 sing-box 1.14.4 | TUN 网卡 `NetPilot`（172.19.0.1/30），按进程/域名把连接绑到不同网卡 | 由服务启动 |

工作目录：`D:\NetPilot`（配置 `data\netpilot.json`、生成的内核配置 `data\singbox.json`、日志 `logs\`）。

## 从 Release 下载使用（无需 Python）

到 [Releases](https://github.com/Yuzuru0822/NetPilot/releases) 下载 `NetPilot-vX.Y.Z-win64.zip`，解压到任意目录（建议 `D:\NetPilot`，与脚本默认兼容），然后：

1. 双击 `NetPilot.exe` 打开界面；
2. 顶部点"启动核心服务（管理员）"，UAC 点"是"（每次开机首次需要）；
3. 点"启动分流"，在"分流规则"页签给程序分配通道。

发布包内含：`NetPilot.exe`（界面）、`NetPilotAgent.exe`（核心服务）、sing-box 1.14.4 内核、全部控制脚本。系统要求 Windows 10/11 x64，**无需安装 Python**。

## 从仓库重新部署

```powershell
git clone https://github.com/Yuzuru0822/NetPilot.git D:\NetPilot
cd D:\NetPilot
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # 建 venv、装依赖、下载 sing-box
copy netpilot.example.json data\netpilot.json               # 可选：以示例规则起步
```

然后双击 `启动NetPilot.bat`。本机已有的 `data\`（你的真实规则、令牌）和 `logs\` 不会进入 git。

## 快速开始

1. **启动界面**：双击 `NetPilot.exe`（独立 exe，任务栏显示 NetPilot 图标，不依赖 Python 环境）或桌面快捷方式 `NetPilot.lnk`；开发模式也可用 `启动NetPilot.bat`（pythonw 跑脚本）。
2. **启动核心服务**：如果顶部显示"核心服务离线"，点"启动核心服务（管理员）"，在 UAC 弹窗点"是"。之后界面内所有操作不再需要 UAC。
3. **点"启动分流"**。状态变绿即生效。
4. **配置规则**（"分流规则"页签）：
   - **通道绑定**：公网直连默认绑 `以太网`，想走 WiFi 就改成 `WLAN`；快橙绑 `本地连接 2`；公司内网绑 `本地连接`。
   - **新建 / 重命名 / 删除通道**：点"＋ 新建通道"添加（自动分配内部 ID，如 `ch1`）；通道名称可双击重命名，**进程规则、默认通道下拉框会同步更新**（内部 ID 不变，配置不受影响）；每行末尾的 ✕ 删除通道（被规则使用或作为默认通道时不可删）。
   - **进程规则**：点"＋ 添加运行进程"选程序（如 `chrome.exe`、`msedge.exe`），把"通道"列改成目标通道。
   - **默认通道**：没配规则的程序都走这里（默认公网直连）。
   - 改完点"💾 保存并应用"（会自动重启内核，几秒钟）。
5. **验证**：到"实时连接"页签，看每个进程的连接实际走的通道和速率。

### 典型配置

- `chrome.exe` / `msedge.exe` → 快橙·国际：浏览器访问国际外网。
- 其他所有程序 → 默认公网直连。
- 公司内网**不需要**给进程配规则：SecoClient 自己推送的 172.168.x 网段路由比 TUN 更具体，内网流量自动走它（已实测多个内网地址可达）。

## 与两个 VPN 的共存原理（重要）

- 快橙是**全隧道**（推送 `0.0.0.0/1` + `128.0.0.0/1`，metric 3）。Windows 最长前缀优先，所以 NetPilot 也写入自己的 `/1` 路由（经 172.19.0.2，metric 1）抢回默认流量；快橙原有路由保留，供"绑定快橙网卡"的流量使用。
- 看门狗每 5 秒检查：路由被 VPN 重连冲掉会自动补；内核异常退出会先删路由恢复网络再尝试拉起。
- `openvpn.exe`、`SecoClient*.exe`、`aTrust*.exe` 等 VPN 进程**默认固定走公网直连**，避免隧道自身流量进入 TUN 造成重连循环。请不要删除这些规则。
- VPN 断开时，绑定到它的程序会断网（预期行为）；把规则改回直连或重连 VPN 即可。
- SecoClient 首次要手动登录（已帮你勾选"记住密码 / 自动登录"，之后可一键连接）。

## DNS 的说明（本机特例）

本机的安全驱动（深信服 aTrust 的 `SdpNetFlt2.2`，WFP 过滤）会**拦截 53 端口的 DNS 包**，包括发往 NetPilot 网卡和 127.0.0.1 的，因此 NetPilot **不接管、不修改系统 DNS**，域名解析沿用系统现有路径（已验证正常、无污染）。这意味着：

- 目前所有 DNS 实际主要经快橙隧道解析，国内域名的 CDN 就近性可能不是最优，但功能正常。
- 域名规则只影响**连接的去向**，不影响 DNS 用哪个服务器解析。
- 如果哪天系统 DNS 异常，优先检查安全软件/aTrust 的 DNS 保护策略，而不是 NetPilot。

## 故障处理

- **断网/网络异常**：先点界面"停止分流"；无效则双击 `恢复网络.bat`（UAC 后删除 NetPilot 路由并停止 sing-box）。
- **路由被 VPN 抢占**：界面"日志与诊断 → 修复路由"。
- **看日志**："日志与诊断"页签（sing-box 最近 300 行）＋ `logs\agent.log`；`logs\singbox.log` 有完整连接明细。
- **WiFi 与有线切换**：把"公网直连"的绑定网卡改成对应名字后重新应用。
- **彻底停止**：界面停止分流后，可再执行 `curl -X POST -H "X-NetPilot-Token: <data\agent.token 内容>" http://127.0.0.1:19090/shutdown` 关闭服务。

## 打包独立 exe

```powershell
D:\NetPilot\.venv\Scripts\python.exe -m pip install pyinstaller pillow
D:\NetPilot\scripts\make_icon.py        # 可选：重新生成 assets\netpilot.ico
D:\NetPilot\scripts\build_exe.ps1       # 生成单文件 NetPilot.exe 到项目根目录
```

exe 与 `data\`、`scripts\`、`core\` 同级放置即可共享现有配置与内核；`build\` 为中间产物，不入库。

## 开机自启（可选）

管理员 PowerShell 执行一次：

```powershell
D:\NetPilot\scripts\install_autostart.ps1
```

注册登录计划任务（最高权限）后，核心服务开机即来、不再有 UAC 弹窗；界面仍可手动双击启动。卸载用 `uninstall_autostart.ps1`。

## 文件地图

```
D:\NetPilot\
  NetPilot.pyw            界面入口
  启动NetPilot.bat         双击启动界面
  恢复网络.bat             一键恢复网络（管理员）
  app\                   gui / agent / config_builder / agent_client / vpn / netinfo / paths
  core\                  sing-box-1.14.4-windows-amd64\
  data\                  netpilot.json（你的规则）/ singbox.json（生成）/ agent.token
  scripts\               VPN 控制、启停服务、诊断、自启安装等
  logs\                  singbox.log / agent.log / 诊断输出
  docs\ref\              sing-box 官方配置文档（离线参考）
```

技术栈：Python 3.12 + PySide6 + psutil + requests；sing-box TUN + `bind_interface` + `process_name` 规则。
