# -*- coding: utf-8 -*-
"""
网络层模块
=================================================
基于 PySide6 QNetworkAccessManager 实现的 HTTP/HTTPS 客户端，特性：
  1. HTTP/HTTPS 请求，支持 GET/POST/PUT/DELETE
  2. 请求超时处理（可配置，默认 10s）
  3. 断线检测 + 指数退避自动重连
  4. 网络状态监听（在线/离线实时感知）
  5. 与 Qt 事件循环集成，非阻塞高性能

提供三个核心类：
  - HttpClient      : 通用 HTTP 客户端
  - NetworkMonitor  : 网络连通性实时监听
  - MessagePoller   : 后台消息轮询器（新消息检测 + 重连恢复）
"""
import json as _json
import time
import logging

from PySide6.QtCore import (
    QObject, Signal, QTimer, QUrl, QByteArray, QCoreApplication
)
from PySide6.QtNetwork import (
    QNetworkAccessManager, QNetworkRequest, QNetworkReply,
    QSslConfiguration
)

import config

logger = logging.getLogger("desktop.network")


# ============================================================
# HttpClient —— 通用 HTTP/HTTPS 客户端
# ============================================================
class HttpClient(QObject):
    """
    封装 QNetworkAccessManager，提供带超时、重试的异步 HTTP 请求。

    用法（回调式）::
        client = HttpClient()
        client.get("http://host/api/messages",
                   on_success=lambda data: print(data),
                   on_error=lambda err: print(err))
    """

    def __init__(self, parent=None, default_timeout=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        # 启用 HTTPS
        ssl_cfg = QSslConfiguration.defaultConfiguration()
        ssl_cfg.setProtocol(QSslConfiguration.TlsV1_2)
        QSslConfiguration.setDefaultConfiguration(ssl_cfg)

        self.default_timeout = default_timeout or config.get("request_timeout", 10)
        # 活跃请求跟踪 {reply: QTimer}
        self._pending = {}

    # -------------------- 公共方法 --------------------
    def get(self, url, on_success=None, on_error=None, timeout=None, headers=None):
        return self._request("GET", url, on_success, on_error, timeout, headers, body=None)

    def post(self, url, body=None, on_success=None, on_error=None, timeout=None, headers=None):
        return self._request("POST", url, on_success, on_error, timeout, headers, body)

    def put(self, url, body=None, on_success=None, on_error=None, timeout=None, headers=None):
        return self._request("PUT", url, on_success, on_error, timeout, headers, body)

    def delete(self, url, on_success=None, on_error=None, timeout=None, headers=None):
        return self._request("DELETE", url, on_success, on_error, timeout, headers, body=None)

    def is_online(self):
        """快速判断：网络访问管理器是否处于可访问状态（非完全离线）。"""
        return self._nam.networkAccessible() != QNetworkAccessManager.NotAccessible

    # -------------------- 内部实现 --------------------
    def _request(self, method, url, on_success, on_error, timeout, headers, body):
        req = QNetworkRequest(QUrl(url))
        # 默认请求头
        req.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        req.setHeader(QNetworkRequest.UserAgentHeader,
                      "HGStudentsUnion-Desktop/1.0")
        # 自定义头
        if headers:
            for k, v in headers.items():
                req.setRawHeader(k.encode("utf-8"), str(v).encode("utf-8"))

        # 请求体
        data = None
        if body is not None:
            if isinstance(body, (dict, list)):
                data = QByteArray(_json.dumps(body, ensure_ascii=False).encode("utf-8"))
            elif isinstance(body, str):
                data = QByteArray(body.encode("utf-8"))
            elif isinstance(body, bytes):
                data = QByteArray(body)
            else:
                data = QByteArray(str(body).encode("utf-8"))

        # 发起请求
        method_upper = method.upper()
        if method_upper == "GET":
            reply = self._nam.get(req)
        elif method_upper == "POST":
            reply = self._nam.post(req, data or QByteArray())
        elif method_upper == "PUT":
            reply = self._nam.put(req, data or QByteArray())
        elif method_upper == "DELETE":
            reply = self._nam.deleteResource(req)
        else:
            if on_error:
                on_error(f"不支持的请求方法: {method}")
            return None

        logger.debug(f"{method_upper} {url}")

        # 超时定时器
        tmo = timeout or self.default_timeout
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._on_timeout(reply))
        timer.start(tmo * 1000)

        self._pending[reply] = timer
        reply.finished.connect(lambda: self._on_finished(reply, on_success, on_error))
        return reply

    def _on_finished(self, reply, on_success, on_error):
        timer = self._pending.pop(reply, None)
        if timer:
            timer.stop()
            timer.deleteLater()

        reply.deleteLater()
        # 通过 deleteLater 确保 reply 安全删除
        err = reply.error()
        if err != QNetworkReply.NoError:
            err_str = reply.errorString()
            logger.warning(f"请求失败 [{err}]: {err_str}")
            if on_error:
                on_error(err_str)
            return

        # 读取响应
        status_code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0
        raw = reply.readAll().data()
        try:
            text = raw.decode("utf-8") if raw else ""
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")

        # 尝试 JSON 解析
        if text:
            try:
                data = _json.loads(text)
            except _json.JSONDecodeError:
                data = text
        else:
            data = None

        if on_success:
            on_success(data, status_code)

    def _on_timeout(self, reply):
        if reply in self._pending:
            logger.warning("请求超时，主动中止")
            reply.abort()
            # abort 会触发 finished，on_error 在那里被调用
            # 但 abort 后 errorString 可能为空，这里补充
            reply.finished.disconnect()
            self._pending.pop(reply, None)
            reply.deleteLater()
            # 发送错误回调


