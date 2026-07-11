// backend.cpp —— 后端启动器 + WinHTTP 网络客户端 + 消息轮询器
#include "backend.h"
#include <winhttp.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <regex>
#include <chrono>

#pragma comment(lib, "winhttp.lib")
#pragma comment(lib, "ws2_32.lib")

// ============================================================
// UTF-8 转换辅助
// ============================================================
static std::wstring Utf8ToWide(const std::string& utf8) {
    if (utf8.empty()) return L"";
    int len = MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(),
                                  (int)utf8.size(), nullptr, 0);
    std::wstring wide(len, 0);
    MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), (int)utf8.size(),
                        &wide[0], len);
    return wide;
}

static std::string WideToUtf8(const std::wstring& wide) {
    if (wide.empty()) return "";
    int len = WideCharToMultiByte(CP_UTF8, 0, wide.c_str(),
                                   (int)wide.size(), nullptr, 0, nullptr, nullptr);
    std::string utf8(len, 0);
    WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), (int)wide.size(),
                        &utf8[0], len, nullptr, nullptr);
    return utf8;
}

// 解析 JSON 字符串中的转义（\" \\ \n \t \uXXXX）
static std::wstring UnescapeJsonString(const std::wstring& s) {
    std::wstring result;
    result.reserve(s.size());
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == L'\\' && i + 1 < s.size()) {
            wchar_t c = s[++i];
            switch (c) {
                case L'"': result += L'"'; break;
                case L'\\': result += L'\\'; break;
                case L'/': result += L'/'; break;
                case L'n': result += L'\n'; break;
                case L't': result += L'\t'; break;
                case L'r': result += L'\r'; break;
                case L'b': result += L'\b'; break;
                case L'f': result += L'\f'; break;
                case L'u': {
                    if (i + 4 < s.size()) {
                        std::wstring hex = s.substr(i + 1, 4);
                        wchar_t ch = (wchar_t)std::stoul(hex, nullptr, 16);
                        result += ch;
                        i += 4;
                    }
                    break;
                }
                default: result += c;
            }
        } else {
            result += s[i];
        }
    }
    return result;
}

// ============================================================
// 简易 JSON 消息解析
// 从 /api/messages 返回的 JSON 数组提取消息列表
// ============================================================
static bool ExtractStringField(const std::wstring& obj,
                                const std::wstring& key, std::wstring& out) {
    std::wstring pattern = L"\"" + key + L"\"";
    size_t pos = obj.find(pattern);
    if (pos == std::wstring::npos) return false;
    pos = obj.find(L':', pos);
    if (pos == std::wstring::npos) return false;
    pos++; // 跳过 ':'
    while (pos < obj.size() && (obj[pos] == L' ' || obj[pos] == L'\t')) pos++;
    if (pos >= obj.size() || obj[pos] != L'"') return false;
    pos++; // 跳过开头引号
    std::wstring raw;
    while (pos < obj.size()) {
        if (obj[pos] == L'\\' && pos + 1 < obj.size()) {
            raw += obj[pos];
            raw += obj[pos + 1];
            pos += 2;
        } else if (obj[pos] == L'"') {
            break;
        } else {
            raw += obj[pos++];
        }
    }
    out = UnescapeJsonString(raw);
    return true;
}

static bool ExtractNumberField(const std::wstring& obj,
                                const std::wstring& key, double& out) {
    std::wstring pattern = L"\"" + key + L"\"";
    size_t pos = obj.find(pattern);
    if (pos == std::wstring::npos) return false;
    pos = obj.find(L':', pos);
    if (pos == std::wstring::npos) return false;
    pos++;
    while (pos < obj.size() && (obj[pos] == L' ' || obj[pos] == L'\t')) pos++;
    std::wstring num;
    while (pos < obj.size() && (iswdigit(obj[pos]) || obj[pos] == L'.' ||
           obj[pos] == L'-' || obj[pos] == L'e' || obj[pos] == L'E')) {
        num += obj[pos++];
    }
    if (num.empty()) return false;
    try { out = std::stod(num); } catch (...) { return false; }
    return true;
}

static bool ExtractBoolField(const std::wstring& obj,
                             const std::wstring& key, bool& out) {
    std::wstring pattern = L"\"" + key + L"\"";
    size_t pos = obj.find(pattern);
    if (pos == std::wstring::npos) return false;
    pos = obj.find(L':', pos);
    if (pos == std::wstring::npos) return false;
    pos++;
    while (pos < obj.size() && (obj[pos] == L' ' || obj[pos] == L'\t')) pos++;
    if (obj.compare(pos, 4, L"true") == 0) { out = true; return true; }
    if (obj.compare(pos, 5, L"false") == 0) { out = false; return true; }
    return false;
}

