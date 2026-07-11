# -*- coding: utf-8 -*-
"""
网络层模块（轻量版，基于 requests）
=================================================
  1. HttpClient      : 通用 HTTP/HTTPS 客户端（requests 封装）
  2. MessagePoller   : 后台消息轮询器（新消息检测 + 指数退避重连）
"""
import json as _json
import time
import threading
import logging

import requests

import config

logger = logging.getLogger("desktop.network")


class HttpClient:
    """基于 requests 的同步 HTTP 客户端。"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "HGStudentsUnion-Desktop/1.0"})

    def get(self, url, timeout=None):
        """同步 GET，返回 (status_code, text)。失败返回 (0, error)。"""
        tmo = timeout or config.get("request_timeout", 10)
        try:
            r = self.session.get(url, timeout=tmo)
            return r.status_code, r.text
        except requests.Timeout:
            logger.warning(f"请求超时: {url}")
            return 0, "timeout"
        except requests.ConnectionError as e:
            logger.warning(f"连接失败: {url} - {e}")
            return 0, "connection_error"
        except Exception as e:
            logger.warning(f"请求异常: {url} - {e}")
            return 0, str(e)


class MessagePoller:
    """
    后台线程轮询 /api/messages，检测新消息。
    指数退避重连，恢复后自动回归正常间隔。
    """
    new_messages = None       # 回调：新消息列表
    state_changed = None      # 回调：连接状态 "connected"/"reconnecting"

    def __init__(self, server_url=None, username=""):
        self._server_url = (server_url or config.get("server_url", "")).rstrip("/")
        self._username = username
        self._poll_interval = config.get("poll_interval", 15)
        self._max_backoff = config.get("reconnect_max_interval", 60)
        self._client = HttpClient()
        cfg = config.load()
        self._seen_ids = set(cfg.get("last_message_ids", {}).get(self._username, []))
        self._fail_count = 0
        self._running = False
        self._thread = None
        self._state = "disconnected"

    def start(self):
        if self._running:
            return
        self._running = True
        self._fail_count = 0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def set_username(self, username):
        self._username = username or ""
        cfg = config.load()
        self._seen_ids = set(cfg.get("last_message_ids", {}).get(self._username, []))

    def set_server_url(self, url):
        self._server_url = (url or "").rstrip("/")

    def get_state(self):
        return self._state

    def _set_state(self, state):
        if state != self._state:
            self._state = state
            logger.info(f"连接状态: {state}")
            if self.state_changed:
                self.state_changed(state)

    def _loop(self):
        if not self._server_url or not self._username:
            return
        self._set_state("connected")
        while self._running:
            self._poll_once()
            if not self._running:
                break
            # 计算等待
            wait = self._poll_interval
            if self._fail_count > 0:
                wait = min((2 ** self._fail_count) * 2, self._max_backoff)
            # 分段等待以便快速响应停止
            for _ in range(int(wait * 10)):
                if not self._running:
                    break
                time.sleep(0.1)

    def _poll_once(self):
        if not self._server_url or not self._username:
            return
        url = self._server_url + "/api/messages"
        code, text = self._client.get(url)
        if code != 200:
            self._fail_count += 1
            self._set_state("reconnecting")
            return
        # 成功
        if self._fail_count > 0:
            self._fail_count = 0
            self._set_state("connected")
        try:
            data = _json.loads(text)
        except _json.JSONDecodeError:
            return
        if not isinstance(data, list):
            return
        # 过滤当前用户的新消息
        new = []
        for m in data:
            if m.get("to") != self._username:
                continue
            mid = m.get("id")
            if mid is None:
                continue
            if mid not in self._seen_ids and not m.get("read", False):
                new.append(m)
            self._seen_ids.add(mid)
        self._persist_seen()
        if new and self.new_messages:
            logger.info(f"检测到 {len(new)} 条新消息")
            self.new_messages(new)

    def _persist_seen(self):
        cfg = config.load()
        last_map = dict(cfg.get("last_message_ids", {}))
        last_map[self._username] = list(self._seen_ids)[-500:]
        config.save({"last_message_ids": last_map})
