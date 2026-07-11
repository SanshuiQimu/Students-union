# -*- coding: utf-8 -*-
"""
学生会人事管理系统 —— Windows 桌面端主程序
=================================================
基于 PySide6 实现，特性：
  1. 系统原生消息通知（Windows 通知中心 / 托盘气球）
  2. HTTP/HTTPS 联网层（超时、断线重连、网络状态监听）
  3. 系统托盘常驻、最小化到托盘
  4. 内嵌 Flask 后端（开箱即用），亦支持连接远程服务器
  5. 零侵入复用现有 index.html 前端

运行方式：
    pip install -r requirements.txt
    python main.py
"""
import sys
import os
import socket
import threading
import logging

# ---- 路径：把项目根目录加入 sys.path，以便内嵌启动 Flask 后端 ----
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
_DESKTOP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DESKTOP_DIR)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QVBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QCheckBox, QDialogButtonBox, QMessageBox,
    QLabel
)
from PySide6.QtCore import QUrl, QTimer, Qt
from PySide6.QtGui import QIcon, QCloseEvent
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineScript, QWebEngineProfile
)

import config
from network import HttpClient, NetworkMonitor, MessagePoller
from notifier import Notifier
from bridge import NativeBridge, INJECT_JS
from tray import TrayIcon, load_app_icon

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("desktop.main")


# ============================================================
# 工具函数
# ============================================================
def parse_url(url):
    """从 URL 解析 host、port，返回 (host, port)。"""
    from urllib.parse import urlparse
    p = urlparse(url)
    host = p.hostname or "127.0.0.1"
    port = p.port or (443 if p.scheme == "https" else 80)
    return host, port


