# Phone Link OTP Autofill

**iPhone → Bluetooth → Windows Phone Link → 自动识别短信验证码 → 自动填写到当前浏览器焦点。**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 下载

普通用户不需要安装 Python 或 Anaconda。请前往 GitHub 项目的 **Releases** 页面下载最新的：

```text
PhoneLinkOtpAutofill-vX.Y.Z.exe
```

同时提供的 `SHA256SUMS.txt` 可用于校验下载文件是否完整。

这个版本是在已经跑通的 v3 核心逻辑上整理出来的桌面常驻版。它不要求 iPhone 和 Windows 在同一个局域网，因此适合校园网、访客 Wi‑Fi、客户端隔离等环境。

对于宿舍、实验室、图书馆等校园网络，手机和电脑即使连接到同一个 Wi‑Fi，也可能因为 AP/客户端隔离而无法互相访问。本工具的数据链路走 iPhone 与 Windows 之间的蓝牙连接，不要求两台设备处于同一子网，也不需要在校园网中开放电脑端口。

## 已实现

- iPhone + Microsoft Phone Link 短信验证码读取
- 4～8 位验证码识别（中文 / 英文常见 OTP 文案）
- 当前前台浏览器进程识别，不依赖窗口标题
- 自动键入当前键盘焦点，不污染剪贴板
- 浏览器白名单保护
- “智能焦点保护”：发现当前焦点明显是按钮、链接、菜单时先不输入
- 可选“严格输入框检测”
- 系统托盘常驻
- 托盘暂停 10 分钟 / 立即恢复
- 托盘开关自动填写、仅浏览器、严格输入框检测
- 开机自动启动（HKCU，不需要管理员权限）
- 单实例保护，避免重复启动
- 自动重连 Phone Link
- 验证码默认不以明文写入日志
- 自动填充完成后 Windows 托盘通知
- 配置文件持久化

## 第一次测试（推荐）

1. 保持 Windows **手机连接 / Phone Link** 已打开，并确认 iPhone 短信能显示。
2. 双击 `run_debug.bat`。
3. 浏览器打开一个需要短信验证码的招聘网站。
4. 点击“获取验证码”，然后点击验证码输入框。
5. 新短信到达后，验证码应自动键入。
6. 测试稳定后再打包 EXE。

> 默认启用了“智能焦点保护”，但没有强制要求 UI Automation 一定把网页输入框识别成 `EditControl`，以保持和已经跑通的 v3 一样的兼容性。

## 开发环境

项目开发和本地打包统一使用 Conda 的 `game` 环境，Python 版本为 3.10：

```powershell
conda env update -n game -f environment.yml
conda run -n game python test_parser.py
```

直接双击 `run_debug.bat` 会使用 `game` 环境启动程序。

## 打包成单个 EXE

最简单：确认 Conda 的 `game` 环境存在后，双击 `build.bat`。

也可以在 PowerShell 中运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

完成后得到：

```text
dist\PhoneLinkOtpAutofill-vX.Y.Z.exe
```

这是 `--onefile --windowed` 版本，启动时不会出现 PowerShell / CMD 黑框。

GitHub Actions 也会使用 Windows 和 Python 3.10 构建。向 GitHub 推送与 `release_metadata.py` 中 `VERSION` 一致的标签（例如 `v1.0.5`）后，会自动运行测试、生成带版本号的 EXE、计算 SHA-256 并创建 Release。

## 托盘菜单

右下角托盘图标右键：

```text
✓ 自动填写
✓ 仅允许浏览器
  严格输入框检测
----------------
暂停 10 分钟
立即恢复
----------------
✓ 开机自动启动
打开手机连接
打开日志
打开配置目录
----------------
退出
```

### 建议保持的默认设置

- **自动填写：开**
- **仅允许浏览器：开**
- **严格输入框检测：关**

“严格输入框检测”打开后，只有 Windows UI Automation 明确认定焦点控件为 `EditControl` 时才输入。安全性更高，但少数网页的验证码输入框可能识别不到。

## 配置文件

第一次运行后自动创建：

```text
%APPDATA%\PhoneLinkOtpAutofill\config.json
```

主要配置：