# ============================================================
# NetworkMonitor —— 网络状态实时监听
# ============================================================
class NetworkMonitor(QObject):
    """
    监听系统网络连通状态，发射 online / offline 信号。

    策略：
      1. 优先使用 PySide6 QNetworkInformation（6.3+）监听系统级网络变化
      2. 同时以可配置间隔 ping 服务器，检测「到后端」的连通性
      3. 两者综合判定，双保险
    """
    online_changed = Signal(bool)   # True=在线, False=离线
    server_reachable = Signal(bool)  # 到后端服务器是否可达

    def __init__(self, parent=None, server_url=None, ping_interval=30):
        super().__init__(parent)
        self._server_url = (server_url or config.get("server_url", "")).rstrip("/")
        self._ping_interval = ping_interval
        self._online = True
        self._server_ok = True
        self._client = HttpClient(self)

        # ---- 系统级网络监听（QNetworkInformation）----
        self._ninfo = None
        try:
            from PySide6.QtNetwork import QNetworkInformation
            if QNetworkInformation.loadDefaultBackend() or \
               QNetworkInformation.loadBackendByFeature(
                   QNetworkInformation.Feature.OnlineDisconnectionAwareness):
                self._ninfo = QNetworkInformation.defaultInstance()
                if self._ninfo:
                    self._ninfo.reachabilityChanged.connect(self._on_reachability)
                    self._online = self._ninfo.reachability() == \
                        QNetworkInformation.Reachability.Online
                    logger.info(f"QNetworkInformation 已启用，初始在线={self._online}")
                else:
                    logger.info("QNetworkInformation 后端不可用，仅用 ping 监听")
            else:
                logger.info("QNetworkInformation 后端加载失败，仅用 ping 监听")
        except Exception as e:
            logger.info(f"QNetworkInformation 不可用: {e}")

        # ---- 服务器可达性 ping 定时器 ----
        self._ping_timer = QTimer(self)
        self._ping_timer.timeout.connect(self._ping)
        self._ping_timer.start(self._ping_interval * 1000)
        # 启动时立即 ping 一次
        QTimer.singleShot(2000, self._ping)

    def is_online(self):
        return self._online

    def is_server_reachable(self):
        return self._server_ok

    def set_server_url(self, url):
        self._server_url = (url or "").rstrip("/")

    def _on_reachability(self, info, reachability):
        online = reachability == type(reachability).Online
        if online != self._online:
            self._online = online
            logger.info(f"系统网络状态变更: {'在线' if online else '离线'}")
            self.online_changed.emit(online)

    def _ping(self):
        if not self._server_url:
            return
        # 用 /api/messages 或根路径做存活探测
        ping_url = self._server_url + "/api/messages"
        self._client.get(
            ping_url,
            on_success=lambda data, code: self._on_ping_ok(code),
            on_error=lambda err: self._on_ping_fail(err),
            timeout=5,
        )

    def _on_ping_ok(self, code):
        ok = 200 <= code < 500
        if ok != self._server_ok:
            self._server_ok = ok
            logger.info(f"后端可达性变更: {'可达' if ok else '不可达'}(HTTP {code})")
            self.server_reachable.emit(ok)

    def _on_ping_fail(self, err):
        if self._server_ok:
            self._server_ok = False
            logger.warning(f"后端不可达: {err}")
            self.server_reachable.emit(False)


