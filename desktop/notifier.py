# -*- coding: utf-8 -*-
"""
原生通知模块（轻量版，不依赖 PySide6）
=================================================
优先 win11toast（Windows 通知中心），回退 pystray 气球通知。
"""
import os
import time
import logging

logger = logging.getLogger("desktop.notifier")

_TOAST_AVAILABLE = False
try:
    from win11toast import toast
    _TOAST_AVAILABLE = True
    logger.info("win11toast 已加载")
except Exception as e:
    logger.info(f"win11toast 不可用: {e}")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ICON_PATH = os.path.join(_PROJECT_ROOT, "school-logo.png")
if not os.path.exists(_ICON_PATH):
    _ICON_PATH = None


class Notifier:
    """Windows 原生通知封装。"""

    def __init__(self, tray=None):
        self._tray = tray
        self._recent = {}
        self._click_handlers = {}

    def show(self, title, body="", on_click=None, duration="short"):
        cfg = {}
        try:
            cfg = config_load()
        except Exception:
            pass
        if not cfg.get("notification_enabled", True):
            return
        # 去重
        key = (title, (body or "")[:20])
        now = time.time()
        last = self._recent.get(key)
        if last and now - last < 5:
            return
        self._recent[key] = now
        if len(self._recent) > 50:
            self._recent = {k: v for k, v in self._recent.items() if now - v < 60}

        if _TOAST_AVAILABLE:
            self._show_toast(title, body, on_click, cfg)
        else:
            self._show_balloon(title, body)

    def _show_toast(self, title, body, on_click, cfg):
        try:
            from win11toast import toast
            kwargs = {
                "title": title,
                "body": body,
                "duration": duration if duration in ("short", "long") else "short",
            }
            if _ICON_PATH:
                kwargs["icon"] = _ICON_PATH
            if not cfg.get("sound_enabled", True):
                kwargs["audio"] = {"silent": "true"}
            if on_click:
                kwargs["on_click"] = lambda *a: on_click()
            toast(**kwargs)
            logger.info(f"[Toast] {title}")
        except Exception as e:
            logger.warning(f"Toast 失败，回退气球: {e}")
            self._show_balloon(title, body)

    def _show_balloon(self, title, body):
        if self._tray:
            try:
                # pystray 的 notify 方法
                self._tray.notify(title, body)
            except Exception:
                pass

    def show_messages(self, messages, on_click=None):
        if not messages:
            return
        if len(messages) == 1:
            m = messages[0]
            self.show(m.get("title", "新消息"), m.get("body", ""), on_click)
        else:
            self.show(
                f"收到 {len(messages)} 条新消息",
                messages[-1].get("title", "点击查看"),
                on_click,
            )


def config_load():
    import config
    return config.load()
