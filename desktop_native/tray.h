#pragma once
#include <windows.h>
#include <string>
#include <functional>

// 系统托盘管理（Shell_NotifyIcon）
class TrayManager {
public:
    // 窗口句柄 + 自定义消息 ID（用于托盘图标回调）
    TrayManager(HWND hwnd, UINT callbackMsg);
    ~TrayManager();

    // 添加托盘图标，iconPath 为 .ico 文件路径
    bool Add(const std::wstring& iconPath, const std::wstring& tip);
    // 更新提示文字
    void UpdateTip(const std::wstring& tip);
    // 显示气泡通知（系统托盘通知区域）
    void ShowBalloon(const std::wstring& title, const std::wstring& body);
    // 移除托盘图标
    void Remove();
    // 弹出右键菜单（在指定坐标）
    void ShowContextMenu(HWND hwnd, int x, int y);

    // 菜单项回调
    std::function<void()> onShowWindow;
    std::function<void()> onToggleWindow;
    std::function<void()> onSettings;
    std::function<void()> onQuit;

    bool IsVisible() const { return m_visible; }

private:
    HWND m_hwnd;
    UINT m_callbackMsg;
    bool m_visible;
    HMENU m_menu;
};
