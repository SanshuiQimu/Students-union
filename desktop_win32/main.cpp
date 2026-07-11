// main.cpp —— 登录窗口 + WinMain 入口
// 纯 C++ Win32 API，无浏览器/WebView 依赖
#include <windows.h>
#include <commctrl.h>
#include <string>
#include "http_client.h"
#include "members_window.h"
#include "resource.h"

#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "comdlg32.lib")

// 全局状态
static HINSTANCE g_hInst = nullptr;
static HttpClient* g_http = nullptr;
static MembersWindow* g_membersWin = nullptr;
static HWND g_loginHwnd = nullptr;
static std::string g_serverUrl = "http://127.0.0.1:5000";

// 登录窗口类名
static const wchar_t* WC_LOGIN = L"HGLoginWindow";

// ============================================================
// 登录窗口控件创建
// ============================================================
static void CreateLoginControls(HWND hwnd) {
    // 标题
    CreateWindowW(L"STATIC", L"学生会人事管理系统",
        WS_CHILD | WS_VISIBLE | SS_CENTER,
        50, 20, 380, 30, hwnd, nullptr, g_hInst, nullptr);
    CreateWindowW(L"STATIC", L"请登录以继续",
        WS_CHILD | WS_VISIBLE | SS_CENTER,
        50, 50, 380, 20, hwnd, nullptr, g_hInst, nullptr);

    int y = 90;
    // 用户名
    CreateWindowW(L"STATIC", L"用户名:",
        WS_CHILD | WS_VISIBLE, 70, y + 4, 70, 20,
        hwnd, nullptr, g_hInst, nullptr);
    CreateWindowW(L"EDIT", L"",
        WS_CHILD | WS_VISIBLE | WS_BORDER | ES_AUTOHSCROLL,
        150, y, 250, 24, hwnd, (HMENU)IDC_LOGIN_USER, g_hInst, nullptr);
    y += 35;

    // 密码
    CreateWindowW(L"STATIC", L"密码:",
        WS_CHILD | WS_VISIBLE, 70, y + 4, 70, 20,
        hwnd, nullptr, g_hInst, nullptr);
    CreateWindowW(L"EDIT", L"",
        WS_CHILD | WS_VISIBLE | WS_BORDER | ES_AUTOHSCROLL | ES_PASSWORD,
        150, y, 250, 24, hwnd, (HMENU)IDC_LOGIN_PASS, g_hInst, nullptr);
    y += 35;

    // 角色
    CreateWindowW(L"STATIC", L"身份:",
        WS_CHILD | WS_VISIBLE, 70, y + 4, 70, 20,
        hwnd, nullptr, g_hInst, nullptr);
    HWND combo = CreateWindowW(L"COMBOBOX", L"",
        WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
        150, y, 250, 100, hwnd, (HMENU)IDC_LOGIN_ROLE, g_hInst, nullptr);
    SendMessageW(combo, CB_ADDSTRING, 0, (LPARAM)L"部长 / 处长");
    SendMessageW(combo, CB_ADDSTRING, 0, (LPARAM)L"成员");
    SendMessageW(combo, CB_SETCURSEL, 0, 0);
    y += 35;

    // 服务器地址
    CreateWindowW(L"STATIC", L"服务器:",
        WS_CHILD | WS_VISIBLE, 70, y + 4, 70, 20,
        hwnd, nullptr, g_hInst, nullptr);
    CreateWindowW(L"EDIT", Utf8ToWide(g_serverUrl).c_str(),
        WS_CHILD | WS_VISIBLE | WS_BORDER | ES_AUTOHSCROLL,
        150, y, 250, 24, hwnd, (HMENU)IDC_LOGIN_SERVER, g_hInst, nullptr);
    y += 40;

    // 登录按钮
    CreateWindowW(L"BUTTON", L"登 录",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON | BS_DEFPUSHBUTTON,
        150, y, 120, 35, hwnd, (HMENU)IDC_LOGIN_BTN, g_hInst, nullptr);
    // 直接进入按钮（跳过登录）
    CreateWindowW(L"BUTTON", L"直接进入",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
        280, y, 120, 35, hwnd, (HMENU)IDC_LOGIN_BTN + 100, g_hInst, nullptr);

    // 状态
    CreateWindowW(L"STATIC", L"就绪",
        WS_CHILD | WS_VISIBLE | SS_CENTER,
        50, y + 45, 380, 20, hwnd, (HMENU)IDC_LOGIN_STATUS, g_hInst, nullptr);
}

// ============================================================
// 更新登录状态
// ============================================================
static void UpdateLoginStatus(HWND hwnd, const std::wstring& text) {
    SetWindowTextW(GetDlgItem(hwnd, IDC_LOGIN_STATUS), text.c_str());
}

