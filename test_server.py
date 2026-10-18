import http.client
import io
import json
import subprocess
import struct
import sys
import threading
import time
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import server
from util import lan_address
from util import terminal_qr


class NetworkAddressTests(unittest.TestCase):
    def test_route_selected_address_is_returned_and_socket_is_closed(self):
        with patch.object(lan_address.socket, 'socket') as make_socket:
            probe = make_socket.return_value
            probe.getsockname.return_value = ('192.168.10.42', 49152)
            self.assertEqual(lan_address.lan_ipv4_address(), '192.168.10.42')
        make_socket.assert_called_once_with(
            lan_address.socket.AF_INET, lan_address.socket.SOCK_DGRAM)
        probe.connect.assert_called_once_with(('192.0.2.1', 80))
        probe.close.assert_called_once_with()

    def test_hostname_fallback_skips_unusable_addresses(self):
        with patch.object(lan_address.socket, 'socket') as make_socket, \
             patch.object(lan_address.socket, 'gethostname', return_value='desktop'), \
             patch.object(
                 lan_address.socket, 'gethostbyname_ex',
                 return_value=('desktop', [], ['0.0.0.0', '127.0.0.1', '10.0.0.24']),
             ) as resolve:
            make_socket.return_value.connect.side_effect = OSError('no route')
            self.assertEqual(lan_address.lan_ipv4_address(), '10.0.0.24')
        resolve.assert_called_once_with('desktop')
        make_socket.return_value.close.assert_called_once_with()

    def test_unusable_or_failed_results_return_none(self):
        cases = [
            ('127.0.0.1', ['0.0.0.0', '127.0.0.1']),
            ('0.0.0.0', []),
        ]
        for route_address, fallback_addresses in cases:
            with self.subTest(route_address=route_address), \
                 patch.object(lan_address.socket, 'socket') as make_socket, \
                 patch.object(lan_address.socket, 'gethostname', return_value='desktop'), \
                 patch.object(
                     lan_address.socket, 'gethostbyname_ex',
                     return_value=('desktop', [], fallback_addresses),
                 ):
                make_socket.return_value.getsockname.return_value = (route_address, 49152)
                self.assertIsNone(lan_address.lan_ipv4_address())
        with patch.object(
                 lan_address.socket, 'socket', side_effect=OSError('unavailable')), \
             patch.object(
                 lan_address.socket, 'gethostname', side_effect=OSError('unavailable')):
            self.assertIsNone(lan_address.lan_ipv4_address())

    def render_banner(self, host, detected='192.168.1.25', qr_available=True):
        output = io.StringIO()
        with patch.object(server, 'lan_ipv4_address', return_value=detected) as detect, \
             patch.object(
                 server, 'print_terminal_qr', return_value=qr_available) as print_qr, \
             patch.object(server, 'get_backend', return_value='wtype'), \
             redirect_stdout(output):
            server.print_startup_banner(host, 8765, 'auto')
        return output.getvalue(), detect, print_qr

    def test_banner_advertises_detected_or_explicit_address(self):
        output, detect, print_qr = self.render_banner('0.0.0.0')
        self.assertIn('手机访问： http://192.168.1.25:8765', output)
        detect.assert_called_once_with()
        print_qr.assert_called_once_with('http://192.168.1.25:8765')

        output, detect, print_qr = self.render_banner('10.0.0.8')
        self.assertIn('流声 Liusheng 已启动： http://10.0.0.8:8765', output)
        self.assertIn('手机访问： http://10.0.0.8:8765', output)
        detect.assert_not_called()
        print_qr.assert_called_once_with('http://10.0.0.8:8765')

    def test_banner_handles_loopback_and_detection_failure(self):
        for host in ('127.0.0.1', 'localhost'):
            with self.subTest(host=host):
                output, detect, print_qr = self.render_banner(host)
                self.assertIn(f'手机访问： 不可用（服务仅监听 {host}）', output)
                detect.assert_not_called()
                print_qr.assert_not_called()

        output, detect, print_qr = self.render_banner('0.0.0.0', detected=None)
        self.assertIn('未检测到局域网地址', output)
        self.assertIn('hostname -I', output)
        detect.assert_called_once_with()
        print_qr.assert_not_called()

    def test_banner_silently_skips_unavailable_qr_renderer(self):
        output, _, print_qr = self.render_banner('0.0.0.0', qr_available=False)
        self.assertNotIn('手机扫码', output)
        self.assertNotIn('二维码不可用', output)
        print_qr.assert_called_once_with('http://192.168.1.25:8765')


