# Liusheng (流声)

**Use your phone's keyboard or voice input to type on your computer.**

[中文文档](README.zh-CN.md) · [MIT License](LICENSE)

Open the web page on your phone, dictate with your phone keyboard, and send the recognized text to the focused input on **Niri/Wayland Linux or macOS**. The server uses the desktop clipboard and simulated keyboard shortcuts. No browser microphone access or native phone app is required.

## Features

- Unicode text input, including Chinese, emoji, and multiple lines.
- A compact toolbar: send text, **send text + Return**, or send text + Control+Return.
- Return is the main button. With an empty draft, Return and Control+Return send only the key.
- One-tap phrases: `确定` (Confirm), `推送代码` (Push code), and `创建 PR` (Create PR). Each sends its phrase followed by Return and preserves your draft.
- Current target app, connection status, and delivery feedback.
- Local draft storage and an installable PWA with an offline editor.

The mobile UI is currently in Chinese. Voice recognition is provided by your phone keyboard; Liusheng receives the resulting text.

## Requirements

| Desktop | Requirements | Paste shortcut |
| --- | --- | --- |
| Linux with Niri/Wayland | Python 3, `wl-clipboard`, `wtype` | Ctrl+V; Ctrl+Shift+V for recognized terminals |
| macOS | Python 3, built-in `pbcopy` and `osascript`, Accessibility and Automation permissions | Command+V, including terminals |

Linux can use `ydotool` instead of `wtype`; configure and authorize `ydotoold` separately. Other Wayland compositors may work but are not verified; target detection is specific to Niri. X11 and Windows are not supported.

The macOS backend has automated tests using mocked system commands. Real macOS input, app compatibility, and permission prompts still need validation on a Mac.

## Quick start

### 1. Install dependencies

On Linux, use the command for your distribution:

```bash
# Arch / EndeavourOS
sudo pacman -S --needed python wl-clipboard wtype

# Fedora
sudo dnf install python3 wl-clipboard wtype

# Debian / Ubuntu, if the packages are available
sudo apt install python3 python3-venv wl-clipboard wtype
```

On macOS, install Python 3 if needed (for example, `brew install python` if you already use Homebrew). No `pip` dependencies or Linux input tools are required.

The recommended `run.sh` launcher creates `.venv` and installs the QR renderer from `requirements.txt`. For a manual start, install it into the Python environment that runs the server:

```bash
python3 -m pip install -r requirements.txt
```

When `qrcode` is installed, startup prints the phone URL and its QR code automatically. If the package is missing, the server silently skips the QR code and still prints the URL normally.

### 2. Start the server on the target computer

Download or clone this repository, then run from a terminal inside your desktop login session:

```bash
cd niri-voice-input
./run.sh
```

The launcher creates or reuses `.venv`, installs current dependencies, and starts `server.py`. Extra arguments are forwarded, for example `./run.sh --port 9000`.

On Linux, the terminal must inherit `WAYLAND_DISPLAY` and `NIRI_SOCKET`. On macOS, start from a terminal app you can authorize, such as Terminal or iTerm2; complete the permissions steps below.

The default address is `0.0.0.0:8765`. At startup, the server detects the IPv4 address selected by the computer's default network route and prints a ready-to-open phone URL. If `qrcode` is installed, it also prints a QR code automatically. Connect your phone to the same trusted network and open the URL or scan the code:

```text
手机访问： http://192.168.x.x:8765
```

If automatic detection fails, startup continues and the console tells you how to find the address manually. A VPN or unusual routing setup may cause the detected address to differ from the Wi-Fi or Ethernet address your phone can reach.

### 3. Use it

1. Focus an editable field on your computer, initially in a harmless text editor.
2. On your phone, type or dictate into the page's editor.
3. Tap the left paper-plane icon to paste only, the large center **回车 ↵** button to paste and press Return, or the right Control+Return icon for that combination.
4. Successful requests clear the sent draft; failed or uncertain requests preserve it. Quick phrases always preserve the draft.

Whether Return submits or inserts a line break depends on the target app. **Control+Return means the Control key on both platforms; it does not become Command+Return on macOS.**

## macOS permissions

The server uses `pbcopy` for text and AppleScript through System Events for fixed key commands. User text is passed to the clipboard through stdin, never interpolated into AppleScript.

1. Start the server from your terminal app and try sending to a text editor from your phone.
2. Open **System Settings → Privacy & Security → Accessibility** and authorize the app responsible for launching the server, usually your terminal app. Follow the identity named by macOS if it differs.
3. If prompted to control **System Events**, allow it. Review the corresponding entry under **Privacy & Security → Automation**.
4. Restart the server if needed, focus the target field, and retry manually after checking whether the previous attempt inserted anything.