// ============================================================
// 执行登录
// ============================================================
static bool DoLogin(HWND hwnd) {
    wchar_t user[256], pass[256], server[512];
    GetDlgItemTextW(hwnd, IDC_LOGIN_USER, user, 256);
    GetDlgItemTextW(hwnd, IDC_LOGIN_PASS, pass, 256);
    GetDlgItemTextW(hwnd, IDC_LOGIN_SERVER, server, 512);

    std::string username = WideToUtf8(user);
    std::string password = WideToUtf8(pass);
    g_serverUrl = WideToUtf8(server);

    if (username.empty()) {
        UpdateLoginStatus(hwnd, L"请输入用户名");
        return false;
    }

    g_http->SetServerUrl(g_serverUrl);

    // 先检测服务器连通性（解决连接拒绝问题）
    UpdateLoginStatus(hwnd, L"正在连接服务器...");
    HttpResponse test = g_http->Get("/api/auth/status");
    if (test.statusCode == 0) {
        // 服务器不可达
        std::wstring err = L"无法连接服务器: " + Utf8ToWide(test.error);
        err += L"\n请检查服务器地址或确认后端已启动";
        MessageBoxW(hwnd, err.c_str(), L"连接失败", MB_OK | MB_ICONERROR);
        UpdateLoginStatus(hwnd, L"连接失败");
        return false;
    }

    // 调用登录 API
    UpdateLoginStatus(hwnd, L"正在验证身份...");
    std::string body = "{\"username\":\"" + JsonEscape(username) +
                       "\",\"password\":\"" + JsonEscape(password) + "\"}";
    HttpResponse resp = g_http->Post("/api/auth/login", body);

    if (resp.statusCode == 503) {
        // Supabase 未配置，提示用户
        int choice = MessageBoxW(hwnd,
            L"后端未配置 Supabase 认证。\n是否直接进入成员管理（无身份验证）？",
            L"认证不可用", MB_YESNO | MB_ICONQUESTION);
        if (choice == IDYES) {
            return true;  // 直接进入
        }
        UpdateLoginStatus(hwnd, L"认证不可用");
        return false;
    }

    if (resp.statusCode == 401) {
        UpdateLoginStatus(hwnd, L"用户名或密码错误");
        MessageBoxW(hwnd, L"用户名或密码错误", L"登录失败",
                   MB_OK | MB_ICONWARNING);
        return false;
    }

    if (!resp.success) {
        std::wstring err = L"登录失败: " + Utf8ToWide(resp.error);
        if (!resp.body.empty()) err = Utf8ToWide(resp.body);
        MessageBoxW(hwnd, err.c_str(), L"登录失败", MB_OK | MB_ICONERROR);
        UpdateLoginStatus(hwnd, L"登录失败");
        return false;
    }

    // 登录成功
    UpdateLoginStatus(hwnd, L"登录成功");
    return true;
}

// ============================================================
// 打开成员管理窗口
// ============================================================
static void OpenMembersWindow() {
    // 隐藏登录窗口
    ShowWindow(g_loginHwnd, SW_HIDE);

    // 创建成员管理窗口
    g_membersWin = new MembersWindow(g_hInst, g_http);
    g_membersWin->Show();

    // 在新窗口的消息循环中运行
    // （MembersWindow 的 WM_DESTROY 会 PostQuitMessage）
}

// ============================================================
// 登录窗口过程
// ============================================================
static LRESULT CALLBACK LoginWndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_CREATE:
            CreateLoginControls(hwnd);
            return 0;

        case WM_COMMAND:
            switch (LOWORD(wp)) {
                case IDC_LOGIN_BTN: {
                    // 登录按钮
                    if (DoLogin(hwnd)) {
                        OpenMembersWindow();
                    }
                    return 0;
                }
                case IDC_LOGIN_BTN + 100: {
                    // 直接进入按钮
                    g_http->SetServerUrl(g_serverUrl);
                    // 检测服务器
                    HttpResponse test = g_http->Get("/api/auth/status");
                    if (test.statusCode == 0) {
                        MessageBoxW(hwnd,
                            (L"无法连接服务器: " + Utf8ToWide(test.error)).c_str(),
                            L"连接失败", MB_OK | MB_ICONERROR);
                        return 0;
                    }
                    OpenMembersWindow();
                    return 0;
                }
            }
            return 0;

        case WM_KEYDOWN:
            if (wp == VK_RETURN) {
                if (DoLogin(hwnd)) OpenMembersWindow();
                return 0;
            }
            break;

        case WM_CLOSE:
            DestroyWindow(hwnd);
            return 0;

        case WM_DESTROY:
            PostQuitMessage(0);
            return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

// ============================================================
// WinMain
// ============================================================
int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE, PWSTR, int showCmd) {
    g_hInst = hInst;

    // 初始化公共控件
    INITCOMMONCONTROLSEX icc = {};
    icc.dwSize = sizeof(icc);
    icc.dwICC = ICC_LISTVIEW_CLASSES | ICC_STANDARD_CLASSES;
    InitCommonControlsEx(&icc);

    // 创建 HTTP 客户端
    g_http = new HttpClient(g_serverUrl);

    // 注册登录窗口类
    WNDCLASSEXW wc = {};
    wc.cbSize = sizeof(wc);
    wc.style = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc = LoginWndProc;
    wc.hInstance = hInst;
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.lpszClassName = WC_LOGIN;
    wc.hIcon = LoadIconW(nullptr, IDI_APPLICATION);
    RegisterClassExW(&wc);

    // 创建登录窗口
    int sw = GetSystemMetrics(SM_CXSCREEN);
    int sh = GetSystemMetrics(SM_CYSCREEN);
    int w = 480, h = 320;
    g_loginHwnd = CreateWindowExW(0, WC_LOGIN,
        L"学生会人事管理系统 - 登录",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        (sw - w) / 2, (sh - h) / 2, w, h,
        nullptr, nullptr, hInst, nullptr);

    ShowWindow(g_loginHwnd, showCmd);
    UpdateWindow(g_loginHwnd);

    // 消息循环
    MSG msg;
    while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
        if (g_loginHwnd && IsWindowVisible(g_loginHwnd) &&
            IsDialogMessageW(g_loginHwnd, &msg)) {
            continue;
        }
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }

    // 清理
    delete g_http;
    if (g_membersWin) delete g_membersWin;
    return (int)msg.wParam;
}