class TerminalQrTests(unittest.TestCase):
    def test_qr_uses_terminal_mode_only_for_a_tty(self):
        qr = unittest.mock.Mock()
        module = types.SimpleNamespace(
            QRCode=unittest.mock.Mock(return_value=qr),
            constants=types.SimpleNamespace(ERROR_CORRECT_M=0),
            exceptions=types.SimpleNamespace(DataOverflowError=RuntimeError),
        )
        output = io.StringIO()
        with patch.dict(sys.modules, {'qrcode': module}):
            self.assertTrue(terminal_qr.print_terminal_qr('http://10.0.0.8:8765', output))
        module.QRCode.assert_called_once_with(error_correction=0, border=4)
        qr.add_data.assert_called_once_with('http://10.0.0.8:8765')
        qr.print_ascii.assert_called_once_with(out=output, tty=False)

    def test_missing_qr_package_is_nonfatal(self):
        with patch.dict(sys.modules, {'qrcode': None}):
            self.assertFalse(terminal_qr.print_terminal_qr('http://10.0.0.8:8765'))


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        platform = patch.object(server.sys, 'platform', 'linux')
        platform.start()
        self.addCleanup(platform.stop)

    def test_terminal_detection_uses_app_name_boundaries(self):
        for app in ('kitty', 'org.wezfurlong.wezterm', 'gnome-terminal-server', 'org.kde.konsole'):
            self.assertEqual(server.paste_shortcut(app, 'auto'), 'terminal')
        for app in ('jetbrains-studio', 'org.gnome.TextEditor', 'firefox', 'code'):
            self.assertEqual(server.paste_shortcut(app, 'auto'), 'normal')

    def test_background_output_does_not_delay_command(self):
        command = "import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)'])"
        started = time.monotonic()
        server.run_command([sys.executable, '-c', command])
        self.assertLess(time.monotonic() - started, 1.5)

    def test_command_failure_includes_detail(self):
        with self.assertRaisesRegex(RuntimeError, 'probe error'):
            server.run_command([sys.executable, '-c', "import sys; sys.exit('probe error')"])

    def test_invalid_text_rejected_before_clipboard(self):
        for text in ('', 'a' * (server.MAX_TEXT + 1), '\ud800', '\x00'):
            with self.subTest(text=repr(text[:20])):
                with self.assertRaises(ValueError), patch.object(server, 'run_command') as run:
                    server.deliver(text, 'auto', 'auto')
                run.assert_not_called()

    def test_delivery_uses_terminal_shortcut_and_plain_text(self):
        with patch.object(server.shutil, 'which', side_effect=lambda name: '/bin/' + name), \
             patch.object(server, 'focused_window', return_value={'id': 1, 'app_id': 'kitty'}), \
             patch.object(server, 'run_command') as run, \
             patch.object(server, 'emit_paste') as emit:
            result = server.deliver('你好', 'auto', 'auto')
        run.assert_called_once_with(['wl-copy', '--type', 'text/plain;charset=utf-8'], input_data='你好')
        emit.assert_called_once_with('wtype', 'terminal')
        self.assertTrue(result['ok'])

    def test_key_delivery_on_both_backends_without_clipboard(self):
        commands = {
            ('wtype', 'enter'): ['wtype', '-k', 'Return'],
            ('wtype', 'ctrl_enter'): ['wtype', '-M', 'ctrl', '-k', 'Return', '-m', 'ctrl'],
            ('ydotool', 'enter'): ['ydotool', 'key', '28:1', '28:0'],
            ('ydotool', 'ctrl_enter'): ['ydotool', 'key', '29:1', '28:1', '28:0', '29:0'],
        }
        for (backend, key), command in commands.items():
            with self.subTest(backend=backend, key=key), \
                 patch.object(server.shutil, 'which', side_effect=lambda name: '/bin/' + name if name == backend else None), \
                 patch.object(server, 'focused_window', return_value={'id': 1}), \
                 patch.object(server, 'run_command') as run:
                result = server.deliver_key(key, backend)
                self.assertEqual(result['target'], {'id': 1})
                run.assert_called_once_with(command)

    def test_text_is_pasted_before_key_and_failure_stops_submission(self):
        for key in ('enter', 'ctrl_enter'):
            with self.subTest(key=key), \
                 patch.object(server.shutil, 'which', return_value='/bin/tool'), \
                 patch.object(server, 'focused_window', return_value={'id': 1, 'app_id': 'kitty'}), \
                 patch.object(server, 'run_command') as run, \
                 patch.object(server.time, 'sleep'):
                server.deliver_key(key, 'wtype', '你好')
                self.assertEqual(run.call_args_list[0].args[0][0], 'wl-copy')
                self.assertEqual(run.call_args_list[0].kwargs['input_data'], '你好')
                self.assertIn('shift', run.call_args_list[1].args[0])
                self.assertIn('Return', run.call_args_list[2].args[0])
                self.assertEqual(len(run.call_args_list), 3)
                run.reset_mock()
                with patch.object(server, 'emit_paste', side_effect=RuntimeError('paste failed')):
                    with self.assertRaises(RuntimeError):
                        server.deliver_key(key, 'wtype', '你好')
                run.assert_called_once()

    def test_key_validation_and_failures_do_not_send_again(self):
        for key in (None, '', 'tab', [], {}):
            with self.subTest(key=key), patch.object(server, 'run_command') as run:
                with self.assertRaises(ValueError):
                    server.deliver_key(key, 'auto')
                run.assert_not_called()
        with patch.object(server.shutil, 'which', return_value=None):
            with self.assertRaises(RuntimeError):
                server.deliver_key('enter', 'auto')
        with patch.object(server.shutil, 'which', return_value='/bin/tool'), \
             patch.object(server, 'focused_window', return_value=None), \
             patch.object(server, 'run_command', side_effect=RuntimeError('failed')) as run:
            with self.assertRaises(RuntimeError):
                server.deliver_key('ctrl_enter', 'auto')
            run.assert_called_once()

    def test_failed_paste_is_not_retried(self):
        with patch.object(server.shutil, 'which', return_value='/bin/tool'), \
             patch.object(server, 'focused_window', return_value=None), \
             patch.object(server, 'run_command'), \
             patch.object(server, 'emit_paste', side_effect=RuntimeError('failed')) as emit:
            with self.assertRaises(RuntimeError):
                server.deliver('hello', 'auto', 'auto')
        emit.assert_called_once()


