# -*- coding: utf-8 -*-
"""
JS <-> Python 桥接模块
=================================================
现有前端 index.html 通过 `window.AndroidNative` 接口调用原生功能：

  - AndroidNative.showNotification(title, body)     // 弹原生通知
  - AndroidNative.onAppVisibilityChanged(hidden)    // 通知原生可见性
  - AndroidNative.stopBackgroundPolling()           // 停止后台轮询

本模块通过「注入 JS + 拦截 console 协议消息」实现零侵入桥接，
前端代码完全无需修改。同时自动上报当前登录用户名，
驱动 Python 后台 MessagePoller。

协议格式（通过 console.log 传输，稳定可靠）：
  @@native:notify:<json>
  @@native:visibility:0|1
  @@native:stop_polling
  @@native:user:<username>
"""
import json as _json
import logging

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("desktop.bridge")

# 协议前缀
_PREFIX = "@@native:"

# 注入到页面的 JS 代码：定义 window.AndroidNative 对象并自动上报用户名
INJECT_JS = r"""
(function(){
    if(window.__hg_native_injected) return;
    window.__hg_native_injected = true;

    // 定义原生接口（兼容现有前端 window.AndroidNative 调用）
    window.AndroidNative = {
        showNotification: function(title, body){
            console.log('@@native:notify:' + JSON.stringify({title: title||'', body: body||''}));
        },
        onAppVisibilityChanged: function(hidden){
            console.log('@@native:visibility:' + (hidden ? '1' : '0'));
        },
        stopBackgroundPolling: function(){
            console.log('@@native:stop_polling');
        }
    };

    // 自动上报当前登录用户名，驱动 Python 后台轮询
    var _lastUser = null;
    setInterval(function(){
        try {
            var u = (window.currentUser && window.currentUser.name) || '';
            if(u && u !== _lastUser){
                _lastUser = u;
                console.log('@@native:user:' + u);
            } else if(!u && _lastUser){
                _lastUser = null;
                console.log('@@native:logout');
            }
        } catch(e){}
    }, 2000);
})();
"""


class NativeBridge(QObject):
    """
    原生桥接器：解析前端通过 console 发送的协议消息，转换为 Qt 信号。

    信号：
      notify_requested(str, str)   —— 标题, 正文（显示通知）
      visibility_changed(bool)      —— 窗口可见性
      stop_polling_requested()      —— 停止后台轮询
      user_changed(str)             —— 当前登录用户变更
      user_logged_out()             —— 用户登出
    """
    notify_requested = Signal(str, str)
    visibility_changed = Signal(bool)
    stop_polling_requested = Signal()
    user_changed = Signal(str)
    user_logged_out = Signal()

    def handle_console_message(self, level, message, line_number, source_id):
        """
        连接到 QWebEnginePage.javaScriptConsoleMessage 信号。
        解析 @@native: 协议消息。
        """
        if not message or not message.startswith(_PREFIX):
            return  # 普通日志，忽略

        payload = message[len(_PREFIX):]

        try:
            if payload.startswith("notify:"):
                data = _json.loads(payload[len("notify:"):])
                self.notify_requested.emit(
                    data.get("title", ""),
                    data.get("body", ""),
                )
            elif payload.startswith("visibility:"):
                hidden = payload[len("visibility:")].strip() == "1"
                self.visibility_changed.emit(not hidden)
            elif payload == "stop_polling":
                self.stop_polling_requested.emit()
            elif payload.startswith("user:"):
                username = payload[len("user:")].strip()
                if username:
                    logger.info(f"前端上报用户: {username}")
                    self.user_changed.emit(username)
            elif payload == "logout":
                logger.info("前端上报用户登出")
                self.user_logged_out.emit()
        except Exception as e:
            logger.warning(f"解析协议消息失败: {e} | {message}")
