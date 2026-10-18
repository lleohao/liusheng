#!/usr/bin/env python3
"""Liusheng — phone-to-focused-input text paste on Linux and macOS."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from util.lan_address import is_loopback_host, lan_ipv4_address
from util.terminal_qr import print_terminal_qr

ROOT = Path(__file__).resolve().parent
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8"),
    "/sw.js": ("sw.js", "text/javascript; charset=utf-8"),
    "/icons/icon.svg": ("icons/icon.svg", "image/svg+xml"),
    "/icons/icon-192.png": ("icons/icon-192.png", "image/png"),
    "/icons/icon-512.png": ("icons/icon-512.png", "image/png"),
    "/icons/icon-maskable-512.png": ("icons/icon-maskable-512.png", "image/png"),
    "/icons/apple-touch-icon.png": ("icons/apple-touch-icon.png", "image/png"),
}
MAX_BODY = 256 * 1024
MAX_TEXT = 64_000
INPUT_LOCK = threading.Lock()
TERMINAL_APP_IDS = (
    "foot", "alacritty", "kitty", "ghostty", "wezterm", "konsole",
    "gnome-terminal", "gnome.console", "org.gnome.console", "xterm",
    "tilix", "terminator", "st", "rio", "com.mitchellh.ghostty",
    "org.wezfurlong.wezterm", "com.raggesilver.blackbox", "io.elementary.terminal",
)
MACOS_FOCUS_SCRIPT = '''
ObjC.import('AppKit');
var app = $.NSWorkspace.sharedWorkspace.frontmostApplication;
JSON.stringify(app.isNil() ? null : {
    id: Number(app.processIdentifier),
    app_id: ObjC.unwrap(app.bundleIdentifier) || '',
    title: ObjC.unwrap(app.localizedName) || ''
});
'''


def focused_window():
    macos = sys.platform == "darwin"
    tool = "osascript" if macos else "niri"
    if not shutil.which(tool):
        return None
    try:
        completed = subprocess.run(
            (["osascript", "-l", "JavaScript", "-e", MACOS_FOCUS_SCRIPT]
             if macos else ["niri", "msg", "--json", "focused-window"]),
            text=True, capture_output=True, timeout=2, check=True,
        )
        result = json.loads(completed.stdout)
        return result if isinstance(result, dict) and result.get("id") is not None else None
    except (subprocess.SubprocessError, OSError, ValueError):
        return None


def get_backend(configured):
    supported = ("macos",) if sys.platform == "darwin" else (
        ("wtype", "ydotool") if sys.platform.startswith("linux") else ())
    if configured == "auto":
        for item in supported:
            if shutil.which("osascript" if item == "macos" else item):
                return item
        return None
    if configured not in supported:
        return None
    return configured if shutil.which("osascript" if configured == "macos" else configured) else None


def clipboard_tool():
    return "pbcopy" if sys.platform == "darwin" else "wl-copy"


def missing_backend_message():
    if sys.platform == "darwin":
        return "macOS 输入后端不可用：请使用 --backend auto 或 macos，并检查 osascript"
    return "输入后端不可用：Linux 请安装 wtype 或 ydotool；macOS 请使用系统自带 osascript"


def paste_shortcut(app_id, mode):
    if mode == "normal":
        return "normal"
    if mode == "terminal":
        return "terminal"
    app = (app_id or "").lower()
    is_terminal = any(
        app == part or app.startswith(part + "-") or app.startswith(part + ".")
        or app.endswith("." + part)
        for part in TERMINAL_APP_IDS
    )
    return "terminal" if is_terminal else "normal"


def run_command(args, *, input_data=None):
    # pbcopy otherwise falls back to legacy encodings in launchers without a locale.
    command_env = {**os.environ, "LC_ALL": "en_US.UTF-8"} if args[0] == "pbcopy" else None
    try:
        # wl-copy forks a clipboard owner that inherits its output descriptors.
        # Pipes make communicate() wait for that owner and falsely time out.
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as output:
            result = subprocess.run(
                args, input=input_data, encoding="utf-8", errors="replace",
                stdout=output, stderr=output, env=command_env, timeout=4, check=False,
            )
            output.seek(0)
            detail = output.read(4096).strip()
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"命令执行超时：{args[0]}") from exc
    except OSError as exc:
        raise RuntimeError(f"无法执行 {args[0]}：{exc}") from exc
    if result.returncode:
        raise RuntimeError(f"{args[0]} 执行失败：{(detail or '未知错误')[:400]}")


def emit_paste(backend, mode):
    if backend == "macos":
        run_macos_key("key code 9 using command down")
    elif backend == "wtype":
        if mode == "terminal":
            run_command(["wtype", "-M", "ctrl", "-M", "shift", "-k", "v", "-m", "shift", "-m", "ctrl"])
        else:
            run_command(["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"])
    elif backend == "ydotool":
        if mode == "terminal":
            # Linux key codes: LEFTCTRL=29, LEFTSHIFT=42, V=47
            run_command(["ydotool", "key", "29:1", "42:1", "47:1", "47:0", "42:0", "29:0"])
        else:
            run_command(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"])
    else:
        raise RuntimeError(missing_backend_message())


def run_macos_key(action):
    # Only fixed key commands enter AppleScript; dictated text goes to pbcopy stdin.
    try:
        run_command(["osascript", "-e", f'tell application "System Events" to {action}'])
    except RuntimeError as exc:
        raise RuntimeError(
            f"{exc}；请检查 macOS 系统设置 → 隐私与安全性 → 辅助功能，"
            "授权启动服务的终端或应用，并在自动化中允许控制 System Events；"
            "授权后请手动重试"
        ) from exc


def emit_key(backend, key):
    if key not in ("enter", "ctrl_enter"):
        raise ValueError("无效的按键")
    if backend == "macos":
        action = "key code 36" + (" using control down" if key == "ctrl_enter" else "")
        return run_macos_key(action)
    elif backend == "wtype":
        command = (["wtype", "-M", "ctrl", "-k", "Return", "-m", "ctrl"]
                   if key == "ctrl_enter" else ["wtype", "-k", "Return"])
    elif backend == "ydotool":
        # Linux key codes: LEFTCTRL=29, ENTER=28
        command = (["ydotool", "key", "29:1", "28:1", "28:0", "29:0"]
                   if key == "ctrl_enter" else ["ydotool", "key", "28:1", "28:0"])
    else:
        raise RuntimeError(missing_backend_message())
    # Never retry: a failure can occur after the target received the key.
    run_command(command)


def deliver_key(key, configured_backend, text=""):
    if key not in ("enter", "ctrl_enter"):
        raise ValueError("无效的按键")
    if not isinstance(text, str):
        raise ValueError("无效的文字")
    if text:
        return deliver(text, "auto", configured_backend, after_key=key)
    backend = get_backend(configured_backend)
    if backend is None:
        raise RuntimeError(missing_backend_message())
    with INPUT_LOCK:
        target = focused_window()
        emit_key(backend, key)
    return {"ok": True, "backend": backend, "key": key, "target": target,
            "message": "已发送按键（无法确认目标应用是否响应）"}


def deliver(text, paste_mode, configured_backend, *, after_key=None):
    if not text:
        raise ValueError("不能发送空文本")
    if len(text) > MAX_TEXT:
        raise ValueError(f"文字过长，最多 {MAX_TEXT} 字符")
    if "\x00" in text:
        raise ValueError("文字不能包含空字符")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("文字包含无效的 Unicode 字符") from exc
    tool = clipboard_tool()
    if not shutil.which(tool):
        raise RuntimeError(f"剪贴板工具不可用：{tool}（Linux 请安装 wl-clipboard）")

    backend = get_backend(configured_backend)
    if backend is None:
        raise RuntimeError(missing_backend_message())

    with INPUT_LOCK:
        target = focused_window()
        detected = "normal" if backend == "macos" else paste_shortcut((target or {}).get("app_id"), paste_mode)
        command = ["pbcopy"] if backend == "macos" else ["wl-copy", "--type", "text/plain;charset=utf-8"]
        run_command(command, input_data=text)
        # A failure may follow partial execution; don't risk pasting twice.
        emit_paste(backend, detected)
        if after_key:
            # Give the target time to consume the clipboard before submitting.
            time.sleep(0.15)
            try:
                emit_key(backend, after_key)
            except RuntimeError as exc:
                raise RuntimeError(f"已触发文字粘贴，但未确认回车结果：{exc}") from exc

    return {"ok": True, "backend": backend, "paste_mode": detected,
            "target": target, "message": "已发送粘贴快捷键（无法确认目标应用是否实际插入）"}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data, code=200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in STATIC_FILES:
            filename, content_type = STATIC_FILES[path]
            raw = (ROOT / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif path == "/api/status":
            self.send_json({
                "ok": True,
                "backend": get_backend(self.server.backend),
                "clipboard": bool(shutil.which(clipboard_tool())),
                "target": focused_window(),
            })
        else:
            self.send_json({"ok": False, "message": "未找到页面"}, 404)

    def do_POST(self):
        if self.path not in ("/api/send", "/api/key"):
            return self.send_json({"ok": False, "message": "未找到接口"}, 404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.send_json({"ok": False, "message": "请求格式错误"}, 400)
        if length < 1 or length > MAX_BODY:
            return self.send_json({"ok": False, "message": "请求大小不合法"}, 413)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("请求格式错误")
            if self.path == "/api/key":
                result = deliver_key(payload.get("key"), self.server.backend, payload.get("text", ""))
                return self.send_json(result)
            if not isinstance(payload.get("text"), str):
                raise ValueError("缺少文字")
            mode = payload.get("paste_mode", "auto")
            if mode not in ("auto", "normal", "terminal"):
                raise ValueError("无效的粘贴模式")
            result = deliver(payload["text"], mode, self.server.backend)
            self.send_json(result)
        except (ValueError, UnicodeError) as exc:
            self.send_json({"ok": False, "message": str(exc)}, 400)
        except RuntimeError as exc:
            self.send_json({"ok": False, "message": str(exc)}, 503)

    def log_message(self, fmt, *args):
        # No content logging: useful when dictating private notes or source code.
        if not self.path.startswith("/api/status"):
            super().log_message(fmt, *args)


def print_startup_banner(host, port, backend):
    startup_host = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"\n流声 Liusheng 已启动： http://{startup_host}:{port}", flush=True)
    phone_url = None
    if host == "0.0.0.0":
        address = lan_ipv4_address()
        if address:
            phone_url = f"http://{address}:{port}"
            print(f"手机访问： {phone_url}", flush=True)
        else:
            print(
                "手机访问： 未检测到局域网地址；macOS 请在系统设置 → 网络查看，"
                "Linux 请使用 hostname -I",
                flush=True,
            )
    elif is_loopback_host(host):
        print(f"手机访问： 不可用（服务仅监听 {host}）", flush=True)
    else:
        phone_url = f"http://{host}:{port}"
        print(f"手机访问： {phone_url}", flush=True)
    if phone_url:
        print_terminal_qr(phone_url)
    print(f"输入后端：{get_backend(backend) or missing_backend_message()}", flush=True)
    print("在桌面登录会话的终端中运行；macOS 需辅助功能及自动化权限；Ctrl+C 停止。\n", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Liusheng: phone -> focused input on Linux/macOS")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--backend", choices=("auto", "wtype", "ydotool", "macos"), default="auto")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.backend = args.backend
    print_startup_banner(args.host, server.server_port, args.backend)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