```json
{
  "autofill_enabled": true,
  "browser_only": true,
  "strict_input_focus": false,
  "smart_focus_guard": true,
  "poll_interval": 0.35,
  "pending_seconds": 15.0,
  "otp_cooldown_seconds": 120.0,
  "notify_on_fill": true,
  "show_code_in_notification": false,
  "ignore_existing_on_start": true
}
```

`otp_cooldown_seconds` 用于阻止 Phone Link 的多个 UI 文本节点重复触发同一个验证码。只有真正完成键盘输入后才开始计时；默认 120 秒后允许相同数字再次填写。

程序连接 Phone Link 后只建立一次即时文本基线，随后立即监听新验证码。没有成功填写的验证码不会进入额外检测冷却；等待焦点超时后，如果另一个 UI 文本节点再次出现相同验证码，仍可重新进入待填写状态。

### 自定义浏览器

如果你以后使用了特殊浏览器，把其 exe 名称加入 `browser_processes`，例如：

```json
"browser_processes": [
  "chrome.exe",
  "msedge.exe",
  "mybrowser.exe"
]
```

## 日志

日志位置：

```text
%APPDATA%\PhoneLinkOtpAutofill\otp_autofill.log
```

验证码默认会被掩码，例如：

```text
检测到验证码 50**** / 来源=Moka招聘
已填写验证码 50**** / browser=msedge.exe
```

完整验证码不会默认写入磁盘。

## 开机启动

托盘菜单勾选 **“开机自动启动”** 即可。

程序写入当前用户：

```text
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
```

因此不需要管理员权限。

> Phone Link 本身也需要在后台可用。若程序先启动而 Phone Link 尚未打开，它会持续等待，并在 Phone Link 出现后自动连接。

## 安全边界

这个工具会模拟键盘输入，因此建议始终保持：

1. “仅允许浏览器”开启；
2. 点击“获取验证码”后，把光标放到验证码输入框；
3. 不要把 `browser_only` 关闭后长期后台运行；
4. 对非常敏感的网站，可以临时打开“严格输入框检测”。

## 为什么不用局域网转发

在家庭路由器中，“手机访问电脑的局域网地址”通常很容易实现；校园网的情况不同。常见限制包括：

- **AP/客户端隔离**：连接到同一 Wi‑Fi 的终端仍然不能相互访问；
- **VLAN 隔离**：手机和电脑可能被分配到不同的网络或安全域；
- **访客网络限制**：只允许访问互联网，阻止终端之间的入站连接；
- **认证和地址变化**：网页登录、NAC 准入、动态 IP 等机制会增加局域网转发的配置成本。

如果验证码方案要求 iPhone 主动访问电脑 IP、电脑监听 HTTP 端口，或两端通过局域网发现彼此，这些策略都可能让连接直接失败。

本项目采用的链路是：

```text
iPhone
  ↓ Bluetooth
Windows Phone Link
  ↓ UI Automation
PhoneLinkOtpAutofill
  ↓
浏览器当前输入焦点
```

它带来的实际优势是：

- 不需要 iPhone 直接访问电脑的局域网 IP；
- 不需要固定 IP、端口映射、局域网广播或设备发现；
- 不受校园网“同一 Wi‑Fi 但终端不能互访”的限制；
- 切换宿舍、教室、实验室或访客 Wi‑Fi 时，通常不需要重新配置本工具；
- 验证码识别和自动输入均在本机完成，不需要自建中转服务器。

### 使用边界

“验证码链路走蓝牙”不等于电脑完全不需要网络。首次配置 Microsoft 账户、安装或更新 Phone Link，以及某些系统服务可能仍需互联网连接。电脑必须支持蓝牙低功耗（BLE），iPhone 与 Windows 也必须先在 Phone Link 中成功配对并授予消息通知权限。

本项目不会绕过学校或单位的设备管理策略。如果管理员禁用了蓝牙、Phone Link 或跨设备功能，应遵守相应管理要求。

关于 iPhone 与 Phone Link 的系统要求和权限设置，可参考 [Microsoft Phone Link 官方说明](https://support.microsoft.com/windows/apps/phonelink/phone-link-requirements-and-setup)。

## 许可证

本项目采用 [MIT License](LICENSE)。
