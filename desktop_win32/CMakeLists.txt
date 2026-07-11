cmake_minimum_required(VERSION 3.20)
project(HGStudentsUnionWin32 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# MSVC 编译优化（极致性能 + 极小体积）
if(MSVC)
    add_compile_options(/O2 /GL /Gy /Gw /utf-8 /EHsc /W3 /Zc:__cplusplus)
    add_link_options(/LTCG /OPT:REF /OPT:ICF /SUBSYSTEM:WINDOWS)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

add_executable(${PROJECT_NAME} WIN32
    main.cpp
    members_window.cpp
    http_client.cpp
)

target_include_directories(${PROJECT_NAME} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

# 仅链接 Windows 系统库（无第三方依赖，无 Web 组件）
target_link_libraries(${PROJECT_NAME} PRIVATE
    user32          # 窗口与消息
    gdi32           # 图形设备
    comctl32        # ListView/Button 等公共控件
    comdlg32        # 通用对话框
    winhttp         # HTTP/HTTPS 网络请求
    ws2_32          # Winsock（端口检测）
    shell32         # Shell API
    advapi32        # 系统服务
)

set_target_properties(${PROJECT_NAME} PROPERTIES
    OUTPUT_NAME "学生会人事管理系统"
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin
)