class MacOSTests(unittest.TestCase):
    def setUp(self):
        platform = patch.object(server.sys, 'platform', 'darwin')
        platform.start()
        self.addCleanup(platform.stop)

    def test_backend_detection_and_missing_native_tool(self):
        with patch.object(server.shutil, 'which', return_value='/usr/bin/tool'):
            self.assertEqual(server.get_backend('auto'), 'macos')
            self.assertEqual(server.get_backend('macos'), 'macos')
            self.assertIsNone(server.get_backend('wtype'))
        with patch.object(server.shutil, 'which', side_effect=lambda tool: '/bin/tool' if tool == 'wtype' else None):
            self.assertIsNone(server.get_backend('auto'))
        self.assertEqual(server.clipboard_tool(), 'pbcopy')
        with patch.object(server.sys, 'platform', 'linux'):
            self.assertIsNone(server.get_backend('macos'))

    def test_unicode_text_only_enters_clipboard_not_script(self):
        text = '你好 "quoted"\n\\path\n$(touch /tmp/example)'
        with patch.object(server.shutil, 'which', return_value='/usr/bin/tool'), \
             patch.object(server, 'focused_window', return_value={'id': 42, 'app_id': 'com.apple.Terminal'}), \
             patch.object(server, 'run_command') as run, \
             patch.object(server.time, 'sleep'):
            result = server.deliver_key('ctrl_enter', 'auto', text)
        self.assertEqual(result['backend'], 'macos')
        self.assertEqual(result['paste_mode'], 'normal')
        self.assertEqual(run.call_args_list[0].args[0], ['pbcopy'])
        self.assertEqual(run.call_args_list[0].kwargs, {'input_data': text})
        self.assertEqual(run.call_args_list[1].args[0], [
            'osascript', '-e', 'tell application "System Events" to key code 9 using command down'])
        self.assertEqual(run.call_args_list[2].args[0], [
            'osascript', '-e', 'tell application "System Events" to key code 36 using control down'])
        self.assertEqual(len(run.call_args_list), 3)

    def test_standalone_keys_need_no_clipboard_and_keep_control_semantics(self):
        for key, action in [('enter', 'key code 36'), ('ctrl_enter', 'key code 36 using control down')]:
            with self.subTest(key=key), \
                 patch.object(server.shutil, 'which', side_effect=lambda name: '/usr/bin/osascript' if name == 'osascript' else None), \
                 patch.object(server, 'focused_window', return_value=None), \
                 patch.object(server, 'run_command') as run:
                server.deliver_key(key, 'auto')
                run.assert_called_once_with(['osascript', '-e', f'tell application "System Events" to {action}'])

    def test_missing_clipboard_stops_before_input(self):
        with patch.object(server.shutil, 'which', side_effect=lambda name: None if name == 'pbcopy' else '/usr/bin/tool'), \
             patch.object(server, 'run_command') as run:
            with self.assertRaisesRegex(RuntimeError, 'pbcopy'):
                server.deliver_key('enter', 'auto', '你好')
            run.assert_not_called()

    def test_pbcopy_uses_utf8_even_with_legacy_locale(self):
        with patch.dict(server.os.environ, {'LC_ALL': 'C'}), \
             patch.object(server.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            server.run_command(['pbcopy'], input_data='你好 😀')
            self.assertEqual(run.call_args.kwargs['env']['LC_ALL'], 'en_US.UTF-8')
            self.assertEqual(run.call_args.kwargs['encoding'], 'utf-8')
            self.assertEqual(run.call_args.kwargs['input'], '你好 😀')

    def test_failed_return_after_paste_is_not_retried(self):
        with patch.object(server.shutil, 'which', return_value='/usr/bin/tool'), \
             patch.object(server, 'focused_window', return_value=None), \
             patch.object(server.time, 'sleep'), \
             patch.object(server, 'run_command', side_effect=[None, None, RuntimeError('denied')]) as run:
            with self.assertRaisesRegex(RuntimeError, '已触发文字粘贴，但未确认回车结果'):
                server.deliver_key('enter', 'auto', '你好')
            self.assertEqual(run.call_count, 3)

    def test_permission_error_is_actionable_and_does_not_retry_or_submit(self):
        with patch.object(server.shutil, 'which', return_value='/usr/bin/tool'), \
             patch.object(server, 'focused_window', return_value=None), \
             patch.object(server, 'run_command', side_effect=[None, RuntimeError('not authorized (-1743)')]) as run:
            with self.assertRaisesRegex(RuntimeError, '辅助功能.*自动化'):
                server.deliver_key('enter', 'auto', 'hello')
            self.assertEqual(run.call_count, 2)

    def test_frontmost_app_uses_json_and_failure_is_optional(self):
        target = {'id': 42, 'app_id': 'com.apple.Terminal', 'title': 'Terminal "test"\n窗口'}
        with patch.object(server.shutil, 'which', return_value='/usr/bin/osascript'), \
             patch.object(server.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(target))) as run:
            self.assertEqual(server.focused_window(), target)
            self.assertEqual(run.call_args.args[0][:3], ['osascript', '-l', 'JavaScript'])
            self.assertIn('NSWorkspace', run.call_args.args[0][-1])
        with patch.object(server.shutil, 'which', return_value='/usr/bin/osascript'), \
             patch.object(server.subprocess, 'run', side_effect=subprocess.TimeoutExpired('osascript', 2)):
            self.assertIsNone(server.focused_window())


