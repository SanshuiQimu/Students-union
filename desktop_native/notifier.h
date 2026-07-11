#pragma once
#include <string>
#include <vector>
#include <functional>
#include <unordered_map>
#include "config.h"

class TrayManager;

// Windows 原生 Toast 通知（通知中心）
// 优先使用 WinRT Toast，回退到托盘气球
class Notifier {
public:
    Notifier();
    ~Notifier();

    // 显示通知，iconPath 为应用图标路径（可为空）
    // onClick 为点击回调（可为空）
    void Show(const std::wstring& title, const std::wstring& body,
              const std::wstring& iconPath = L"",
              std::function<void()> onClick = nullptr);

    // 批量消息通知
    void ShowMessages(const std::vector<AppMessage>& messages,
                     const std::wstring& iconPath,
                     std::function<void()> onClick = nullptr);

    // 设置回退托盘（当 Toast 不可用时用气球）
    void SetFallbackTray(class TrayManager* tray) { m_tray = tray; }

private:
    TrayManager* m_tray;
    // 去重：最近通知的 (title) -> 时间戳
    std::unordered_map<std::wstring, double> m_recent;

    bool TryToast(const std::wstring& title, const std::wstring& body,
                  const std::wstring& iconPath);
    void FallbackBalloon(const std::wstring& title, const std::wstring& body);
    bool ShouldDedup(const std::wstring& key);
};
