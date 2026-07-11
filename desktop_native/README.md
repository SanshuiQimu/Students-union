# 学生会人事管理系统 —— C++/MSVC 原生桌面端

使用 **C++ + Win32 API + WebView2** 开发，经 **MSVC 编译器**编译为 Windows 原生二进制，极致运行性能，体积远低于 100MB。

## 与 Python 版的区别

| 特性 | Python 版 (PySide6) | C++ 版 (本项目) |
|---|---|---|
| 语言 | Python | C++ |
| 编译器 | PyInstaller 打包 | MSVC 原生编译 |
| 窗口/渲染 | Qt + QtWebEngine(Chromium) | Win32 + WebView2(系统内置) |
| 体积 | 230MB | **~20MB**（含 Python 后端） |
| 性能 | 解释执行 | 原生机器码 |
| 依赖 | 打包 Qt 运行时 | 仅依赖系统 WebView2 |

**体积优化的核心**：剥离 QtWebEngine（Chromium 内核 150MB+），改用 Windows 10/11 系统自带的 **WebView2**（Edge Chromium 运行时，无需打包）。

## 功能架构

```
desktop_native/
├── main.cpp           # Win32 窗口 + WebView2 初始化 + 模块整合
├── tray.cpp/.h        # 系统托盘（Shell_NotifyIcon）
├── notifier.cpp/.h    # 原生 Toast 通知（WinRT COM）+ 气球回退
├── backend.cpp/.h     # WinHTTP 网络层 + 后端启动器 + 消息轮询
├── config.h           # 配置常量
├── app.rc             # 资源文件（图标）
├── app.manifest       # 应用清单（DPI感知/UTF-8/兼容性）
├── CMakeLists.txt     # MSVC 构建配置
└── installer.nsi      # NSIS 安装程序脚本
```

### 1. 独立桌面应用窗口
- `main.cpp` 创建 Win32 主窗口（`CreateWindowExW`），`WS_OVERLAPPEDWINDOW` 样式
- WebView2 渲染现有 `index.html` 前端
- `app.manifest` 声明 PerMonitorV2 DPI 感知、UTF-8 代码页
- 窗口图标加载自 `school-logo.png`（GDI+）

### 2. 任务栏图标 + 系统托盘
- `tray.cpp` 通过 `Shell_NotifyIconW` 实现系统托盘常驻
- 任务栏图标通过窗口类 `hIcon` 设置
- 右键菜单：显示窗口/设置/退出
- 左键单击切换窗口显示/隐藏
- 关闭窗口时最小化到托盘（不退出）

### 3. 无需命令行双击运行
- MSVC 编译为 `.exe`，`/SUBSYSTEM:WINDOWS` 无控制台
- 双击即可启动，类似微信桌面端体验

### 4. 联网接口（WinHTTP）
- `backend.cpp` 中 `HttpClient` 基于 **WinHTTP API**（Windows 原生）
- 异步 GET 请求 + 超时处理（可配置）
- `MessagePoller` 后台线程轮询 `/api/messages`，指数退避重连
- 端口检测用 Winsock2

### 5. 原生通知
- `notifier.cpp` 优先使用 **WinRT Toast**（Windows 通知中心）
- 回退使用托盘气球通知

## 编译环境要求

- **Visual Studio 2022**（含 MSVC v143 编译器）或 **Build Tools for Visual Studio 2022**
- **CMake 3.20+**
- **WebView2 SDK**（三选一）：
  - vcpkg: `vcpkg install microsoft-web-webview2`
  - NuGet: 安装 `Microsoft.Web.WebView2` 包
  - 手动: 从 [WebView2 SDK](https://github.com/MicrosoftEdge/WebView2Samples) 下载 headers
- **Windows 10 SDK**（10.0.19041+，含 WinHTTP、WinRT）

## 编译步骤

```bash
# 1. 配置（指定 WebView2 SDK 路径）
cmake -B build -S . ^
    -DWEBVIEW2_SDK_DIR="C:/path/to/webview2/sdk" ^
    -DCMAKE_BUILD_TYPE=Release

# 2. 编译（MSVC 原生优化）
cmake --build build --config Release

# 3. 产物
#    build/bin/学生会人事管理系统.exe（约 3-8MB）
```

或用 VS 2022 直接打开 CMake 项目（File → Open → CMake...）。

## 部署文件准备

编译完成后，准备部署目录：

```
部署目录/
├── 学生会人事管理系统.exe    # C++ 主程序
├── WebView2Loader.dll        # WebView2 加载器（~150KB）
├── index.html                # 前端页面
├── school-logo.png           # 应用图标
├── main.py                   # Flask 后端
└── python/                   # Python 嵌入式运行时
    ├── python.exe
    └── ...
```

### 获取 Python 嵌入式运行时

```bash
# 下载 python-3.12.x-embed-amd64.zip（约 10MB）
# 解压到 python/ 目录
# 安装 Flask：.\python\python.exe -m pip install flask
```

## 打包安装程序

```bash
# 安装 NSIS（https://nsis.sourceforge.io/）
# 修改 installer.nsi 中的路径指向你的构建产物
# 编译安装程序：
makensis installer.nsi

# 产物：学生会人事管理系统_安装程序.exe（约 15-25MB，远低于 100MB）
```

安装程序使用 **LZMA 固实压缩**，将 C++ exe + Python 运行时 + 前端 + 后端
全部压缩为单一安装包。用户双击安装程序，自动部署到
`%LOCALAPPDATA%\HGStudentsUnion`，创建桌面/开始菜单快捷方式。

## 体积分析

| 组件 | 原始大小 | LZMA 压缩后 |
|---|---|---|
| C++ 主程序 exe | ~6MB | ~3MB |
| WebView2Loader.dll | 150KB | 80KB |
| Python 嵌入式 | 10MB | 4MB |
| Flask + 依赖 | 5MB | 2MB |
| index.html + 图标 | 1MB | 0.5MB |
| **安装程序总计** | **~22MB** | **~10MB** |

**满足 100MB 限制**，无需进一步精简。

## 运行原理

1. 用户双击 exe 启动
2. `EnsureBackend()` 检测本地 5000 端口，无服务则启动内嵌 Python Flask
3. WebView2 加载 `http://127.0.0.1:5000`，渲染 `index.html`
4. 系统托盘图标显示
5. 后台 `MessagePoller` 线程轮询消息，新消息触发 Toast 通知
6. 关闭窗口 → 最小化到托盘，后台持续运行

## 系统要求

- Windows 10 1809+ 或 Windows 11（需内置 WebView2 运行时）
- WebView2 Runtime（Win10/11 通常已预装，未预装可从 Microsoft 下载）
