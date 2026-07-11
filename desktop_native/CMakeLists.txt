cmake_minimum_required(VERSION 3.20)
project(HGStudentsUnionDesktop LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ============================================================
# MSVC 编译选项优化（极致性能 + 极小体积）
# ============================================================
if(MSVC)
    # /O2        —— 全速优化（速度优先）
    # /GL        —— 全程序优化（LTCG，链接时代码生成）
    # /Gy        —— 函数级链接（配合 /OPT:REF 移除未用函数）
    # /Gw        —— 优化全局数据（配合 /OPT:REF 移除未用数据）
    # /utf-8     —— 源码 UTF-8 编码（含中文）
    # /EHsc      —— C++ 异常
    # /W3        —— 警告级别
    # /Zc:__cplusplus —— 正确报告 C++ 标准版本
    add_compile_options(/O2 /GL /Gy /Gw /utf-8 /EHsc /W3 /Zc:__cplusplus)

    # 链接选项
    # /LTCG     —— 链接时代码生成（配合 /GL）
    # /OPT:REF  —— 移除未引用的函数和数据
    # /OPT:ICF  —— 合并相同的 COMDAT（折叠冗余代码）
    # /SUBSYSTEM:WINDOWS —— GUI 子系统，无控制台
    add_link_options(/LTCG /OPT:REF /OPT:ICF /SUBSYSTEM:WINDOWS)

    # 静态链接 C 运行时（避免依赖 vcruntime140.dll）
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

# ============================================================
# 源文件
# ============================================================
set(SOURCES
    main.cpp
    tray.cpp
    notifier.cpp
    backend.cpp
    app.rc
)

# WIN32 表示 GUI 子系统应用（无控制台黑框，类似微信）
add_executable(${PROJECT_NAME} WIN32 ${SOURCES})

target_include_directories(${PROJECT_NAME} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

# ============================================================
# WebView2 SDK 配置
# 获取方式（任选其一）：
#   方式1：vcpkg install microsoft-web-webview2
#   方式2：NuGet 包 Microsoft.Web.WebView2
#   方式3：从 GitHub 下载 WebView2 SDK headers
# ============================================================
set(WEBVIEW2_SDK_DIR "" CACHE PATH "WebView2 SDK 安装路径（含 include/ 和 lib/）")

if(WEBVIEW2_SDK_DIR)
    target_include_directories(${PROJECT_NAME} PRIVATE ${WEBVIEW2_SDK_DIR}/include)
    target_link_directories(${PROJECT_NAME} PRIVATE ${WEBVIEW2_SDK_DIR}/lib)
else()
    # 尝试 vcpkg 自动查找
    find_package(Microsoft.Web.WebView2 CONFIG QUIET)
    if(TARGET Microsoft.Web.WebView2)
        target_link_libraries(${PROJECT_NAME} PRIVATE Microsoft.Web.WebView2)
    endif()
endif()

# ============================================================
# 链接 Windows 系统库
# ============================================================
target_link_libraries(${PROJECT_NAME} PRIVATE
    RuntimeObject      # WinRT COM 运行时（Toast 通知）
    WindowsApp         # Windows App SDK
    WebView2Loader     # WebView2 加载器
    winhttp            # HTTP/HTTPS 客户端
    ws2_32             # Winsock（端口检测）
    shell32            # Shell API（托盘）
    user32             # 窗口
    gdi32              # GDI
    gdiplus            # GDI+（PNG 图标加载）
    advapi32           # 注册表/进程
)

# ============================================================
# 安装目标
# ============================================================
install(TARGETS ${PROJECT_NAME} RUNTIME DESTINATION bin)

# 输出目录
set_target_properties(${PROJECT_NAME} PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin
    OUTPUT_NAME "学生会人事管理系统"
)
