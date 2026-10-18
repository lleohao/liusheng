# 流声 Liusheng

**使用手机键盘或语音输入，在电脑当前输入框中输入文字。**

[English](README.md) · [MIT 许可证](LICENSE)

手机打开网页，用手机输入法进行语音转写，再将文字发送到 **Niri/Wayland Linux 或 macOS** 当前聚焦的输入框。服务通过电脑剪贴板和模拟快捷键完成输入，无需使用浏览器麦克风或安装手机原生 App。

## 功能

- 支持中文、Emoji 和多行 Unicode 文本。
- 底部单排工具栏：左侧发送图标只粘贴文字，中间加宽的「回车」先粘贴再回车，右侧图标先粘贴再发送 Control+回车。
- 草稿为空时，回车和 Control+回车只发送对应按键。
- 输入框上方提供「确定」「推送代码」「创建 PR」快捷文本，点击发送对应文字并回车，保留现有草稿。
- 显示目标应用、连接状态和发送结果；草稿保存在手机浏览器本地。
- 支持 PWA 和离线编辑，断线时不排队发送，也不会在恢复连接后自动补发。

手机界面目前使用中文。语音识别由手机输入法提供，服务收到的是识别完成的文本。

## 环境要求

| 电脑平台 | 依赖 | 粘贴快捷键 |
| --- | --- | --- |
| Niri/Wayland Linux | Python 3、`wl-clipboard`、`wtype` | 普通输入框 Ctrl+V，识别到的终端 Ctrl+Shift+V |
| macOS | Python 3、系统自带的 `pbcopy` 和 `osascript`，以及辅助功能和自动化权限 | Command+V，包括终端 |

Linux 可使用 `ydotool` 替代 `wtype`，需要单独配置并授权 `ydotoold`。其他 Wayland 桌面可能可用，但尚未验证；Linux 目标应用检测依赖 Niri。不支持 X11 和 Windows。

macOS 后端已添加模拟系统命令的自动测试，真实输入效果、应用兼容性及权限弹窗仍需在 Mac 实机验证。

## 快速开始

### 1. 安装依赖

Linux 按发行版选择：

```bash
# Arch / EndeavourOS
sudo pacman -S --needed python wl-clipboard wtype

# Fedora
sudo dnf install python3 wl-clipboard wtype

# Debian / Ubuntu，取决于软件源是否提供
sudo apt install python3 python3-venv wl-clipboard wtype
```

macOS 只需安装 Python 3；已使用 Homebrew 时可执行 `brew install python`。不需要安装 Linux 输入工具或执行 `pip install`。

推荐使用的 `run.sh` 启动脚本会自动创建 `.venv`，并从 `requirements.txt` 安装二维码组件。手动启动时，可在运行服务的 Python 环境中安装该组件：

```bash
python3 -m pip install -r requirements.txt
```

安装 `qrcode` 后，服务启动时会自动打印手机访问 URL 及其二维码。未安装时会静默跳过二维码，仍正常启动并打印 URL。

### 2. 在目标电脑启动服务

下载或克隆仓库，在桌面登录会话内的终端中执行：

```bash
cd niri-voice-input
./run.sh
```

该脚本会创建或复用 `.venv`、安装当前依赖，并启动 `server.py`。其他参数会继续传递，例如 `./run.sh --port 9000`。

Linux 终端需要继承 `WAYLAND_DISPLAY`、`NIRI_SOCKET` 等会话变量。macOS 请先从 Terminal 或 iTerm2 等可授权的终端启动，并完成下方权限配置。

默认监听 `0.0.0.0:8765`。服务启动时会自动检测电脑默认网络路由所使用的 IPv4 地址，并在终端打印可直接访问的手机 URL；已安装 `qrcode` 时还会自动打印二维码。手机和电脑连接同一可信网络，在手机浏览器打开该地址或扫描二维码：

```text
手机访问： http://192.168.x.x:8765
```

自动检测失败时服务仍会正常启动，终端会提示如何手动查询地址。使用 VPN 或特殊路由配置时，检测结果可能不是手机能够访问的 Wi-Fi 或有线网络地址。

### 3. 输入和发送

1. 在电脑上聚焦目标输入框，首次测试建议选择普通文本编辑器。
2. 在手机页面输入文字，或使用手机键盘的麦克风进行语音转写。
3. 点击左侧纸飞机只粘贴文字，点击中间「回车 ↵」先粘贴再回车，右侧图标发送文字和 Control+回车。
4. 成功后清空已发送的草稿；失败或结果不确定时保留草稿。快捷文本始终保留原有草稿。

具体提交还是换行由目标应用决定。**Control+回车在 Mac 上仍是 Control，不会自动转换成 Command+回车。**

## macOS 权限配置

服务通过 `pbcopy` 写入剪贴板，通过 `osascript` 调用 System Events 发送固定按键命令。用户文字只通过标准输入传给剪贴板，不会拼接进 AppleScript。

