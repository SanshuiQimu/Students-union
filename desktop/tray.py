# -*- coding: utf-8 -*-
"""
系统托盘模块
=================================================
基于 QSystemTrayIcon 实现 Windows 系统托盘：

  - 托盘图标常驻，右键菜单（显示窗口 / 连接状态 / 设置 / 退出）
  - 左键单击切换主窗口显示/隐藏
  - 实时显示连接状态（在线/重连中/离线）
  - 通知点击信号（配合 Notifier 的气球通知点击）
  - 最小化到托盘（关闭窗口时不退出）
"""
import os
import logging

from PySide6.QtWidgets import (
    QSystemTrayIcon, QMenu, QApplication
)
from PySide6.QtGui import QIcon, QAction, QPixmap
from PySide6.QtCore import Signal, QObject

logger = logging.getLogger("desktop.tray")

# 项目根目录（用于定位图标）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ICON_PATH = os.path.join(_PROJECT_ROOT, "school-logo.png")


def load_app_icon():
    """加载应用图标，优先 png，不存在时用内置像素图。"""
    if os.path.exists(_ICON_PATH):
        icon = QIcon(_ICON_PATH)
        if not icon.isNull():
            logger.info(f"已加载托盘图标: {_ICON_PATH}")
            return icon
    # 内置兜底图标（蓝色方块）
    pm = QPixmap(32, 32)
    pm.fill()
    icon = QIcon(pm)
    logger.info("使用内置兜足图标")
    return icon


class TrayIcon(QObject):
    """
    系统托盘管理器。

    信号：
      show_window_requested()  —— 请求显示主窗口
      toggle_window_requested() —— 切换窗口显示/隐藏
      quit_requested()        —— 请求退出应用
      settings_requested()     —— 请求打开设置
      notification_clicked() —— 通知被点击
    """
    show_window_requested = Signal()
    toggle_window_requested = Signal()
    quit_requested = Signal()
    settings_requested = Signal()
    notification_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tray = QSystemTrayIcon(load_app_icon(), parent)
        self._tray.setToolTip("学生会人事管理系统")

        self._build_menu()
        self._tray.activated.connect(self._on_activated)
        self._tray.messageClicked.connect(self.notification_clicked)

        self._conn_state = "disconnected"

    def _build_menu(self):
        menu = QMenu()

        # 显示主窗口
        act_show = QAction("显示主窗口", menu)
        act_show.triggered.connect(self.show_window_requested)
        menu.addAction(act_show)

        menu.addSeparator()

        # 连接状态（只读显示）
        self._act_status = QAction("连接状态: 未知", menu)
        self._act_status.setEnabled(False)
        menu.addAction(self._act_status)

        # 服务器地址（只读显示）
        self._act_server = QAction("服务器: 未设置", menu)
        self._act_server.setEnabled(False)
        menu.addAction(self._act_server)

        menu.addSeparator()

        # 设置
        act_settings = QAction("设置...", menu)
        act_settings.triggered.connect(self.settings_requested)
        menu.addAction(act_settings)

        menu.addSeparator()

        # 退出
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.quit_requested)
        menu.addAction(act_quit)

        self._tray.setContextMenu(menu)

    # -------------------- 生命周期 --------------------
    def show(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("系统托盘不可用")
            return
        self._tray.show()
        logger.info("系统托盘已显示")

    def hide(self):
        self._tray.hide()

    def is_visible(self):
        return self._tray.isVisible()

    # -------------------- 状态更新 --------------------
    def update_connection_state(self, state):
        """
        更新连接状态显示。
        :param state: "connected" | "reconnecting" | "offline"
        """
        self._conn_state = state
        labels = {
            "connected": "连接状态: 已连接",
            "reconnecting": "连接状态: 重连中...",
            "offline": "连接状态: 离线",
        }
        self._act_status.setText(labels.get(state, "连接状态: 未知"))

    def update_server_info(self, url, reachable):
        """更新服务器地址与可达性显示。"""
        short = url.replace("http://", "").replace("https://", "")
        status = "✓ 可达" if reachable else "✗ 不可达"
        self._act_server.setText(f"服务器: {short} ({status})")
        # 更新托盘提示
        self._tray.setToolTip(
            f"学生会人事管理系统\n{short}\n{status}"
        )

    def show_message(self, title, body, msecs=5000):
        """显示气球通知（回退方案）。"""
        try:
            self._tray.showMessage(
                title, body, QSystemTrayIcon.Information, msecs
            )
        except Exception as e:
            logger.warning(f"显示气球通知失败: {e}")

    # -------------------- 事件处理 --------------------
    def _on_activated(self, reason):
        """托盘图标激活处理。"""
        if reason == QSystemTrayIcon.Trigger:
            # 左键单击：切换窗口
            self.toggle_window_requested.emit()
        elif reason == QSystemTrayIcon.DoubleClick:
            self.show_window_requested.emit()
