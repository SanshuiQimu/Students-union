# -*- coding: utf-8 -*-
"""
学生会人事管理系统 —— Windows 桌面端主程序（轻量版）
基于 pywebview（系统 WebView2）+ pystray + requests。
剥离 PySide6/QtWebEngine，体积降至 ~40MB。
"""
import sys, os, socket, threading, importlib.util, logging

def _is_frozen():
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

if _is_frozen():
    _BASE_DIR = sys._MEIPASS
    _PROJECT_ROOT = _BASE_DIR
else:
    _DESKTOP_DIR = os.path.dirname(os.path.abspath(__file__))
    _PROJECT_ROOT = os.path.dirname(_DESKTOP_DIR)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if not _is_frozen() else _BASE_DIR)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("desktop.main")

import config
from network import HttpClient, MessagePoller
from notifier import Notifier
import webview
import pystray
from PIL import Image

_window = None
_tray = None
_notifier = None
_poller = None
_current_user = ""
_server_url = ""

def parse_url(url):
    from urllib.parse import urlparse
    p = urlparse(url)
    return p.hostname or "127.0.0.1", p.port or 80

def is_port_open(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False

def start_embedded_server(port=5000):
    flask_path = os.path.join(_PROJECT_ROOT, "main.py")
    if not os.path.exists(flask_path):
        return False
    try:
        if _PROJECT_ROOT not in sys.path:
            sys.path.insert(0, _PROJECT_ROOT)
        os.environ.setdefault("PORT", str(port))
        spec = importlib.util.spec_from_file_location("hg_flask_backend", flask_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        def _run():
            mod.app.run(host="127.0.0.1", port=port, debug=False,
                        use_reloader=False, threaded=True)
        threading.Thread(target=_run, name="embedded-flask", daemon=True).start()
        logger.info(f"内嵌 Flask 已启动 (127.0.0.1:{port})")
        return True
    except Exception as e:
        logger.error(f"启动后端失败: {e}")
        return False

def ensure_backend(server_url):
    host, port = parse_url(server_url)
    if host in ("127.0.0.1", "localhost"):
        if not is_port_open(host, port, 1.0):
            start_embedded_server(port)
            import time
            for _ in range(30):
                if is_port_open(host, port, 0.5):
                    break
                time.sleep(0.3)
    return True

def show_window():
    if _window:
        _window.show()
        _window.restore()

def toggle_window():
    if _window:
        if _window.visible:
            _window.hide()
        else:
            show_window()

class JsApi:
    def show_notification(self, title, body=""):
        if _notifier:
            _notifier.show(title, body, on_click=show_window)
        return True
    def stop_background_polling(self):
        if _poller:
            _poller.stop()
        return True
    def report_user(self, username):
        global _current_user
        _current_user = username
        if _poller:
            _poller.set_username(username)
            _poller.set_server_url(_server_url)
            _poller.start()
        logger.info(f"用户登录: {username}，轮询已启动")
        return True
    def report_logout(self):
        global _current_user
        _current_user = ""
        if _poller:
            _poller.stop()
        return True

INJECT_JS = r"""
(function(){
    if(window.__hg_native_injected) return;
    window.__hg_native_injected = true;
    window.AndroidNative = {
        showNotification: function(title, body){
            window.pywebview.api.show_notification(title||'', body||'');
        },
        onAppVisibilityChanged: function(hidden){},
        stopBackgroundPolling: function(){
            window.pywebview.api.stop_background_polling();
        }
    };
    var _lastUser = null;
    setInterval(function(){
        try{
            var u = (window.currentUser && window.currentUser.name) || '';
            if(u && u !== _lastUser){ _lastUser = u; window.pywebview.api.report_user(u); }
            else if(!u && _lastUser){ _lastUser = null; window.pywebview.api.report_logout(); }
        }catch(e){}
    }, 2000);
})();
"""

def create_tray_icon():
    icon_path = os.path.join(_PROJECT_ROOT, "school-logo.png")
    if not os.path.exists(icon_path):
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "school-logo.png")
    try:
        image = Image.open(icon_path) if os.path.exists(icon_path) \
            else Image.new('RGB', (64, 64), color=(0, 120, 215))
    except Exception:
        image = Image.new('RGB', (64, 64), color=(0, 120, 215))
    menu = pystray.Menu(
        pystray.MenuItem("显示主窗口", lambda: show_window(), default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", lambda: quit_app()),
    )
    return pystray.Icon("HGStudentsUnion", image, "学生会人事管理系统", menu)

def quit_app():
    if _poller:
        _poller.stop()
    if _tray:
        _tray.stop()
    if _window:
        _window.destroy()
    os._exit(0)

def on_loaded():
    _window.evaluate_js(INJECT_JS)

def on_closing():
    if config.get("minimize_to_tray", True):
        _window.hide()
        if _tray:
            try: _tray.notify("学生会人事管理系统", "已最小化到托盘")
            except: pass
        return False
    return True

def on_new_messages(messages):
    if _notifier:
        _notifier.show_messages(messages, on_click=show_window)

def main():
    global _window, _tray, _notifier, _poller, _server_url
    cfg = config.load()
    _server_url = cfg.get("server_url", "http://127.0.0.1:5000")
    ensure_backend(_server_url)
    _notifier = Notifier()
    _poller = MessagePoller(server_url=_server_url, username="")
    _poller.new_messages = on_new_messages
    # 托盘（后台线程）
    _tray = create_tray_icon()
    _notifier._tray = _tray
    threading.Thread(target=_tray.run, daemon=True).start()
    # 窗口
    api = JsApi()
    _window = webview.create_window(
        "学生会人事管理系统", _server_url, js_api=api,
        width=1100, height=760, min_size=(900, 600),
        text_select=False,
    )
    _window.events.loaded += on_loaded
    _window.events.closing += on_closing
    # 启动（阻塞），使用 edgechromium 引擎（WebView2）
    webview.start(gui='edgechromium', debug=False)

if __name__ == "__main__":
    main()
