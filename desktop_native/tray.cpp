// tray.cpp —— 系统托盘实现（Shell_NotifyIcon）
#include "tray.h"
#include <shellapi.h>
#include <strsafe.h>
#include <gdiplus.h>
#pragma comment(lib, "gdiplus.lib")

// GDI+ 自动初始化 + PNG 图标加载
class GdiplusInit {
    ULONG_PTR token;
public:
    GdiplusInit() {
        Gdiplus::GdiplusStartupInput input;
        Gdiplus::GdiplusStartup(&token, &input, nullptr);
    }
    ~GdiplusInit() { Gdiplus::GdiplusShutdown(token); }
};

// 加载图标（支持 .ico 和 .png）
static HICON LoadIconFromFile(const std::wstring& path) {
    HICON hIcon = (HICON)LoadImageW(nullptr, path.c_str(),
                     IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE);
    if (hIcon) return hIcon;
    // GDI+ 加载 PNG 转 HICON
    static GdiplusInit gdiplus;
    Gdiplus::Bitmap bitmap(path.c_str());
    HICON hIconPng = nullptr;
    bitmap.GetHICON(&hIconPng);
    return hIconPng ? hIconPng : LoadIconW(nullptr, IDI_APPLICATION);
}

TrayManager::TrayManager(HWND hwnd, UINT callbackMsg)
    : m_hwnd(hwnd), m_callbackMsg(callbackMsg), m_visible(false) {
    m_menu = CreatePopupMenu();
}

TrayManager::~TrayManager() {
    Remove();
    if (m_menu) DestroyMenu(m_menu);
}

bool TrayManager::Add(const std::wstring& iconPath, const std::wstring& tip) {
    NOTIFYICONDATAW nid = {};
    nid.cbSize = sizeof(nid);
    nid.hWnd = m_hwnd;
    nid.uID = 1;
    nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
    nid.uCallbackMessage = m_callbackMsg;

    // 加载图标文件（支持 .ico 和 .png）
    HICON hIcon = LoadIconFromFile(iconPath);
    nid.hIcon = hIcon;

    // 提示文字
    StringCchCopyW(nid.szTip, _countof(nid.szTip), tip.c_str());

    m_visible = Shell_NotifyIconW(NIM_ADD, &nid) != 0;
    return m_visible;
}

void TrayManager::UpdateTip(const std::wstring& tip) {
    NOTIFYICONDATAW nid = {};
    nid.cbSize = sizeof(nid);
    nid.hWnd = m_hwnd;
    nid.uID = 1;
    nid.uFlags = NIF_TIP;
    StringCchCopyW(nid.szTip, _countof(nid.szTip), tip.c_str());
    Shell_NotifyIconW(NIM_MODIFY, &nid);
}

void TrayManager::ShowBalloon(const std::wstring& title, const std::wstring& body) {
    NOTIFYICONDATAW nid = {};
    nid.cbSize = sizeof(nid);
    nid.hWnd = m_hwnd;
    nid.uID = 1;
    nid.uFlags = NIF_INFO;
    nid.dwInfoFlags = NIIF_INFO;
    StringCchCopyW(nid.szInfoTitle, _countof(nid.szInfoTitle), title.c_str());
    StringCchCopyW(nid.szInfo, _countof(nid.szInfo), body.c_str());
    Shell_NotifyIconW(NIM_MODIFY, &nid);
}

void TrayManager::Remove() {
    if (!m_visible) return;
    NOTIFYICONDATAW nid = {};
    nid.cbSize = sizeof(nid);
    nid.hWnd = m_hwnd;
    nid.uID = 1;
    Shell_NotifyIconW(NIM_DELETE, &nid);
    m_visible = false;
}

void TrayManager::ShowContextMenu(HWND hwnd, int x, int y) {
    if (!m_menu) return;
    // 重建菜单
    while (GetMenuItemCount(m_menu) > 0)
        DeleteMenu(m_menu, 0, MF_BYPOSITION);

    AppendMenuW(m_menu, MF_STRING, 1, L"显示主窗口");
    AppendMenuW(m_menu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(m_menu, MF_STRING, 2, L"设置...");
    AppendMenuW(m_menu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(m_menu, MF_STRING, 99, L"退出");

    // 必须设置前台窗口，否则菜单可能不消失
    SetForegroundWindow(hwnd);
    int cmd = TrackPopupMenu(m_menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                             x, y, 0, hwnd, nullptr);
    switch (cmd) {
        case 1: if (onShowWindow) onShowWindow(); break;
        case 2: if (onSettings) onSettings(); break;
        case 99: if (onQuit) onQuit(); break;
    }
}
