# -*- coding: utf-8 -*-
"""
原生通知模块
=================================================
实现 Windows 系统原生级别的消息通知：

  1. 优先使用 win11toast —— 调用 Windows 通知中心（Toast Notification），
     通知会进入操作中心，支持交互按钮、应用图标、声音；
  2. 回退使用 QSystemTrayIcon.showMessage —— Qt 内置气球通知，
     也会在系统通知区域显示；
  3. 提供 on_click 回调，点击通知可唤起主窗口。

确保通知在系统托盘与通知中心均能正常显示与留存。
"""
import os
import logging
import time

logger = logging.getLogger("desktop.notifier")

# 尝试加载 win11toast（Windows 10/11 原生 Toast 通知）
_TOAST_AVAILABLE = False
try:
    from win11toast import toast  # noqa
    _TOAST_AVAILABLE = True
    logger.info("win11toast 已加载，将使用 Windows 通知中心原生通知")
except Exception as e:
    logger.info(f"win11toast 不可用({e})，将回退 QSystemTrayIcon 气球通知")

# 应用图标路径（复用项目根目录的 school-logo.png）
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ICON_PATH = os.path.join(_APP_DIR, "school-logo.png")
if not os.path.exists(_ICON_PATH):
    _ICON_PATH = None


class Notifier:
    """
    Windows 原生通知封装。

    用法::

        notifier = Notifier(tray_icon)   # tray_icon 可为 None
        notifier.show("新消息", "张三: 请尽快处理", on_click=lambda: show_window())
    """

    def __init__(self, tray_icon=None):
        # QSystemTrayIcon 实例（回退方案需要）
        self._tray = tray_icon
        # 点击回调
        self._click_handlers = {}
        # 通知去重：(title, body[:20]) -> timestamp，5s 内不重复
        self._recent = {}

    def show(self, title, body="", on_click=None, duration="short"):
        """
        显示一条桌面通知。

        :param title:     通知标题
        :param body:       通知正文
        :param on_click:   点击回调（无参函数）
        :param duration:   "short"(~7s) 或 "long"(~25s)
        """
        from config import load
        cfg = load()
        if not cfg.get("notification_enabled", True):
            logger.debug("通知已禁用，跳过")
            return

        # 去重：5s 内相同标题+正文不重复弹
        key = (title, (body or "")[:20])
        now = time.time()
        last = self._recent.get(key)
        if last and now - last < 5:
            logger.debug(f"通知去重，跳过: {title}")
            return
        self._recent[key] = now
        # 清理过期记录
        if len(self._recent) > 50:
            self._recent = {k: v for k, v in self._recent.items() if now - v < 60}

        if _TOAST_AVAILABLE:
            self._show_toast(title, body, on_click, cfg)
        else:
            self._show_balloon(title, body, on_click)

    # -------------------- 原生 Toast（win11toast）--------------------
    def _show_toast(self, title, body, on_click, cfg):
        try:
            from win11toast import toast
            # 点击交互
            click_arg = "click"
            if on_click:
                self._click_handlers[click_arg] = on_click

            args = {
                "title": title,
                "body": body,
                "icon": _ICON_PATH if _ICON_PATH else None,
                "duration": duration_to_str(duration),
                "on_click": self._handle_toast_click,
                "argument": click_arg,
            }
            # 声音
            if not cfg.get("sound_enabled", True):
                args["audio"] = {"silent": "true"}

            toast(**{k: v for k, v in args.items() if v is not None})
            logger.info(f"[Toast] {title}: {body[:40]}")
        except Exception as e:
            logger.warning(f"Toast 通知失败，回退气球: {e}")
            self._show_balloon(title, body, on_click)

    def _handle_toast_click(self, args=None):
        """win11toast 点击回调。args 可能是 activation 参数。"""
        try:
            key = "click"
            handler = self._click_handlers.pop(key, None)
            if handler:
                handler()
        except Exception as e:
            logger.debug(f"处理 Toast 点击异常: {e}")

    # -------------------- 回退：QSystemTrayIcon 气球 --------------------
    def _show_balloon(self, title, body, on_click):
        if self._tray is None:
            logger.debug("无托盘图标，无法显示气球通知")
            return
        try:
            from PySide6.QtWidgets import QSystemTrayIcon
            if not self._tray.isVisible():
                self._tray.show()
            # 存储点击回调
            import time
            key = str(time.time())
            if on_click:
                self._click_handlers[key] = on_click
            # QSystemTrayIcon 的 messageClicked 信号在主入口连接处理
            self._tray.showMessage(
                title,
                body,
                QSystemTrayIcon.Information,
                5000,
            )
            logger.info(f"[Balloon] {title}: {body[:40]}")
        except Exception as e:
            logger.error(f"气球通知失败: {e}")

    # -------------------- 批量通知 --------------------
    def show_messages(self, messages, on_click=None):
        """
        批量展示消息通知。单条直接展示标题正文；多条合并为一条摘要。
        :param messages: 消息字典列表 [{title, body, ...}, ...]
        """
        if not messages:
            return
        if len(messages) == 1:
            m = messages[0]
            self.show(
                title=m.get("title", "新消息"),
                body=m.get("body", ""),
                on_click=on_click,
            )
        else:
            last = messages[-1]
            self.show(
                title=f"收到 {len(messages)} 条新消息",
                body=last.get("title", "点击查看详情"),
                on_click=on_click,
            )


def duration_to_str(duration):
    """将 duration 参数转为 win11toast 接受的字符串。"""
    if duration in ("short", "long"):
        return duration
    return "short"
