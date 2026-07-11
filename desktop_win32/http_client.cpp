// http_client.cpp —— WinHTTP 客户端 + JSON 解析 + UTF 转换
#include "http_client.h"
#include <windows.h>
#include <winhttp.h>
#include <sstream>
#include <algorithm>

#pragma comment(lib, "winhttp.lib")

// ============================================================
// UTF-8 / UTF-16 转换
// ============================================================
std::wstring Utf8ToWide(const std::string& utf8) {
    if (utf8.empty()) return L"";
    int len = MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), (int)utf8.size(), nullptr, 0);
    std::wstring wide(len, 0);
    MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), (int)utf8.size(), &wide[0], len);
    return wide;
}

std::string WideToUtf8(const std::wstring& wide) {
    if (wide.empty()) return "";
    int len = WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), (int)wide.size(),
                                  nullptr, 0, nullptr, nullptr);
    std::string utf8(len, 0);
    WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), (int)wide.size(),
                        &utf8[0], len, nullptr, nullptr);
    return utf8;
}

// ============================================================
// HttpClient 实现
// ============================================================
HttpClient::HttpClient(const std::string& baseUrl) : m_baseUrl(baseUrl) {
    // 确保 base URL 无尾斜杠
    if (!m_baseUrl.empty() && m_baseUrl.back() == '/')
        m_baseUrl.pop_back();
}

void HttpClient::SetServerUrl(const std::string& url) {
    m_baseUrl = url;
    if (!m_baseUrl.empty() && m_baseUrl.back() == '/')
        m_baseUrl.pop_back();
}

// 解析 URL，提取 host/port/path/scheme
struct UrlParts {
    std::wstring host;
    int port = 80;
    std::wstring path = L"/";
    bool https = false;
};

static UrlParts ParseUrl(const std::string& url) {
    UrlParts p;
    std::string u = url;
    if (u.substr(0, 8) == "https://") { p.https = true; u = u.substr(8); p.port = 443; }
    else if (u.substr(0, 7) == "http://") { u = u.substr(7); }
    // 分割 host:port / path
    size_t slash = u.find('/');
    std::string hostport = (slash == std::string::npos) ? u : u.substr(0, slash);
    if (slash != std::string::npos) p.path = Utf8ToWide(u.substr(slash));
    else p.path = L"/";
    // host:port
    size_t colon = hostport.find(':');
    if (colon != std::string::npos) {
        p.host = Utf8ToWide(hostport.substr(0, colon));
        p.port = std::stoi(hostport.substr(colon + 1));
    } else {
        p.host = Utf8ToWide(hostport);
    }
    return p;
}

HttpResponse HttpClient::DoRequest(const std::string& method,
                                   const std::string& path,
                                   const std::string& body) {
    HttpResponse resp;
    std::string fullUrl = m_baseUrl + path;
    UrlParts parts = ParseUrl(fullUrl);

    HINTERNET hSession = WinHttpOpen(L"HGStudentsUnion/1.0",
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!hSession) { resp.error = "WinHttpOpen failed"; return resp; }

    // 超时设置（解决连接拒绝：连接超时 5s，读取超时 10s）
    WinHttpSetTimeouts(hSession, 5000, 5000, 10000, 10000);

    HINTERNET hConnect = WinHttpConnect(hSession, parts.host.c_str(),
        parts.port, parts.https ? WINHTTP_FLAG_SECURE : 0);
    if (!hConnect) { WinHttpCloseHandle(hSession); resp.error = "WinHttpConnect failed"; return resp; }

    std::wstring methodW = Utf8ToWide(method);
    DWORD flags = parts.https ? WINHTTP_FLAG_SECURE : 0;
    HINTERNET hRequest = WinHttpOpenRequest(hConnect, methodW.c_str(),
        parts.path.c_str(), nullptr, WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES, flags);
    if (!hRequest) {
        WinHttpCloseHandle(hConnect); WinHttpCloseHandle(hSession);
        resp.error = "WinHttpOpenRequest failed"; return resp;
    }

    // 添加请求头
    std::wstring headers = L"Content-Type: application/json\r\n";
    if (!body.empty()) {
        headers += L"Content-Length: " + std::to_wstring(body.size()) + L"\r\n";
    }

    BOOL bSent = WinHttpSendRequest(hRequest, headers.c_str(), (DWORD)-1,
        body.empty() ? WINHTTP_NO_REQUEST_DATA : (LPVOID)body.c_str(),
        (DWORD)body.size(), (DWORD)body.size(), 0);

    if (bSent) bSent = WinHttpReceiveResponse(hRequest, nullptr);

    if (!bSent) {
        DWORD err = GetLastError();
        if (err == 12029) resp.error = "无法连接到服务器";
        else if (err == 12002) resp.error = "请求超时";
        else resp.error = "WinHttp 错误: " + std::to_string(err);
        WinHttpCloseHandle(hRequest); WinHttpCloseHandle(hConnect); WinHttpCloseHandle(hSession);
        return resp;
    }

    // 状态码
    DWORD statusCode = 0, codeSize = sizeof(statusCode);
    WinHttpQueryHeaders(hRequest,
        WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
        WINHTTP_HEADER_NAME_BY_INDEX, &statusCode, &codeSize, WINHTTP_NO_HEADER_INDEX);
    resp.statusCode = (int)statusCode;

    // 读取响应体
    DWORD bytesAvail = 0, bytesRead = 0;
    do {
        bytesAvail = 0;
        if (!WinHttpQueryDataAvailable(hRequest, &bytesAvail)) break;
        if (bytesAvail == 0) break;
        std::vector<char> buf(bytesAvail + 1, 0);
        if (!WinHttpReadData(hRequest, buf.data(), bytesAvail, &bytesRead)) break;
        resp.body.append(buf.data(), bytesRead);
    } while (bytesRead > 0);

    resp.success = (statusCode >= 200 && statusCode < 300);

    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);
    WinHttpCloseHandle(hSession);
    return resp;
}