# ============================================================
# MessagePoller —— 后台消息轮询（断线重连 + 新消息检测）
# ============================================================
class MessagePoller(QObject):
    """
    后台轮询 /api/messages，检测发给当前用户的新消息。

    特性：
      - 定时轮询（默认 15s）
      - 请求失败时指数退避重连，恢复后恢复正常间隔
      - 通过对比 last_message_ids 增量检测新消息
      - 发射 new_messages 信号携带新消息列表
      - 发射 connection_state 信号通知连接状态（用于托盘图标）
    """
    new_messages = Signal(list)       # 新消息列表
    connection_state_changed = Signal(str)   # "connected" / "reconnecting" / "offline"

    def __init__(self, parent=None, server_url=None, username=None):
        super().__init__(parent)
        self._server_url = (server_url or config.get("server_url", "")).rstrip("/")
        self._username = username or ""
        self._poll_interval = config.get("poll_interval", 15) * 1000
        self._max_backoff = config.get("reconnect_max_interval", 60) * 1000
        self._client = HttpClient(self)

        # 已通知过的消息 id 集合（持久化于 config）
        cfg = config.load()
        self._seen_ids = set(cfg.get("last_message_ids", {}).get(self._username, []))

        self._consecutive_failures = 0
        self._state = "disconnected"

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_once)
        # 首次延迟启动
        QTimer.singleShot(3000, self._start)

    # -------------------- 公共接口 --------------------
    def start(self):
        self._start()

    def stop(self):
        self._timer.stop()

    def set_username(self, username):
        """登录后设置当前用户名，切换 seen_ids。"""
        self._username = username or ""
        cfg = config.load()
        self._seen_ids = set(cfg.get("last_message_ids", {}).get(self._username, []))
        # 用户切换后立即轮询
        if self._username:
            self._start()

    def set_server_url(self, url):
        self._server_url = (url or "").rstrip("/")
        self._start()

    def get_state(self):
        return self._state

    # -------------------- 内部逻辑 --------------------
    def _start(self):
        """启动/恢复正常轮询。"""
        if not self._server_url or not self._username:
            return
        self._consecutive_failures = 0
        self._timer.stop()
        self._timer.start(self._poll_interval)
        self._set_state("connected")
        # 立即拉取一次
        QTimer.singleShot(500, self._poll_once)

    def _set_state(self, state):
        if state != self._state:
            self._state = state
            logger.info(f"连接状态: {state}")
            self.connection_state_changed.emit(state)

    def _poll_once(self):
        if not self._server_url or not self._username:
            return
        url = self._server_url + "/api/messages"
        self._client.get(
            url,
            on_success=self._on_success,
            on_error=self._on_error,
            timeout=config.get("request_timeout", 10),
            headers={"Accept": "application/json"},
        )

    def _on_success(self, data, code):
        if code != 200 or not isinstance(data, list):
            self._on_error(f"HTTP {code}")
            return
        # 重置失败计数，恢复正常间隔
        self._consecutive_failures = 0
        self._set_state("connected")
        cur_interval = config.get("poll_interval", 15) * 1000
        if self._timer.interval() != cur_interval:
            self._timer.start(cur_interval)

        # 过滤发给当前用户的消息
        my_msgs = [m for m in data if m.get("to") == self._username]
        new = []
        for m in my_msgs:
            mid = m.get("id")
            if mid is None:
                continue
            if mid not in self._seen_ids and not m.get("read", False):
                new.append(m)
            self._seen_ids.add(mid)

        # 持久化 seen_ids（截断最近 500 条避免无限增长）
        self._persist_seen()

        if new:
            logger.info(f"检测到 {len(new)} 条新消息")
            self.new_messages.emit(new)

    def _on_error(self, err):
        self._consecutive_failures += 1
        # 指数退避：2^n * base，上限 max_backoff
        backoff = min(
            (2 ** self._consecutive_failures) * 2000,
            self._max_backoff
        )
        logger.warning(
            f"轮询失败({self._consecutive_failures}次): {err}，"
            f"{backoff // 1000}s 后重试"
        )
        self._set_state("reconnecting")
        self._timer.stop()
        self._timer.start(backoff)

    def _persist_seen(self):
        """持久化已通知消息 id，防止重启后重复通知。"""
        cfg = config.load()
        last_map = dict(cfg.get("last_message_ids", {}))
        # 仅保留最近 500 条
        ids_list = list(self._seen_ids)[-500:]
        last_map[self._username] = ids_list
        config.save({"last_message_ids": last_map})
