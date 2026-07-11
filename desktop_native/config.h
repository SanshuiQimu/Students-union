#pragma once
#include <string>
#include <functional>
#include <vector>

// 应用配置常量
namespace AppConfig {
    // 窗口标题
    constexpr const wchar_t* APP_TITLE = L"学生会人事管理系统";
    // 窗口默认尺寸
    constexpr int WINDOW_W = 1100;
    constexpr int WINDOW_H = 760;
    constexpr int WINDOW_MIN_W = 900;
    constexpr int WINDOW_MIN_H = 600;
    // 内嵌后端地址
    constexpr const wchar_t* BACKEND_HOST = L"127.0.0.1";
    constexpr int BACKEND_PORT = 5000;
    constexpr const wchar_t* BACKEND_URL = L"http://127.0.0.1:5000";
    // 消息轮询间隔（毫秒）
    constexpr int POLL_INTERVAL_MS = 15000;
    // 请求超时（毫秒）
    constexpr int REQUEST_TIMEOUT_MS = 10000;
    // 重连最大间隔（毫秒）
    constexpr int RECONNECT_MAX_MS = 60000;
}

// 消息结构
struct AppMessage {
    std::wstring id;
    std::wstring to;
    std::wstring title;
    std::wstring body;
    bool read;
};

// 全局回调类型
using ShowWindowCallback = std::function<void()>;
using MessageCallback = std::function<void(const std::vector<AppMessage>&)>;