def is_port_open(host, port, timeout=1.0):
    """检测端口是否开放（快速判断后端是否在运行）。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def start_embedded_server(port=5000):
    """
    在守护线程中启动内嵌 Flask 后端（复用项目根目录 main.py）。
    使用 importlib 按文件路径加载，避免与桌面端入口 main.py 同名冲突。
    使用 daemon=True，主进程退出时自动结束。
    """
    import importlib.util
    flask_main_path = os.path.join(_PROJECT_ROOT, "main.py")
    if not os.path.exists(flask_main_path):
        logger.error(f"未找到后端文件: {flask_main_path}")
        return False
    try:
        # 确保项目根目录在 sys.path 中（后端 main.py 依赖 flask 等模块）
        if _PROJECT_ROOT not in sys.path:
            sys.path.insert(0, _PROJECT_ROOT)
        os.environ.setdefault("PORT", str(port))
        # 通过文件路径加载，规避桌面端入口同名冲突
        spec = importlib.util.spec_from_file_location(
            "hg_flask_backend", flask_main_path
        )
        flask_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(flask_module)
        flask_app = flask_module.app

        def _run():
            flask_app.run(
                host="127.0.0.1", port=port,
                debug=False, use_reloader=False, threaded=True,
            )

        t = threading.Thread(target=_run, name="embedded-flask", daemon=True)
        t.start()
        logger.info(f"内嵌 Flask 后端已启动 (127.0.0.1:{port})")
        return True
    except Exception as e:
        logger.error(f"启动内嵌后端失败: {e}")
        return False


# ============================================================
# 自定义 WebEnginePage：拦截 console 消息
# ============================================================
class DesktopWebPage(QWebEnginePage):
    """继承 QWebEnginePage，转发 console 消息给 NativeBridge。"""

    def __init__(self, profile, parent=None, bridge=None):
        super().__init__(profile, parent)
        self._bridge = bridge

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        # 先让 bridge 处理协议消息
        if self._bridge:
            self._bridge.handle_console_message(level, message, line_number, source_id)
            # 如果是协议消息，不再打印（减少日志噪音）


# ============================================================
# 设置对话框
# ============================================================
class SettingsDialog(QDialog):
    """桌面端设置对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(420)

        cfg = config.load()
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.server_input = QLineEdit(cfg.get("server_url", "http://127.0.0.1:5000"))
        form.addRow("服务器地址：", self.server_input)

        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(5, 300)
        self.poll_spin.setSuffix(" 秒")
        self.poll_spin.setValue(cfg.get("poll_interval", 15))
        form.addRow("消息轮询间隔：", self.poll_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(3, 60)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setValue(cfg.get("request_timeout", 10))
        form.addRow("请求超时：", self.timeout_spin)

        self.chk_notify = QCheckBox("启用桌面通知")
        self.chk_notify.setChecked(cfg.get("notification_enabled", True))
        form.addRow("", self.chk_notify)

        self.chk_sound = QCheckBox("通知声音")
        self.chk_sound.setChecked(cfg.get("sound_enabled", True))
        form.addRow("", self.chk_sound)

        self.chk_tray = QCheckBox("关闭窗口时最小化到托盘")
        self.chk_tray.setChecked(cfg.get("minimize_to_tray", True))
        form.addRow("", self.chk_tray)

        layout.addLayout(form)

        # 信息提示
        info = QLabel(
            f"配置文件位置：\n{config.config_path()}\n\n"
            "修改服务器地址后需点击「确定」并等待页面重新加载。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(info)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self):
        return {
            "server_url": self.server_input.text().strip(),
            "poll_interval": self.poll_spin.value(),
            "request_timeout": self.timeout_spin.value(),
            "notification_enabled": self.chk_notify.isChecked(),
            "sound_enabled": self.chk_sound.isChecked(),
            "minimize_to_tray": self.chk_tray.isChecked(),
        }


# ============================================================
# 主窗口
# ============================================================
class MainWindow(QMainWindow):
    """
    桌面端主窗口，内嵌 QWebEngineView 渲染现有 index.html。
    """

    def __init__(self, server_url, bridge):
        super().__init__()
        self._server_url = server_url
        self._bridge = bridge

        self.setWindowTitle("学生会人事管理系统")
        self.setWindowIcon(load_app_icon())
        self.resize(1100, 760)
        self.setMinimumSize(900, 600)

        # ---- WebEngine 配置 ----
        profile = QWebEngineProfile.defaultProfile()
        # 允许持久化存储（localStorage）
        profile.setPersistentCookiesPolicy(
            profile.PersistentCookiesPolicy.AllowPersistentCookies
        )
        from PySide6.QtWebEngineCore import QWebEngineSettings
        s = profile.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        # ---- 页面 ----
        self._page = DesktopWebPage(profile, self, bridge)
        # 注入桥接 JS（每次导航自动注入，DocumentCreation 最早）
        inject_script = QWebEngineScript()
        inject_script.setName("android_native_bridge")
        inject_script.setSourceCode(INJECT_JS)
        inject_script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        inject_script.setWorldId(QWebEngineScript.MainWorld)
        inject_script.setRunsOnSubFrames(False)
        self._page.scripts().insert(inject_script)

        # ---- 视图 ----
        self._view = QWebEngineView(self)
        self._view.setPage(self._page)
        self.setCentralWidget(self._view)

        self._load_url = server_url
        self._load_attempts = 0

    # -------------------- 页面加载 --------------------
    def load_server(self, url=None):
        """加载服务器页面。"""
        target = url or self._load_url
        self._load_url = target
        logger.info(f"加载页面: {target}")
        self._view.setUrl(QUrl(target))

    def reload(self):
        self._view.reload()

    def run_js(self, code, callback=None):
        """在页面执行 JS。"""
        self._page.runJavaScript(code, 0, callback) if callback else \
            self._page.runJavaScript(code)

    # -------------------- 窗口行为 --------------------
    def closeEvent(self, event: QCloseEvent):
        """关闭窗口时，按配置决定最小化到托盘或退出。"""
        if config.get("minimize_to_tray", True):
            # 最小化到托盘
            event.ignore()
            self.hide()
            logger.info("窗口已最小化到托盘")
        else:
            event.accept()


# ============================================================
# 应用控制器
# ============================================================
class AppController:
    """整合所有模块的控制器。"""

    def __init__(self):
        self.app = None
        self.window = None
        self.bridge = None
        self.notifier = None
        self.monitor = None
        self.poller = None
        self.tray = None
        self._current_user = ""

    def run(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("学生会人事管理系统")
        self.app.setOrganizationName("HGStudentsUnion")
        self.app.setWindowIcon(load_app_icon())
        # 退出时不要在最后一个窗口关闭就退出（托盘常驻）
        self.app.setQuitOnLastWindowClosed(False)

        cfg = config.load()
        server_url = cfg.get("server_url", "http://127.0.0.1:5000")

        # ---- 自动探测 / 启动内嵌后端 ----
        self._ensure_backend(server_url)

        # ---- 创建模块 ----
        self.bridge = NativeBridge()
        self.window = MainWindow(server_url, self.bridge)
        self.notifier = Notifier()  # tray 注入后再设置
        self.monitor = NetworkMonitor(
            parent=None, server_url=server_url, ping_interval=30
        )
        self.poller = MessagePoller(
            parent=None, server_url=server_url, username=""
        )
        self.tray = TrayIcon()
        self.notifier._tray = self.tray._tray  # 回退气球通知需要

        # ---- 连接信号 ----
        self._connect_signals()

        # ---- 启动 ----
        self.tray.show()
        self.window.show()
        # 延迟加载页面，等待内嵌后端就绪
        QTimer.singleShot(1500, lambda: self.window.load_server(server_url))

        # 如果内嵌后端正在启动，给额外等待
        if self._embedded_starting:
            QTimer.singleShot(3000, self.window.reload)

        sys.exit(self.app.exec())

    # -------------------- 后端探测 --------------------
    def _ensure_backend(self, server_url):
        """如果指向本地且端口未开放，启动内嵌 Flask 后端。"""
        self._embedded_starting = False
        host, port = parse_url(server_url)
        if host in ("127.0.0.1", "localhost"):
            if not is_port_open(host, port, timeout=1.0):
                logger.info("本地后端未运行，启动内嵌 Flask...")
                if start_embedded_server(port):
                    self._embedded_starting = True
                    # 等待后端就绪
                    self._wait_for_port(host, port, timeout=10)

    def _wait_for_port(self, host, port, timeout=10):
        """轮询等待端口开放（阻塞但限时）。"""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            if is_port_open(host, port, timeout=0.5):
                logger.info(f"内嵌后端已就绪 ({host}:{port})")
                return True
            time.sleep(0.3)
        logger.warning("等待后端就绪超时")
        return False

    # -------------------- 信号连接 --------------------
    def _connect_signals(self):
        # 桥接信号
        self.bridge.notify_requested.connect(self._on_notify_requested)
        self.bridge.user_changed.connect(self._on_user_changed)
        self.bridge.user_logged_out.connect(self._on_user_logout)
        self.bridge.stop_polling_requested.connect(self.poller.stop)
        self.bridge.visibility_changed.connect(self._on_visibility_changed)

        # 网络监听信号
        self.monitor.online_changed.connect(self._on_online_changed)
        self.monitor.server_reachable.connect(self._on_server_reachable)

        # 消息轮询信号
        self.poller.new_messages.connect(self._on_new_messages)
        self.poller.connection_state_changed.connect(
            self.tray.update_connection_state
        )

        # 托盘信号
        self.tray.show_window_requested.connect(self._show_window)
        self.tray.toggle_window_requested.connect(self._toggle_window)
        self.tray.quit_requested.connect(self._quit)
        self.tray.settings_requested.connect(self._open_settings)
        self.tray.notification_clicked.connect(self._show_window)

    # -------------------- 信号处理 --------------------
    def _on_notify_requested(self, title, body):
        """前端请求弹通知 → 转发到 Notifier。"""
        self.notifier.show(title, body, on_click=self._show_window)

    def _on_user_changed(self, username):
        """登录用户变更 → 启动后台消息轮询。"""
        self._current_user = username
        self.poller.set_username(username)
        self.poller.start()
        logger.info(f"后台消息轮询已启动，用户: {username}")

    def _on_user_logout(self):
        """用户登出 → 停止后台轮询。"""
        self._current_user = ""
        self.poller.stop()
        logger.info("后台消息轮询已停止")

    def _on_visibility_changed(self, visible):
        """页面可见性变化 → 窗口可见时前端轮询，隐藏时 Python 接管。"""
        if not visible and self._current_user:
            # 窗口隐藏，确保后台轮询运行
            if self.poller.get_state() != "connected":
                self.poller.start()

    def _on_online_changed(self, online):
        """系统网络状态变化。"""
        if not online:
            self.tray.show_message("网络已断开", "请检查网络连接")
        else:
            self.tray.show_message("网络已恢复", "正在重新连接服务器...")

    def _on_server_reachable(self, reachable):
        """后端可达性变化。"""
        cfg = config.load()
        self.tray.update_server_info(cfg.get("server_url", ""), reachable)
        if reachable:
            # 服务器恢复，重启轮询
            if self._current_user:
                self.poller.start()

    def _on_new_messages(self, messages):
        """检测到新消息 → 弹原生通知。"""
        self.notifier.show_messages(messages, on_click=self._show_window)

    # -------------------- 窗口控制 --------------------
    def _show_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        if self.window.isMinimized():
            self.window.showNormal()

    def _toggle_window(self):
        if self.window.isVisible():
            self.window.hide()
        else:
            self._show_window()

    # -------------------- 设置 --------------------
    def _open_settings(self):
        dlg = SettingsDialog(self.window)
        if dlg.exec() == QDialog.Accepted:
            values = dlg.get_values()
            old_url = config.get("server_url")
            config.save(values)
            # 应用新配置
            self.poller._poll_interval = values["poll_interval"] * 1000
            self.poller._max_backoff = config.get("reconnect_max_interval", 60) * 1000
            self.monitor.set_server_url(values["server_url"])
            self.poller.set_server_url(values["server_url"])

            # 服务器地址变更 → 重新探测并加载
            if values["server_url"] != old_url:
                QMessageBox.information(
                    self.window, "提示",
                    "服务器地址已更改，正在重新连接..."
                )
                self._ensure_backend(values["server_url"])
                QTimer.singleShot(1000, lambda: self.window.load_server(
                    values["server_url"]
                ))

    # -------------------- 退出 --------------------
    def _quit(self):
        """退出应用。"""
        reply = QMessageBox.question(
            None, "确认退出",
            "确定要退出学生会人事管理系统吗？\n退出后将不再接收新消息通知。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            logger.info("应用退出")
            self.poller.stop()
            self.tray.hide()
            self.app.quit()


# ============================================================
# 入口
# ============================================================
def main():
    controller = AppController()
    controller.run()


if __name__ == "__main__":
    main()
