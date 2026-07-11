# 学生会人事管理系统 —— Windows 桌面端

基于 PySide6 的 Windows 原生桌面应用，复用现有 `index.html` 前端与 Flask 后端，集成系统通知、托盘常驻与联网管理。

## 功能特性

### 1. 系统原生消息通知
- 基于 **win11toast** 调用 Windows 通知中心（Toast Notification），通知进入操作中心可回溯查看
- 回退方案：`QSystemTrayIcon` 气球通知（无需额外依赖）
- 通知支持应用图标、声音、点击唤起主窗口
- 窗口最小化到托盘时仍可后台接收消息并弹窗提醒

### 2. 联网接口
- **HTTP/HTTPS 请求**：基于 `QNetworkAccessManager`，异步非阻塞
- **请求超时处理**：可配置超时（默认 10s），超时自动中止
- **断线重连**：指数退避策略（2^n × 2s，上限 60s），网络恢复后自动恢复正常轮询
- **网络状态监听**：双保险机制
  - `QNetworkInformation` 监听系统级网络变化（在线/离线实时感知）
  - 定时 ping 后端服务器检测可达性
- 新消息增量检测（对比已通知 id 集合，避免重复提醒）

### 3. Windows 系统兼容
- **系统托盘常驻**：右键菜单（显示窗口 / 连接状态 / 设置 / 退出），左键切换窗口
- **最小化到托盘**：关闭窗口不退出，后台持续运行
- **内嵌后端**：检测本地无服务时自动启动 Flask，开箱即用
- 配置持久化至 `%APPDATA%\HGStudentsUnion\config.json`

## 快速开始

### 环境要求
- Windows 10 / 11（64 位）
- Python 3.8+

### 安装依赖

```bash
cd desktop
pip install -r requirements.txt
```

### 运行

```bash
python main.py
```

首次启动会自动检测本地 `127.0.0.1:5000`，若无后端运行则内嵌启动 Flask。
如需连接远程服务器，启动后通过托盘菜单 →「设置」修改服务器地址。

## 架构说明

```
desktop/
├── main.py            # 应用入口：QWebEngineView 窗口 + 信号整合 + 设置对话框
├── network.py         # 网络层：HttpClient / NetworkMonitor / MessagePoller
├── notifier.py        # 原生通知：win11toast 优先，QSystemTrayIcon 回退
├── bridge.py         # JS↔Python 桥接：console 协议 + window.AndroidNative 注入
├── tray.py           # 系统托盘：QSystemTrayIcon + 右键菜单
├── config.py         # 配置管理：持久化至 %APPDATA%
└── requirements.txt  # 依赖清单
```

### 工作原理

```
┌─────────────────────────────────────────────────┐
│                  桌面端进程                      │
│                                                  │
│  ┌───────────┐    注入 JS     ┌──────────────┐  │
│  │ QWebEngine│ ◀───────────  │ NativeBridge  │  │
│  │  (前端UI) │ ──console──▶  │ (协议解析)    │  │
│  └───────────┘                └──────┬───────┘  │
│                                       │ 信号     │
│  ┌───────────┐  ┌──────────┐  ┌──────▼───────┐  │
│  │ TrayIcon  │  │ Notifier │  │MessagePoller │  │
│  │ (系统托盘) │  │ (原生通知)│  │ (后台轮询)   │  │
│  └───────────┘  └──────────┘  └──────┬───────┘  │
│                                       │          │
│                        ┌──────────────▼───────┐ │
│                        │  HttpClient + Monitor │ │
│                        │  (HTTP/超时/重连)     │ │
│                        └──────────┬───────────┘ │
└───────────────────────────────────┼─────────────┘
                                    │ HTTP/HTTPS
                          ┌─────────▼─────────┐
                          │  Flask 后端(main.py)│
                          │  本地内嵌或远程部署  │
                          └─────────────────────┘
```

### JS 桥接协议（零侵入）

前端 `index.html` 无需任何修改。通过 `QWebEngineScript` 在页面创建时注入
`window.AndroidNative` 对象，内部以 `console.log('@@native:...')` 协议传输：

| 协议消息 | 含义 |
|---|---|
| `@@native:notify:{json}` | 请求弹原生通知 |
| `@@native:visibility:0\|1` | 页面可见性变化 |
| `@@native:stop_polling` | 停止后台轮询 |
| `@@native:user:<name>` | 上报当前登录用户 |
| `@@native:logout` | 用户登出 |

Python 端 `QWebEnginePage.javaScriptConsoleMessage` 拦截并解析，转为 Qt 信号。

## 配置项

托盘菜单 →「设置」可调整：

| 配置 | 默认值 | 说明 |
|---|---|---|
| server_url | `http://127.0.0.1:5000` | 后端服务器地址 |
| poll_interval | 15 秒 | 消息轮询间隔 |
| request_timeout | 10 秒 | 请求超时 |
| notification_enabled | true | 启用桌面通知 |
| sound_enabled | true | 通知声音 |
| minimize_to_tray | true | 关闭窗口时最小化到托盘 |

## 打包为 exe

使用 PyInstaller 打包为单文件可执行程序：

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --icon ..\school-logo.png ^
    --add-data "..\index.html;." ^
    --add-data "..\school-logo.png;." ^
    main.py
```

生成的 `dist\main.exe` 可独立分发运行。

## 故障排查

| 问题 | 解决方案 |
|---|---|
| 启动黑屏 | 确认 PySide6-Addons 已安装（提供 WebEngine） |
| 无通知 | Windows 设置 → 系统 → 通知，确认应用已启用 |
| 内嵌后端启动失败 | 确认 `flask` 已安装，或连接远程服务器 |
| 远程连接超时 | 检查服务器防火墙、地址是否正确 |
