#pragma once
#include <windows.h>
#include <string>
#include <vector>
#include <functional>
#include <thread>
#include <atomic>
#include "config.h"

// 后端启动器：启动内嵌 Flask 后端（Python 子进程）
class BackendLauncher {
public:
    BackendLauncher();
    ~BackendLauncher();

    // 启动后端，返回是否成功
    // pythonExe: python.exe 路径（如为空则搜索 PATH）
    // scriptPath: 后端 main.py 路径
    // port: 端口
    bool Start(const std::wstring& pythonExe,
               const std::wstring& scriptPath,
               int port);
    // 停止后端
    void Stop();
    // 检测端口是否在监听
    static bool IsPortOpen(const std::wstring& host, int port, int timeoutMs = 1000);
    // 等待端口就绪
    bool WaitForReady(int timeoutMs = 10000);
    bool IsRunning() const { return m_running.load(); }

private:
    std::atomic<bool> m_running{false};
    HANDLE m_hProcess{nullptr};
    HANDLE m_hThread{nullptr};
};

// WinHTTP 网络客户端
class HttpClient {
public:
    HttpClient();
    ~HttpClient();

    // 异步 GET 请求
    // onDone: 回调 (statusCode, responseBody)，失败时 statusCode=0
    void GetAsync(const std::wstring& url,
                  std::function<void(int, const std::wstring&)> onDone,
                  int timeoutMs = 10000);

private:
    std::wstring m_userAgent;
};

// 消息轮询器：后台轮询 /api/messages，检测新消息
class MessagePoller {
public:
    MessagePoller();
    ~MessagePoller();

    // 启动轮询
    void Start(const std::wstring& serverUrl, const std::wstring& username);
    void Stop();
    void SetUsername(const std::wstring& username) { m_username = username; }
    void SetServerUrl(const std::wstring& url) { m_serverUrl = url; }

    // 新消息回调
    std::function<void(const std::vector<AppMessage>&)> onNewMessages;
    // 连接状态回调: "connected" / "reconnecting" / "offline"
    std::function<void(const std::wstring&)> onStateChanged;

private:
    void PollLoop();
    void DoPoll();
    std::wstring ParseMessages(const std::wstring& json,
                              std::vector<AppMessage>& out);
    bool IsNew(const std::wstring& id);

    std::atomic<bool> m_running{false};
    std::thread m_thread;
    std::wstring m_serverUrl;
    std::wstring m_username;
    std::vector<std::wstring> m_seenIds;
    int m_failCount{0};
    HttpClient m_http;
};
