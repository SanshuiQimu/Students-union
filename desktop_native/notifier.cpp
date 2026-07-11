// notifier.cpp —— Windows 原生 Toast 通知（通知中心）+ 托盘气回退
#include "notifier.h"
#include "tray.h"
#include <ctime>

// WinRT COM 头文件（用于 Toast 通知中心）
#include <wrl/client.h>
#include <wrl/wrappers/corewrappers.h>
#include <windows.foundation.h>
#include <windows.ui.notifications.h>
#include <windows.data.xml.dom.h>

using namespace Microsoft::WRL;
using namespace Microsoft::WRL::Wrappers;
using namespace ABI::Windows::UI::Notifications;
using namespace ABI::Windows::Data::Xml::Dom;

// 应用 AUMID（通知中心标识）
static const wchar_t* APP_AUMID = L"HGStudentsUnion.Desktop";

Notifier::Notifier() : m_tray(nullptr) {}
Notifier::~Notifier() = default;

bool Notifier::ShouldDedup(const std::wstring& key) {
    double now = (double)time(nullptr);
    auto it = m_recent.find(key);
    if (it != m_recent.end() && (now - it->second) < 5.0) {
        return true;  // 5 秒内重复，跳过
    }
    m_recent[key] = now;
    // 清理过期
    if (m_recent.size() > 50) {
        for (auto it2 = m_recent.begin(); it2 != m_recent.end();) {
            if (now - it2->second > 60) it2 = m_recent.erase(it2);
            else ++it2;
        }
    }
    return false;
}

void Notifier::Show(const std::wstring& title, const std::wstring& body,
                    const std::wstring& iconPath, std::function<void()> onClick) {
    if (ShouldDedup(title)) return;
    if (!TryToast(title, body, iconPath)) {
        FallbackBalloon(title, body);
    }
}

void Notifier::ShowMessages(const std::vector<AppMessage>& messages,
                            const std::wstring& iconPath,
                            std::function<void()> onClick) {
    if (messages.empty()) return;
    if (messages.size() == 1) {
        const auto& m = messages[0];
        Show(m.title, m.body, iconPath, onClick);
    } else {
        Show(L"收到 " + std::to_wstring(messages.size()) + L" 条新消息",
             messages.back().title, iconPath, onClick);
    }
}

bool Notifier::TryToast(const std::wstring& title, const std::wstring& body,
                        const std::wstring& iconPath) {
    // 1. 获取 ToastNotificationManager 静态工厂
    ComPtr<IToastNotificationManagerStatics> manager;
    HRESULT hr = Windows::Foundation::GetActivationFactory(
        HStringReference(RuntimeClass_Windows_UI_Notifications_ToastNotificationManager).Get(),
        &manager);
    if (FAILED(hr) || !manager) return false;

    // 2. 获取 Toast 模板（标题 + 正文）
    ComPtr<IXmlDocument> doc;
    manager->GetTemplateContent(ToastTemplateType::ToastText02, &doc);
    if (!doc) return false;

    // 3. 填充文本节点
    ComPtr<IXmlNodeList> textNodes;
    hr = doc->GetElementsByTagName(HStringReference(L"text").Get(), &textNodes);
    if (FAILED(hr)) return false;

    auto setNodeText = [&](UINT index, const std::wstring& text) -> bool {
        ComPtr<IXmlNode> node;
        if (FAILED(textNodes->Item(index, &node)) || !node) return false;
        // 清空现有子节点
        ComPtr<IXmlNode> firstChild;
        node->get_FirstChild(&firstChild);
        if (firstChild) {
            node->RemoveChild(firstChild.Get(), nullptr);
        }
        // 创建文本节点
        ComPtr<IXmlText> textNode;
        if (FAILED(doc->CreateTextNode(HStringReference(text.c_str()).Get(), &textNode)))
            return false;
        ComPtr<IXmlNode> textNodeIface;
        textNode.As(&textNodeIface);
        ComPtr<IXmlNode> appended;
        node->AppendChild(textNodeIface.Get(), &appended);
        return true;
    };
    if (!setNodeText(0, title)) return false;
    if (!body.empty()) setNodeText(1, body);

    // 4. 添加图标（如果提供）
    if (!iconPath.empty()) {
        ComPtr<IXmlNodeList> imageNodes;
        doc->GetElementsByTagName(HStringReference(L"image").Get(), &imageNodes);
        // ToastText02 无 image，需改为 ToastImageAndText02
    }

    // 5. 创建 Toast 通知
    ComPtr<IToastNotifier> notifier;
    hr = manager->CreateToastNotifierWithId(
        HStringReference(APP_AUMID).Get(), &notifier);
    if (FAILED(hr) || !notifier) return false;

    ComPtr<IToastNotificationFactory> toastFactory;
    hr = Windows::Foundation::GetActivationFactory(
        HStringReference(RuntimeClass_Windows_UI_Notifications_ToastNotification).Get(),
        &toastFactory);
    if (FAILED(hr) || !toastFactory) return false;

    ComPtr<IToastNotification> toast;
    hr = toastFactory->CreateToastNotification(doc.Get(), &toast);
    if (FAILED(hr) || !toast) return false;

    // 6. 显示通知
    hr = notifier->Show(toast.Get());
    return SUCCEEDED(hr);
}

void Notifier::FallbackBalloon(const std::wstring& title, const std::wstring& body) {
    if (m_tray) {
        m_tray->ShowBalloon(title, body);
    }
}