// 从 JSON 数组提取消息列表
static std::vector<AppMessage> ParseMessagesArray(const std::wstring& json) {
    std::vector<AppMessage> result;
    // 提取所有 {...} 对象
    size_t pos = 0;
    while (true) {
        size_t start = json.find(L'{', pos);
        if (start == std::wstring::npos) break;
        // 匹配配对的大括号
        int depth = 0;
        size_t end = start;
        for (; end < json.size(); ++end) {
            if (json[end] == L'{') depth++;
            else if (json[end] == L'}') {
                depth--;
                if (depth == 0) break;
            }
        }
        if (end >= json.size()) break;
        std::wstring obj = json.substr(start, end - start + 1);

        AppMessage msg;
        double idNum = 0;
        if (ExtractNumberField(obj, L"id", idNum))
            msg.id = std::to_wstring((long long)idNum);
        ExtractStringField(obj, L"to", msg.to);
        ExtractStringField(obj, L"title", msg.title);
        ExtractStringField(obj, L"body", msg.body);
        ExtractBoolField(obj, L"read", msg.read);
        result.push_back(msg);
        pos = end + 1;
    }
    return result;
}

// ============================================================
// BackendLauncher —— 后端启动器
// ============================================================
BackendLauncher::BackendLauncher() {}

BackendLauncher::~BackendLauncher() { Stop(); }

bool BackendLauncher::Start(const std::wstring& pythonExe,
                             const std::wstring& scriptPath, int port) {
    if (m_running.load()) return true;

    std::wstring cmd = pythonExe + L" \"" + scriptPath + L"\"";
    // 设置端口环境变量
    std::wstring env = L"PORT=" + std::to_wstring(port);

    STARTUPINFOW si = {};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;  // 隐藏控制台窗口
    PROCESS_INFORMATION pi = {};

    // 设置环境变量块
    std::wstring envBlock = env + L"\0\0";

    BOOL ok = CreateProcessW(
        nullptr,                           // 应用名
        const_cast<LPWSTR>(cmd.c_str()),   // 命令行
        nullptr, nullptr, FALSE,
        CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT,
        (LPVOID)envBlock.c_str(),          // 环境变量
        nullptr, &si, &pi);
    if (!ok) return false;

    m_hProcess = pi.hProcess;
    m_hThread = pi.hThread;
    m_running = true;
    return true;
}

void BackendLauncher::Stop() {
    if (!m_running.load()) return;
    if (m_hProcess) {
        // 优雅终止：发送 Ctrl+C 信号，然后 TerminateProcess
        TerminateProcess(m_hProcess, 0);
        WaitForSingleObject(m_hProcess, 3000);
        CloseHandle(m_hProcess);
        m_hProcess = nullptr;
    }
    if (m_hThread) {
        CloseHandle(m_hThread);
        m_hThread = nullptr;
    }
    m_running = false;
}

bool BackendLauncher::IsPortOpen(const std::wstring& host, int port, int timeoutMs) {
    WSADATA wsaData;
    static bool wsaInit = false;
    if (!wsaInit) {
        WSAStartup(MAKEWORD(2, 2), &wsaData);
        wsaInit = true;
    }
    SOCKET sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock == INVALID_SOCKET) return false;
    // 设置超时
    DWORD timeout = timeoutMs;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (char*)&timeout, sizeof(timeout));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, (char*)&timeout, sizeof(timeout));

    std::string hostA = WideToUtf8(host);
    struct sockaddr_in addr = {};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((u_short)port);
    inet_pton(AF_INET, hostA.c_str(), &addr.sin_addr);

    int r = connect(sock, (struct sockaddr*)&addr, sizeof(addr));
    closesocket(sock);
    return r == 0;
}

bool BackendLauncher::WaitForReady(int timeoutMs) {
    auto start = std::chrono::steady_clock::now();
    while (true) {
        if (IsPortOpen(AppConfig::BACKEND_HOST, AppConfig::BACKEND_PORT, 500))
            return true;
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - start).count();
        if (elapsed > timeoutMs) return false;
        Sleep(300);
    }
}

// ============================================================
// HttpClient —— WinHTTP 同步客户端（异步封装）
// ============================================================
HttpClient::HttpClient()
    : m_userAgent(L"HGStudentsUnion-Desktop/1.0") {}
HttpClient::~HttpClient() {}

