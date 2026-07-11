#pragma once
#include <string>
#include <vector>

// ============================================================
// 成员数据结构
// ============================================================
struct Member {
    int id = 0;
    std::string name;
    std::string dept;
    std::string position;
    std::string duty;
    std::string joinDate;
    std::string leaveDate;
};

// ============================================================
// HTTP 响应
// ============================================================
struct HttpResponse {
    int statusCode = 0;
    std::string body;
    bool success = false;
    std::string error;
};

// ============================================================
// WinHTTP 客户端（同步，解决连接拒绝：超时+重试）
// ============================================================
class HttpClient {
public:
    HttpClient(const std::string& baseUrl = "http://127.0.0.1:5000");

    HttpResponse Get(const std::string& path);
    HttpResponse Post(const std::string& path, const std::string& body);
    HttpResponse Put(const std::string& path, const std::string& body);
    HttpResponse Delete(const std::string& path);

    // 带重试的请求（解决连接拒绝问题）
    HttpResponse GetWithRetry(const std::string& path, int retries = 3);

    void SetServerUrl(const std::string& url);
    std::string GetServerUrl() const { return m_baseUrl; }

    // 检测服务器是否可达
    static bool IsServerAlive(const std::string& url, int timeoutMs = 2000);

private:
    std::string m_baseUrl;
    HttpResponse DoRequest(const std::string& method,
                           const std::string& path,
                           const std::string& body);
};

// ============================================================
// 简易 JSON 工具
// ============================================================
std::string JsonEscape(const std::string& s);
std::string JsonGetString(const std::string& json, const std::string& key);
int JsonGetInt(const std::string& json, const std::string& key, int def = 0);
bool JsonGetBool(const std::string& json, const std::string& key, bool def = false);
std::vector<Member> ParseMembers(const std::string& json);
std::string MemberToJson(const Member& m);

// ============================================================
// UTF-8 / UTF-16 转换（Win32 控件需要 wchar_t）
// ============================================================
std::wstring Utf8ToWide(const std::string& utf8);
std::string WideToUtf8(const std::wstring& wide);
