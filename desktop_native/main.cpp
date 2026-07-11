// main.cpp —— Win32 主窗口 + WebView2 + 托盘 + 通知 + 后端整合
// 使用 MSVC 编译为 Windows 原生二进制，极致性能
#include <windows.h>
#include <shellapi.h>
#include <wrl/client.h>
#include <WebView2.h>
#include <atomic>
#include <mutex>
#include <string>

#include "config.h"
#include "tray.h"
#include "notifier.h"
#include "backend.h"

using namespace Microsoft::WRL;

// 自定义窗口消息
#define WM_APP_TRAY          (WM_APP + 1)  // 托盘图标回调
#define WM_APP_NEW_MESSAGES  (WM_APP + 2)  // 新消息通知
#define WM_APP_STATE_CHANGE  (WM_APP + 3)  // 连接状态变化

// 窗口类名
static const wchar_t* WC_MAIN = L"HGStudentsUnionMainWindow";

// 全局状态（单实例应用）
static HWND g_hwnd = nullptr;
static ComPtr<ICoreWebView2Controller> g_webController;
static ComPtr<ICoreWebView2> g_webView;
static TrayManager* g_tray = nullptr;
static Notifier* g_notifier = nullptr;
static BackendLauncher g_backend;
static MessagePoller g_poller;
static std::wstring g_serverUrl = AppConfig::BACKEND_URL;
static std::wstring g_iconPath;
static std::atomic<bool> g_quit{false};

// 新消息队列（线程安全）
static std::mutex g_msgMutex;
static std::vector<AppMessage> g_pendingMessages;

// ============================================================
// 窗口大小变化时调整 WebView2
// ============================================================
static void ResizeWebView() {
    if (g_webController) {
        RECT bounds;
        GetClientRect(g_hwnd, &bounds);
        g_webController->put_Bounds(bounds);
    }
}

// ============================================================
// 初始化 WebView2
// ============================================================
static void InitWebView2() {
    CreateCoreWebView2EnvironmentWithOptions(
        nullptr, nullptr, nullptr,
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [](HRESULT hr, ICoreWebView2Environment* env) -> HRESULT {
                if (FAILED(hr) || !env) return hr;
                env->CreateCoreWebView2Controller(g_hwnd,
                    Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
                        [](HRESULT hr, ICoreWebView2Controller* controller) -> HRESULT {
                            if (FAILED(hr) || !controller) return hr;
                            g_webController = controller;
                            g_webController->get_CoreWebView2(&g_webView);

                            // 显示并调整大小
                            g_webController->put_IsVisible(TRUE);
                            ResizeWebView();

                            // 导航到后端 URL
                            g_webView->Navigate(g_serverUrl.c_str());

                            return S_OK;
                        }).Get());
                return S_OK;
            }).Get());
}

// ============================================================
// 启动内嵌后端
// ============================================================
static void EnsureBackend() {
    std::wstring host = AppConfig::BACKEND_HOST;
    int port = AppConfig::BACKEND_PORT;

    if (BackendLauncher::IsPortOpen(host, port, 1000)) {
        // 后端已在运行
        return;
    }

    // 搜索 python.exe
    std::wstring pythonExe;
    // 1. 同目录下的 python
    wchar_t exePath[MAX_PATH];
    GetModuleFileNameW(nullptr, exePath, MAX_PATH);
    std::wstring exeDir = exePath;
    exeDir = exeDir.substr(0, exeDir.find_last_of(L"\\"));
    std::wstring localPy = exeDir + L"\\python\\python.exe";
    if (GetFileAttributesW(localPy.c_str()) != INVALID_FILE_ATTRIBUTES) {
        pythonExe = localPy;
    }

    // 2. 同目录下的 main.py（Flask 后端）
    std::wstring scriptPath = exeDir + L"\\main.py";
    if (GetFileAttributesW(scriptPath.c_str()) == INVALID_FILE_ATTRIBUTES) {
        // 尝试上级目录
        std::wstring parent = exeDir.substr(0, exeDir.find_last_of(L"\\"));
        scriptPath = parent + L"\\main.py";
    }

    if (pythonExe.empty() || GetFileAttributesW(scriptPath.c_str()) == INVALID_FILE_ATTRIBUTES) {
        // 无内嵌 Python，假设远程后端可用
        return;
    }

    if (g_backend.Start(pythonExe, scriptPath, port)) {
        g_backend.WaitForReady(10000);
    }
}

// ============================================================
// 启动消息轮询
// ============================================================
static void StartPolling(const std::wstring& username) {
    g_poller.SetServerUrl(g_serverUrl);
    g_poller.SetUsername(username);
    g_poller.onNewMessages = [](const std::vector<AppMessage>& msgs) {
        // 后台线程回调：存入队列，通知主线程
        {
            std::lock_guard<std::mutex> lock(g_msgMutex);
            g_pendingMessages = msgs;
        }
        PostMessageW(g_hwnd, WM_APP_NEW_MESSAGES, 0, 0);
    };
    g_poller.onStateChanged = [](const std::wstring& state) {
        // 后台线程：通知主线程更新托盘
        PostMessageW(g_hwnd, WM_APP_STATE_CHANGE, 0, 0);
    };
    g_poller.Start(g_serverUrl, username);
}

// ============================================================
// 窗口控制
// ============================================================
static void ShowMainWindow() {
    ShowWindow(g_hwnd, SW_RESTORE);
    SetForegroundWindow(g_hwnd);
}

