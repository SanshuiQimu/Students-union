# -*- coding: utf-8 -*-
"""
配置管理模块
负责读取/持久化桌面端运行配置（服务器地址、轮询间隔、通知开关等）。
配置文件存放在用户目录下，避免应用更新丢失。
"""
import os
import json
import threading

# 配置文件存放目录：%APPDATA%\HGStudentsUnion\config.json
_APP_NAME = "HGStudentsUnion"
_CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), _APP_NAME)
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "config.json")

# 默认配置
DEFAULTS = {
    # 后端服务器地址（本地默认指向 Flask dev server）
    "server_url": "http://127.0.0.1:5000",
    # 消息轮询间隔（秒）
    "poll_interval": 15,
    # 请求超时（秒）
    "request_timeout": 10,
    # 断线重连最大间隔（秒，指数退避上限）
    "reconnect_max_interval": 60,
    # 是否启用桌面通知
    "notification_enabled": True,
    # 是否启用声音提示
    "sound_enabled": True,
    # 最小化到托盘（关闭窗口时）
    "minimize_to_tray": True,
    # 开机自启
    "auto_start": False,
    # 上次记录的消息 id（用于增量检测）
    "last_message_ids": {},
}

_lock = threading.Lock()
_cache = None


def _ensure_dir():
    os.makedirs(_CONFIG_DIR, exist_ok=True)


def load():
    """加载配置，合并默认值。线程安全。"""
    global _cache
    with _lock:
        if _cache is not None:
            return dict(_cache)
        cfg = dict(DEFAULTS)
        try:
            _ensure_dir()
            if os.path.exists(_CONFIG_PATH):
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    cfg.update(saved)
        except Exception as e:
            print(f"[Config] 加载配置失败，使用默认值: {e}")
        _cache = cfg
        return dict(cfg)


def save(updates):
    """合并更新并持久化配置。线程安全。"""
    global _cache
    with _lock:
        cfg = _cache if _cache is not None else dict(DEFAULTS)
        cfg.update(updates)
        _cache = dict(cfg)
        try:
            _ensure_dir()
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Config] 保存配置失败: {e}")


def get(key, default=None):
    """读取单个配置项。"""
    return load().get(key, default)


def set(key, value):
    """设置单个配置项并持久化。"""
    save({key: value})


def config_path():
    """返回配置文件路径（供调试查看）。"""
    return _CONFIG_PATH