See Apple's guides to [Accessibility access](https://support.apple.com/guide/mac-help/allow-accessibility-apps-to-access-your-mac-mh43185/mac) and [UI scripting](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/AutomatetheUserInterface.html).

“Connected” confirms that required commands are available, not that macOS permissions are granted. Permission failures are reported when sending. App detection shows the frontmost app's name, not its document or window title; detection failures do not prevent sending.

Start manually from an authorized terminal first. The included systemd service is Linux-only. Running under a different launcher or a background service can require separate macOS authorization.

## Options

```bash
python3 server.py --host 0.0.0.0 --port 8765 --backend auto
```

- `auto`: macOS selects `macos`; Linux prefers `wtype`, then `ydotool`.
- `macos`: explicitly select the native macOS tools.
- `wtype` / `ydotool`: explicitly select a Linux backend.
- `--host 127.0.0.1`: accept local connections only; your phone cannot connect directly.

Backend failures are never retried or automatically switched to another backend, because the first attempt may already have inserted text or submitted an action.

## Linux user service

For a checkout at `~/projects/niri-voice-input`, run inside the Niri desktop session:

```bash
mkdir -p ~/.config/systemd/user
cp niri-voice-input.service ~/.config/systemd/user/
systemctl --user import-environment WAYLAND_DISPLAY NIRI_SOCKET
systemctl --user daemon-reload
systemctl --user enable --now niri-voice-input.service
```

For other checkout locations or Python installations, edit `WorkingDirectory` and `ExecStart` in the service first. The service follows `graphical-session.target`, so your desktop must start and stop that target.

```bash
systemctl --user status niri-voice-input.service
journalctl --user -u niri-voice-input.service -n 50
systemctl --user restart niri-voice-input.service
# Stop and disable automatic startup
systemctl --user disable --now niri-voice-input.service
```

## Phone installation and offline use

The LAN HTTP URL works for normal input. To enable service-worker caching and PWA installation where supported, serve **your own instance** over HTTPS (localhost also works for development). Both the page and `/api/*` must reach the same desktop server. Do not expose this unauthenticated server to the public internet.

- Android Chrome: use “Install app” or “Add to Home screen,” where available.
- iPhone Safari: Share → Add to Home Screen.

After an initial online visit in a secure context, the page and icons are cached. You can open the editor and retain drafts offline, but sending and status checks require a live server. Requests are never queued or replayed on reconnection. The service worker uses network-first shell caching and never caches API calls.

## Troubleshooting and limits

- **Cannot open the page:** check the LAN IP, network isolation, port, and desktop firewall. Allow incoming access only on your trusted network.
- **`run.sh` reports that pip is missing:** on Debian or Ubuntu, install the virtual-environment support with `sudo apt install python3-venv`, then run `./run.sh` again. The launcher will repair the incomplete `.venv` automatically.
- **Missing components:** Linux: `command -v wl-copy wtype`; macOS: `command -v python3 pbcopy osascript`.
- **macOS permission error:** follow the steps above. Authorization must apply to the app that actually launches the server.
- **Sent but no text:** delivery means commands ran, not that the destination accepted them. Check focus and the app's paste shortcuts. Secure or non-editable fields may reject simulated input.
- **Linux terminal paste fails:** check whether the app supports Ctrl+Shift+V and whether Niri reports its app ID correctly.
- **Input problems with Niri/wtype:** try `python3 server.py --backend ydotool` after setting up `ydotoold`.
- **Return arrives before a slow paste finishes:** there is a short fixed delay between paste and Return, not an application-level acknowledgment. Check the destination before retrying.
- The desktop clipboard is overwritten and is not restored. Drafts remain in your phone browser's local storage.
- Sending text and Return into a terminal may execute commands. Keep the intended target focused throughout delivery.
- **No authentication or TLS is built in. Use only on a trusted network.** Anyone who can reach the service can send text and supported keys to your desktop.

## Development

The core server uses only the Python standard library. The optional `qrcode` package renders the startup QR code; Node.js is needed only for service-worker tests.

```bash
python3 -m unittest -v
node --test test_sw.mjs
```

Input tests mock desktop commands and do not type into your apps. macOS tests verify backend selection, clipboard handling, key modifiers, and permission-error reporting; they do not replace a real Mac smoke test. Increment the cache version in `sw.js` when changing cached resources.

## License

[MIT](LICENSE).