static void ToggleMainWindow() {
    if (IsWindowVisible(g_hwnd)) {
        ShowWindow(g_hwnd, SW_HIDE);
    } else {
        ShowMainWindow();
    }
}

// ============================================================
// 窗口过程
// ============================================================
static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_SIZE:
            if (wp != SIZE_MINIMIZED) ResizeWebView();
            return 0;

        case WM_GETMINMAXINFO: {
            auto* mmi = (MINMAXINFO*)lp;
            mmi->ptMinTrackSize.x = AppConfig::WINDOW_MIN_W;
            mmi->ptMinTrackSize.y = AppConfig::WINDOW_MIN_H;
            return 0;
        }

        case WM_CLOSE:
            // 最小化到托盘而非退出
            ShowWindow(hwnd, SW_HIDE);
            if (g_tray) g_tray->ShowBalloon(L"学生会人事管理系统", L"程序已最小化到托盘，后台持续接收消息");
            return 0;

        // 托盘图标回调
        case WM_APP_TRAY: {
            if (wp == WM_LBUTTONUP) {
                // 左键单击：切换窗口
                ToggleMainWindow();
            } else if (wp == WM_RBUTTONUP) {
                // 右键：显示菜单
                POINT pt;
                GetCursorPos(&pt);
                if (g_tray) g_tray->ShowContextMenu(hwnd, pt.x, pt.y);
            }
            return 0;
        }

        // 新消息通知（主线程）
        case WM_APP_NEW_MESSAGES: {
            std::vector<AppMessage> msgs;
            {
                std::lock_guard<std::mutex> lock(g_msgMutex);
                msgs.swap(g_pendingMessages);
            }
            if (!msgs.empty() && g_notifier) {
                g_notifier->ShowMessages(msgs, g_iconPath, []() { ShowMainWindow(); });
            }
            return 0;
        }

        // 连接状态变化
        case WM_APP_STATE_CHANGE: {
            if (g_tray) {
                g_tray->UpdateTip(L"学生会人事管理系统 - 运行中");
            }
            return 0;
        }

        case WM_DESTROY:
            g_quit = true;
            PostQuitMessage(0);
            return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

// ============================================================
// 注册窗口类 + 创建窗口
// ============================================================
static HWND CreateMainWindow(HINSTANCE hInst) {
    WNDCLASSEXW wc = {};
    wc.cbSize = sizeof(wc);
    wc.style = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInst;
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = WC_MAIN;
    // 加载图标
    wc.hIcon = (HICON)LoadImageW(nullptr, g_iconPath.c_str(),
                                  IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE);
    if (!wc.hIcon) wc.hIcon = LoadIconW(nullptr, IDI_APPLICATION);
    wc.hIconSm = wc.hIcon;
    RegisterClassExW(&wc);

    int screenW = GetSystemMetrics(SM_CXSCREEN);
    int screenH = GetSystemMetrics(SM_CYSCREEN);
    int x = (screenW - AppConfig::WINDOW_W) / 2;
    int y = (screenH - AppConfig::WINDOW_H) / 2;

    HWND hwnd = CreateWindowExW(
        0, WC_MAIN, AppConfig::APP_TITLE,
        WS_OVERLAPPEDWINDOW,
        x, y, AppConfig::WINDOW_W, AppConfig::WINDOW_H,
        nullptr, nullptr, hInst, nullptr);
    return hwnd;
}

// ============================================================
// WinMain 入口
// ============================================================
int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE, PWSTR cmdLine, int showCmd) {
    // 初始化 COM（STA，WebView2 需要）
    HRESULT hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    if (FAILED(hr)) return 1;

    // 确定图标路径
    wchar_t exePath[MAX_PATH];
    GetModuleFileNameW(nullptr, exePath, MAX_PATH);
    std::wstring exeDir = exePath;
    exeDir = exeDir.substr(0, exeDir.find_last_of(L"\\"));
    g_iconPath = exeDir + L"\\school-logo.png";

    // 创建主窗口
    g_hwnd = CreateMainWindow(hInst);
    if (!g_hwnd) { CoUninitialize(); return 1; }

    // 创建系统托盘
    g_tray = new TrayManager(g_hwnd, WM_APP_TRAY);
    g_tray->Add(g_iconPath, L"学生会人事管理系统");
    g_tray->onShowWindow = ShowMainWindow;
    g_tray->onToggleWindow = ToggleMainWindow;
    g_tray->onQuit = []() {
        if (MessageBoxW(g_hwnd, L"确定要退出学生会人事管理系统吗？\n退出后将不再接收新消息通知。",
                       L"确认退出", MB_YESNO | MB_ICONQUESTION) == IDYES) {
            g_quit = true;
            g_poller.Stop();
            g_backend.Stop();
            if (g_tray) g_tray->Remove();
            DestroyWindow(g_hwnd);
        }
    };

    // 创建通知器
    g_notifier = new Notifier();
    g_notifier->SetFallbackTray(g_tray);

    // 启动内嵌后端
    EnsureBackend();

    // 初始化 WebView2（加载前端页面）
    InitWebView2();

    // 显示窗口
    ShowWindow(g_hwnd, showCmd);
    UpdateWindow(g_hwnd);

    // 消息循环
    MSG msg;
    while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }

    // 清理
    g_poller.Stop();
    g_backend.Stop();
    if (g_tray) { g_tray->Remove(); delete g_tray; }
    if (g_notifier) delete g_notifier;
    g_webController.Reset();
    g_webView.Reset();
    CoUninitialize();
    return (int)msg.wParam;
}