HttpResponse HttpClient::Get(const std::string& path) {
    return DoRequest("GET", path, "");
}

HttpResponse HttpClient::Post(const std::string& path, const std::string& body) {
    return DoRequest("POST", path, body);
}

HttpResponse HttpClient::Put(const std::string& path, const std::string& body) {
    return DoRequest("PUT", path, body);
}

HttpResponse HttpClient::Delete(const std::string& path) {
    return DoRequest("DELETE", path, "");
}

// 带重试的 GET（解决连接拒绝：自动重试）
HttpResponse HttpClient::GetWithRetry(const std::string& path, int retries) {
    HttpResponse resp;
    for (int i = 0; i <= retries; ++i) {
        resp = Get(path);
        if (resp.success) return resp;
        if (i < retries) {
            // 指数退避等待
            int waitMs = (i + 1) * 1000;
            Sleep(waitMs);
        }
    }
    return resp;
}

bool HttpClient::IsServerAlive(const std::string& url, int timeoutMs) {
    HttpClient client(url);
    HttpResponse r = client.Get("/api/members");
    return r.statusCode > 0;
}

// ============================================================
// JSON 工具实现
// ============================================================
std::string JsonEscape(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 10);
    for (char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default: out += c;
        }
    }
    return out;
}

// 在 JSON 字符串中查找字段值（简易实现）
static size_t FindField(const std::string& json, const std::string& key) {
    std::string needle = "\"" + key + "\"";
    size_t pos = json.find(needle);
    if (pos == std::string::npos) return std::string::npos;
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) return std::string::npos;
    return pos + 1;
}

std::string JsonGetString(const std::string& json, const std::string& key) {
    size_t pos = FindField(json, key);
    if (pos == std::string::npos) return "";
    // 跳过空白
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;
    if (pos >= json.size() || json[pos] != '"') return "";
    pos++; // 跳过开头引号
    std::string result;
    while (pos < json.size()) {
        if (json[pos] == '\\' && pos + 1 < json.size()) {
            char c = json[pos + 1];
            switch (c) {
                case '"': result += '"'; break;
                case '\\': result += '\\'; break;
                case 'n': result += '\n'; break;
                case 't': result += '\t'; break;
                case 'r': result += '\r'; break;
                case '/': result += '/'; break;
                default: result += c;
            }
            pos += 2;
        } else if (json[pos] == '"') {
            break;
        } else {
            result += json[pos++];
        }
    }
    return result;
}

int JsonGetInt(const std::string& json, const std::string& key, int def) {
    size_t pos = FindField(json, key);
    if (pos == std::string::npos) return def;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;
    std::string num;
    while (pos < json.size() && (isdigit((unsigned char)json[pos]) ||
           json[pos] == '-' || json[pos] == '.')) {
        num += json[pos++];
    }
    if (num.empty()) return def;
    try { return std::stoi(num); } catch (...) { return def; }
}

bool JsonGetBool(const std::string& json, const std::string& key, bool def) {
    size_t pos = FindField(json, key);
    if (pos == std::string::npos) return def;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;
    if (json.compare(pos, 4, "true") == 0) return true;
    if (json.compare(pos, 5, "false") == 0) return false;
    return def;
}

std::vector<Member> ParseMembers(const std::string& json) {
    std::vector<Member> result;
    // 提取所有 {...} 对象
    size_t pos = 0;
    while (true) {
        size_t start = json.find('{', pos);
        if (start == std::string::npos) break;
        // 配对大括号
        int depth = 0;
        size_t end = start;
        for (; end < json.size(); ++end) {
            if (json[end] == '{') depth++;
            else if (json[end] == '}') { depth--; if (depth == 0) break; }
        }
        if (end >= json.size()) break;
        std::string obj = json.substr(start, end - start + 1);

        Member m;
        m.id = JsonGetInt(obj, "id", 0);
        m.name = JsonGetString(obj, "name");
        m.dept = JsonGetString(obj, "dept");
        m.position = JsonGetString(obj, "position");
        m.duty = JsonGetString(obj, "duty");
        m.joinDate = JsonGetString(obj, "joinDate");
        m.leaveDate = JsonGetString(obj, "leaveDate");
        result.push_back(m);
        pos = end + 1;
    }
    return result;
}

std::string MemberToJson(const Member& m) {
    std::ostringstream ss;
    ss << "{";
    ss << "\"id\":" << m.id << ",";
    ss << "\"name\":\"" << JsonEscape(m.name) << "\",";
    ss << "\"dept\":\"" << JsonEscape(m.dept) << "\",";
    ss << "\"position\":\"" << JsonEscape(m.position) << "\",";
    ss << "\"duty\":\"" << JsonEscape(m.duty) << "\",";
    ss << "\"joinDate\":\"" << JsonEscape(m.joinDate) << "\",";
    ss << "\"leaveDate\":\"" << JsonEscape(m.leaveDate) << "\"";
    ss << "}";
    return ss.str();
}