void HttpClient::GetAsync(const std::wstring& url,
                          std::function<void(int, const std::wstring&)> onDone,
                          int timeoutMs) {
    std::thread([this, url, onDone, timeoutMs]() {
        int statusCode = 0;
        std::wstring body;

        // 解析 URL
        URL_COMPONENTSW uc = {};
        wchar_t hostName[256] = {};
        wchar_t urlPath[2048] = {};
        uc.dwStructSize = sizeof(uc);
        uc.lpszHostName = hostName;
        uc.dwHostNameLength = 256;
        uc.lpszUrlPath = urlPath;
        uc.dwUrlPathLength = 2048;
        WinHttpCrackUrl(url.c_str(), 0, 0, &uc);

        HINTERNET hSession = WinHttpOpen(m_userAgent.c_str(),
            WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
            WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
        if (!hSession) { if (onDone) onDone(0, L""); return; }

        WinHttpSetTimeouts(hSession, timeoutMs, timeoutMs,
                           timeoutMs, timeoutMs);

        HINTERNET hConnect = WinHttpConnect(hSession, uc.lpszHostName,
            uc.nPort, (uc.nScheme == INTERNET_SCHEME_HTTPS) ? 1 : 0);
        if (!hConnect) { WinHttpCloseHandle(hSession); if (onDone) onDone(0, L""); return; }

        HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"GET",
            uc.lpszUrlPath, nullptr, WINHTTP_NO_REFERER,
            WINHTTP_DEFAULT_ACCEPT_TYPES,
            (uc.nScheme == INTERNET_SCHEME_HTTPS) ? WINHTTP_FLAG_SECURE : 0);
        if (!hRequest) {
            WinHttpCloseHandle(hConnect); WinHttpCloseHandle(hSession);
            if (onDone) onDone(0, L""); return;
        }

        BOOL bRes = WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS,
            0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0);
        if (bRes) {
            bRes = WinHttpReceiveResponse(hRequest, nullptr);
        }

        if (bRes) {
            // 状态码
            DWORD code = 0, codeSize = sizeof(code);
            WinHttpQueryHeaders(hRequest,
                WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                WINHTTP_HEADER_NAME_BY_INDEX, &code, &codeSize, WINHTTP_NO_HEADER_INDEX);
            statusCode = (int)code;

            // 读取响应体
            DWORD bytesAvail = 0, bytesRead = 0;
            std::string rawBody;
            do {
                bytesAvail = 0;
                if (!WinHttpQueryDataAvailable(hRequest, &bytesAvail)) break;
                if (bytesAvail == 0) break;
                std::vector<char> buf(bytesAvail + 1, 0);
                if (!WinHttpReadData(hRequest, buf.data(), bytesAvail, &bytesRead))
                    break;
                rawBody.append(buf.data(), bytesRead);
            } while (bytesRead > 0);
            body = Utf8ToWide(rawBody);
        }

        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);

        if (onDone) onDone(statusCode, body);
    }).detach();
}

// ============================================================
// MessagePoller —— 后台消息轮询器
// ============================================================
MessagePoller::MessagePoller() {}
MessagePoller::~MessagePoller() { Stop(); }

void MessagePoller::Start(const std::wstring& serverUrl,
                           const std::wstring& username) {
    m_serverUrl = serverUrl;
    m_username = username;
    if (m_running.load()) return;
    m_running = true;
    m_failCount = 0;
    m_thread = std::thread(&MessagePoller::PollLoop, this);
}

void MessagePoller::Stop() {
    m_running = false;
    if (m_thread.joinable()) m_thread.join();
}

void MessagePoller::PollLoop() {
    if (onStateChanged) onStateChanged(L"connected");
    while (m_running.load()) {
        DoPoll();
        if (!m_running.load()) break;
        // 计算下次等待时间
        int waitMs = AppConfig::POLL_INTERVAL_MS;
        if (m_failCount > 0) {
            // 指数退避：2^n * 2s，上限 60s
            waitMs = std::min(
                (1 << std::min(m_failCount, 6)) * 2000,
                AppConfig::RECONNECT_MAX_MS);
        }
        // 分段 Sleep 以便快速响应停止
        for (int i = 0; i < waitMs / 200 && m_running.load(); ++i)
            Sleep(200);
    }
}

void MessagePoller::DoPoll() {
    if (m_serverUrl.empty() || m_username.empty()) return;

    std::wstring url = m_serverUrl + L"/api/messages";
    m_http.GetAsync(url, [this](int code, const std::wstring& body) {
        if (code != 200) {
            m_failCount++;
            if (onStateChanged) onStateChanged(L"reconnecting");
            return;
        }
        // 重置失败计数
        if (m_failCount > 0) {
            m_failCount = 0;
            if (onStateChanged) onStateChanged(L"connected");
        }
        // 解析消息
        auto allMsgs = ParseMessagesArray(body);
        // 过滤给当前用户的新消息
        std::vector<AppMessage> newMsgs;
        for (const auto& m : allMsgs) {
            if (m.to != m_username) continue;
            if (IsNew(m.id) && !m.read) {
                newMsgs.push_back(m);
            }
        }
        if (!newMsgs.empty() && onNewMessages) {
            onNewMessages(newMsgs);
        }
    }, AppConfig::REQUEST_TIMEOUT_MS);
}

bool MessagePoller::IsNew(const std::wstring& id) {
    if (id.empty()) return false;
    for (const auto& seen : m_seenIds) {
        if (seen == id) return false;
    }
    m_seenIds.push_back(id);
    // 限制大小
    if (m_seenIds.size() > 500) m_seenIds.erase(m_seenIds.begin());
    return true;
}