class HttpTests(unittest.TestCase):
    def setUp(self):
        platform = patch.object(server.sys, 'platform', 'linux')
        platform.start()
        self.addCleanup(platform.stop)

    def test_routes_and_input_validation(self):
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        httpd.backend = 'auto'
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        try:
            conn = http.client.HTTPConnection(*httpd.server_address, timeout=3)
            conn.request('GET', '/')
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn('流声', response.read().decode())
            for path, (filename, content_type) in server.STATIC_FILES.items():
                with self.subTest(path=path):
                    conn.request('GET', path + '?pwa-test=1')
                    response = conn.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.getheader('Content-Type'), content_type)
                    self.assertEqual(response.read(), (server.ROOT / filename).read_bytes())
            manifest = json.loads((server.ROOT / 'manifest.webmanifest').read_text())
            self.assertEqual(manifest['display'], 'standalone')
            for icon in manifest['icons']:
                png = (server.ROOT / icon['src'].lstrip('/')).read_bytes()
                self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
                dimensions = struct.unpack('>II', png[16:24])
                self.assertEqual('x'.join(map(str, dimensions)), icon['sizes'])
            conn.request('GET', '/api/status')
            response = conn.getresponse()
            self.assertEqual(response.getheader('Cache-Control'), 'no-store')
            self.assertTrue(json.loads(response.read())['ok'])
            with patch.object(server.sys, 'platform', 'darwin'), \
                 patch.object(server, 'focused_window', return_value=None), \
                 patch.object(server.shutil, 'which', side_effect=lambda tool: '/usr/bin/' + tool if tool in ('osascript', 'pbcopy') else None):
                conn.request('GET', '/api/status')
                response = conn.getresponse()
                data = json.loads(response.read())
                self.assertEqual(data['backend'], 'macos')
                self.assertTrue(data['clipboard'])
            for payload in ({'text': ''}, {'text': '\ud800'}, {'text': '\x00'}, [], {'text': 'hi', 'paste_mode': []}):
                conn.request('POST', '/api/send', json.dumps(payload))
                response = conn.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
            with patch.object(server, 'deliver', return_value={'ok': True}) as deliver:
                conn.request('POST', '/api/send', json.dumps({'text': '你好'}))
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertTrue(json.loads(response.read())['ok'])
                deliver.assert_called_once_with('你好', 'auto', 'auto')
            for payload in ({}, {'key': 'tab'}, {'key': []}, {'key': 'enter', 'text': []}, {'key': 'enter', 'text': '\x00'}, []):
                conn.request('POST', '/api/key', json.dumps(payload))
                response = conn.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
            for key in ('enter', 'ctrl_enter'):
                with patch.object(server, 'deliver_key', return_value={'ok': True}) as deliver_key:
                    conn.request('POST', '/api/key', json.dumps({'key': key}))
                    response = conn.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertTrue(json.loads(response.read())['ok'])
                    deliver_key.assert_called_once_with(key, 'auto', '')
            with patch.object(server, 'deliver_key', return_value={'ok': True}) as deliver_key:
                conn.request('POST', '/api/key', json.dumps({'key': 'enter', 'text': '你好'}))
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                deliver_key.assert_called_once_with('enter', 'auto', '你好')
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join()


if __name__ == '__main__':
    unittest.main()