1. 在终端启动服务，用手机向普通文本编辑器尝试发送。
2. 打开「系统设置 → 隐私与安全性 → 辅助功能」，授权启动服务的应用，通常是当前使用的终端。若系统提示的应用身份不同，以系统提示为准。
3. 出现控制 **System Events** 的授权提示时允许；也可在「隐私与安全性 → 自动化」中检查对应权限。
4. 必要时重启服务，重新聚焦目标输入框；先检查上次是否已插入文字，再手动重试。

参考 Apple 的[辅助功能授权说明](https://support.apple.com/guide/mac-help/allow-accessibility-apps-to-access-your-mac-mh43185/mac)和 [UI 自动化说明](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/AutomatetheUserInterface.html)。

页面「已连接」表示所需命令可用，不代表已获得 macOS 权限；发送时会显示权限相关错误。目标检测显示前台应用名称，不读取文档或窗口标题；检测失败不会阻止发送。

建议先在已授权的终端前台运行。仓库内的 systemd 服务仅适用于 Linux；改用其他启动器或后台服务时，可能需要重新授权。

## 启动参数

```bash
python3 server.py --host 0.0.0.0 --port 8765 --backend auto
```

- `auto`：macOS 自动使用 `macos`；Linux 优先选择 `wtype`，未安装时选择 `ydotool`。
- `macos`：明确使用 macOS 系统工具。
- `wtype` / `ydotool`：明确使用对应 Linux 后端。
- `--host 127.0.0.1`：只接受本机连接，手机无法直接访问。

执行失败后不会自动重试或切换其他后端，避免已发生部分输入时再次粘贴或提交。

## Linux 用户服务

仓库位于 `~/projects/niri-voice-input` 时，在 Niri 桌面终端执行：

```bash
mkdir -p ~/.config/systemd/user
cp niri-voice-input.service ~/.config/systemd/user/
systemctl --user import-environment WAYLAND_DISPLAY NIRI_SOCKET
systemctl --user daemon-reload
systemctl --user enable --now niri-voice-input.service
```

其他仓库路径或 Python 安装位置，请先修改 service 文件中的 `WorkingDirectory` 和 `ExecStart`。服务跟随 `graphical-session.target`，需要桌面正确启动和停止该 target。

```bash
systemctl --user status niri-voice-input.service
journalctl --user -u niri-voice-input.service -n 50
systemctl --user restart niri-voice-input.service
# 停止并取消自动启动
systemctl --user disable --now niri-voice-input.service
```

## 手机桌面安装与离线使用

通过局域网 HTTP 地址即可正常输入。启用 Service Worker 缓存及受支持浏览器的 PWA 安装功能，需要为**自己的服务实例**配置 HTTPS，本机开发也可使用 localhost。页面和 `/api/*` 必须连接同一台目标电脑服务；不要将无鉴权的服务暴露到公网。

- Android Chrome：使用菜单中的「安装应用」或「添加到主屏幕」，以浏览器实际提供的选项为准。
- iPhone Safari：分享 → 添加到主屏幕。

在安全上下文中首次联网访问后，会缓存页面和图标。断网时仍可打开页面、编辑和保留草稿，但发送和状态检测需要联网。断线不会排队发送，恢复后不会自动重放。Service Worker 对页面使用网络优先策略，不缓存 API。

## 排错与限制

- **网页打不开**：检查局域网 IP、网络隔离、端口和电脑防火墙，只允许可信网络访问。
- **`run.sh` 提示缺少 pip**：Debian 或 Ubuntu 请执行 `sudo apt install python3-venv`，然后重新运行 `./run.sh`；启动脚本会自动修复未完成的 `.venv`。
- **缺少组件**：Linux 执行 `command -v wl-copy wtype`；macOS 执行 `command -v python3 pbcopy osascript`。
- **macOS 权限错误**：按照上方步骤授权，权限需要对应实际启动服务的应用。
- **显示成功但没有文字**：成功只表示命令执行完毕，不代表目标应用接受了输入。请检查焦点和粘贴快捷键；安全输入框或不可编辑控件可能拒绝模拟输入。
- **Linux 终端无法粘贴**：确认终端支持 Ctrl+Shift+V，并检查 Niri 返回的应用 ID。
- **Niri/wtype 输入异常**：配置好 `ydotoold` 后，可尝试 `python3 server.py --backend ydotool`。
- **慢速应用尚未粘贴完就收到回车**：当前粘贴和回车之间使用短暂固定延迟，没有应用级确认。重试前请检查目标内容。
- 会覆盖电脑当前剪贴板，暂不恢复；草稿保存在手机浏览器本地存储中。
- 向终端发送文字和回车可能执行命令；发送过程中请保持目标焦点不变。
- **未内置鉴权或 TLS，仅限可信网络使用。** 能连接服务的人均可向电脑发送文字和支持的按键。

## 开发与测试

核心服务仅使用 Python 标准库；可选的 `qrcode` 包用于打印启动二维码，Node.js 只用于 Service Worker 测试。

```bash
python3 -m unittest -v
node --test test_sw.mjs
```

输入测试使用模拟系统命令，不会向真实应用输入。macOS 测试覆盖后端选择、剪贴板、组合键和权限错误提示，不代替 Mac 实机验收。修改缓存资源时，请递增 `sw.js` 中的缓存版本。

## 许可证

[MIT](LICENSE)。
