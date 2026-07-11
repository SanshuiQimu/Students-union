# 学生会人事管理系统 —— 纯 C++ Win32 原生桌面应用

完全使用 **C++ + Win32 API** 构建，**无任何浏览器、WebView、Web 组件依赖**。所有界面均为 Windows 原生控件，直接调用后端 REST API。

## 核心模块

### 1. 登录界面
- 用户名/密码输入框（`EDIT` 控件，密码 `ES_PASSWORD`）
- 身份选择下拉框（`COMBOBOX`：部长/成员）
- 服务器地址输入框（可配置连接地址）
- 登录逻辑：`POST /api/auth/login` 调用后端认证
- Supabase 未配置时支持「直接进入」模式
- 服务器连通性检测（解决连接拒绝问题）

### 2. 成员管理界面
- **成员列表**：`ListView` 控件（报告模式），列：ID/姓名/部门/职位/职责/入职日期/离职日期
- **增删改查**：
  - 添加：弹出对话框输入成员信息 → `POST /api/members`
  - 编辑：选中行后修改 → `PUT /api/member/<id>`
  - 删除：确认后删除 → `DELETE /api/member/<id>`
  - 刷新：重新 `GET /api/members`
- 编辑对话框动态创建（内存模板，无需 .rc 资源文件）

### 3. 网络层（解决连接拒绝）
- 基于 **WinHTTP API** 的 HTTP/HTTPS 客户端
- **连接超时**：连接 5s，读取 10s（避免无限等待）
- **自动重试**：`GetWithRetry()` 指数退避重试（解决连接拒绝）
- **错误提示**：连接失败时显示具体原因（无法连接/超时/服务器错误）
- **服务器探测**：启动时 `GET /api/auth/status` 检测后端可达性

## 文件结构

```
desktop_win32/
├── main.cpp              # WinMain + 登录窗口
├── members_window.cpp    # 成员管理窗口（ListView + CRUD）
├── members_window.h      # 成员管理声明
├── http_client.cpp       # WinHTTP 客户端 + JSON 解析
├── http_client.h         # HTTP 客户端声明
├── resource.h            # 控件 ID 定义
├── CMakeLists.txt        # MSVC 构建配置
└── README.md
```

## 编译

### 环境要求
- Visual Studio 2022（MSVC v143）或 Build Tools
- CMake 3.20+
- Windows 10 SDK

### 编译步骤
```bash
cmake -B build -S . -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
# 产物：build/bin/学生会人事管理系统.exe（约 1-2MB，纯原生）
```

## 运行

1. 启动 Flask 后端：`python main.py`（项目根目录）
2. 双击 `学生会人事管理系统.exe`
3. 登录界面输入用户名/密码（或点击「直接进入」）

## 技术特点

| 特性 | 实现 |
|---|---|
| 界面框架 | Win32 API（CreateWindowEx + 控件） |
| 网络层 | WinHTTP（同步 + 重试） |
| JSON 解析 | 手写轻量解析器（无第三方库） |
| 依赖 | 仅 Windows 系统库 |
| 体积 | ~1-2MB（无运行时依赖） |
| 编码 | UTF-8 ↔ UTF-16 自动转换（支持中文） |
