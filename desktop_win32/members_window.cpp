// members_window.cpp —— 成员管理窗口实现
#include "members_window.h"
#include "resource.h"
#include <commctrl.h>
#include <commdlg.h>
#include <sstream>

#pragma comment(lib, "comctl32.lib")

// 成员编辑对话框数据传递
static MembersWindow* g_editCtx = nullptr;

// 动态创建空白对话框模板（无需 .rc 资源文件）
static DLGTEMPLATE* MakeBlankDialog(int w, int h, const wchar_t* title) {
    static BYTE buf[1024];
    memset(buf, 0, sizeof(buf));
    DLGTEMPLATE* dlg = (DLGTEMPLATE*)buf;
    dlg->style = WS_POPUP | WS_CAPTION | WS_SYSMENU | DS_CENTER | DS_SETFONT | DS_MODALFRAME;
    dlg->dwExtendedStyle = 0;
    dlg->cdit = 0;
    dlg->x = 0; dlg->y = 0; dlg->cx = w; dlg->cy = h;
    WORD* p = (WORD*)(dlg + 1);
    *p++ = 0; *p++ = 0;  // menu, class
    while (*title) *p++ = *title++;
    *p++ = 0;
    *p++ = 9; *p++ = 0;  // font size
    const wchar_t* font = L"Microsoft YaHei UI";
    while (*font) *p++ = *font++;
    *p++ = 0;
    return dlg;
}

MembersWindow::MembersWindow(HINSTANCE hInst, HttpClient* http)
    : m_hInst(hInst), m_http(http), m_hwnd(nullptr),
      m_listView(nullptr), m_editMode(false) {}

MembersWindow::~MembersWindow() {
    if (m_hwnd) DestroyWindow(m_hwnd);
}

void MembersWindow::Show() {
    // 创建主窗口
    WNDCLASSEXW wc = {};
    wc.cbSize = sizeof(wc);
    wc.style = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc = WndProc;
    wc.hInstance = m_hInst;
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.lpszClassName = L"HGMembersWindow";
    wc.hIcon = LoadIconW(nullptr, IDI_APPLICATION);
    RegisterClassExW(&wc);

    int sw = GetSystemMetrics(SM_CXSCREEN);
    int sh = GetSystemMetrics(SM_CYSCREEN);
    int w = 900, h = 600;

    m_hwnd = CreateWindowExW(0, L"HGMembersWindow",
        L"学生会人事管理系统 - 成员管理",
        WS_OVERLAPPEDWINDOW,
        (sw - w) / 2, (sh - h) / 2, w, h,
        nullptr, nullptr, m_hInst, this);

    // 存储 this 指针
    SetWindowLongPtrW(m_hwnd, GWLP_USERDATA, (LONG_PTR)this);

    InitListView();

    // 创建按钮
    int btnY = h - 80;
    CreateWindowW(L"BUTTON", L"添加成员",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
        20, btnY, 100, 32, m_hwnd, (HMENU)IDC_BTN_ADD, m_hInst, nullptr);
    CreateWindowW(L"BUTTON", L"编辑",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
        130, btnY, 80, 32, m_hwnd, (HMENU)IDC_BTN_EDIT, m_hInst, nullptr);
    CreateWindowW(L"BUTTON", L"删除",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
        220, btnY, 80, 32, m_hwnd, (HMENU)IDC_BTN_DELETE, m_hInst, nullptr);
    CreateWindowW(L"BUTTON", L"刷新",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
        310, btnY, 80, 32, m_hwnd, (HMENU)IDC_BTN_REFRESH, m_hInst, nullptr);

    // 状态栏
    CreateWindowW(L"STATIC", L"就绪",
        WS_CHILD | WS_VISIBLE | SS_LEFT,
        20, btnY + 38, 400, 20, m_hwnd, (HMENU)IDC_MEMBER_STATUS, m_hInst, nullptr);

    ShowWindow(m_hwnd, SW_SHOW);
    UpdateWindow(m_hwnd);

    // 初始加载
    RefreshList();
}

void MembersWindow::InitListView() {
    m_listView = CreateWindowExW(0, WC_LISTVIEWW, L"",
        WS_CHILD | WS_VISIBLE | LVS_REPORT | LVS_SINGLESEL | LVS_SHOWSELALWAYS | WS_BORDER,
        10, 10, 870, 480, m_hwnd, (HMENU)IDC_MEMBER_LIST, m_hInst, nullptr);

    ListView_SetExtendedListViewStyle(m_listView,
        LVS_EX_FULLROWSELECT | LVS_EX_GRIDLINES);

    // 添加列
    LVCOLUMNW col = {};
    col.mask = LVCF_TEXT | LVCF_WIDTH | LVCF_SUBITEM;

    struct { const wchar_t* name; int width; } cols[] = {
        {L"ID", 50}, {L"姓名", 100}, {L"部门", 120},
        {L"职位", 100}, {L"职责", 250}, {L"入职日期", 120}, {L"离职日期", 120}
    };
    for (int i = 0; i < 7; ++i) {
        col.iSubItem = i;
        col.pszText = (LPWSTR)cols[i].name;
        col.cx = cols[i].width;
        ListView_InsertColumn(m_listView, i, &col);
    }
}

void MembersWindow::RefreshList() {
    if (!m_http) { UpdateStatus(L"未配置服务器"); return; }
    UpdateStatus(L"正在加载成员列表...");
    HttpResponse resp = m_http->GetWithRetry("/api/members", 2);
    if (!resp.success) {
        UpdateStatus(L"加载失败: " + Utf8ToWide(resp.error));
        return;
    }
    m_members = ParseMembers(resp.body);
    PopulateList();
    UpdateStatus(L"已加载 " + std::to_wstring(m_members.size()) + L" 名成员");
}

void MembersWindow::PopulateList() {
    ListView_DeleteAllItems(m_listView);
    for (size_t i = 0; i < m_members.size(); ++i) {
        const auto& m = m_members[i];
        LVITEMW item = {};
        item.mask = LVIF_TEXT;
        item.iItem = (int)i;
        item.iSubItem = 0;
        std::wstring idStr = std::to_wstring(m.id);
        item.pszText = (LPWSTR)idStr.c_str();
        ListView_InsertItem(m_listView, &item);

        ListView_SetItemText(m_listView, (int)i, 1, (LPWSTR)Utf8ToWide(m.name).c_str());
        ListView_SetItemText(m_listView, (int)i, 2, (LPWSTR)Utf8ToWide(m.dept).c_str());
        ListView_SetItemText(m_listView, (int)i, 3, (LPWSTR)Utf8ToWide(m.position).c_str());
        ListView_SetItemText(m_listView, (int)i, 4, (LPWSTR)Utf8ToWide(m.duty).c_str());
        ListView_SetItemText(m_listView, (int)i, 5, (LPWSTR)Utf8ToWide(m.joinDate).c_str());
        ListView_SetItemText(m_listView, (int)i, 6, (LPWSTR)Utf8ToWide(m.leaveDate).c_str());
    }
}

int MembersWindow::GetSelectedIndex() {
    int sel = ListView_GetNextItem(m_listView, -1, LVNI_SELECTED);
    return sel;
}

void MembersWindow::UpdateStatus(const std::wstring& text) {
    SetWindowTextW(GetDlgItem(m_hwnd, IDC_MEMBER_STATUS), text.c_str());
}

void MembersWindow::OnAdd() {
    m_editMode = false;
    m_editMember = Member{};
    g_editCtx = this;
    DLGTEMPLATE* tmpl = MakeBlankDialog(310, 300, L"添加成员");
    DialogBoxIndirectParamW(m_hInst, tmpl, m_hwnd, EditDlgProc, 0);
}

void MembersWindow::OnEdit() {
    int sel = GetSelectedIndex();
    if (sel < 0 || sel >= (int)m_members.size()) {
        MessageBoxW(m_hwnd, L"请先选择一个成员", L"提示", MB_OK | MB_ICONINFORMATION);
        return;
    }
    m_editMode = true;
    m_editMember = m_members[sel];
    g_editCtx = this;
    DLGTEMPLATE* tmpl = MakeBlankDialog(310, 300, L"编辑成员");
    DialogBoxIndirectParamW(m_hInst, tmpl, m_hwnd, EditDlgProc, 0);
}

void MembersWindow::OnDelete() {
    int sel = GetSelectedIndex();
    if (sel < 0 || sel >= (int)m_members.size()) {
        MessageBoxW(m_hwnd, L"请先选择一个成员", L"提示", MB_OK | MB_ICONINFORMATION);
        return;
    }
    const auto& m = m_members[sel];
    std::wstring msg = L"确定删除成员「" + Utf8ToWide(m.name) + L"」吗？";
    if (MessageBoxW(m_hwnd, msg.c_str(), L"确认删除",
        MB_YESNO | MB_ICONQUESTION) != IDYES) return;

    std::string path = "/api/member/" + std::to_string(m.id);
    HttpResponse resp = m_http->Delete(path);
    if (resp.success) {
        UpdateStatus(L"删除成功");
        RefreshList();
    } else {
        MessageBoxW(m_hwnd, Utf8ToWide("删除失败: " + resp.error).c_str(),
                    L"错误", MB_OK | MB_ICONERROR);
    }
}

void MembersWindow::OnRefresh() {
    RefreshList();
}

// ============================================================
// 窗口过程
// ============================================================
LRESULT CALLBACK MembersWindow::WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    MembersWindow* self = (MembersWindow*)GetWindowLongPtrW(hwnd, GWLP_USERDATA);

    switch (msg) {
        case WM_COMMAND: {
            if (!self) break;
            switch (LOWORD(wp)) {
                case IDC_BTN_ADD: self->OnAdd(); break;
                case IDC_BTN_EDIT: self->OnEdit(); break;
                case IDC_BTN_DELETE: self->OnDelete(); break;
                case IDC_BTN_REFRESH: self->OnRefresh(); break;
            }
            return 0;
        }
        case WM_SIZE: {
            if (!self) break;
            // 调整 ListView 和按钮位置
            int w = LOWORD(lp), h = HIWORD(lp);
            MoveWindow(self->m_listView, 10, 10, w - 20, h - 120, TRUE);
            int btnY = h - 80;
            HWND btns[] = {
                GetDlgItem(hwnd, IDC_BTN_ADD),
                GetDlgItem(hwnd, IDC_BTN_EDIT),
                GetDlgItem(hwnd, IDC_BTN_DELETE),
                GetDlgItem(hwnd, IDC_BTN_REFRESH),
            };
            int x = 20;
            for (int i = 0; i < 4; ++i) {
                int w2 = (i == 0) ? 100 : 80;
                MoveWindow(btns[i], x, btnY, w2, 32, TRUE);
                x += w2 + 10;
            }
            MoveWindow(GetDlgItem(hwnd, IDC_MEMBER_STATUS), 20, btnY + 38, 400, 20, TRUE);
            return 0;
        }
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
// 成员编辑对话框（动态创建，无需 .rc 资源文件）
// ============================================================
static HWND s_dlgHwnd = nullptr;

static void CreateEditControls(HWND hwnd, MembersWindow* ctx) {
    // 标签 + 输入框布局
    struct { const wchar_t* label; int id; } fields[] = {
        {L"姓名:", IDC_EDIT_NAME},
        {L"部门:", IDC_EDIT_DEPT},
        {L"职位:", IDC_EDIT_POSITION},
        {L"职责:", IDC_EDIT_DUTY},
        {L"入职日期:", IDC_EDIT_JOINDATE},
        {L"离职日期:", IDC_EDIT_LEAVEDATE},
        {L"密码:", IDC_EDIT_PASS},
    };
    int y = 10;
    HINSTANCE hInst = (HINSTANCE)GetWindowLongPtrW(hwnd, GWLP_HINSTANCE);
    for (int i = 0; i < 7; ++i) {
        CreateWindowW(L"STATIC", fields[i].label,
            WS_CHILD | WS_VISIBLE, 10, y + 3, 70, 18,
            hwnd, nullptr, hInst, nullptr);
        DWORD style = WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL | WS_BORDER;
        if (fields[i].id == IDC_EDIT_PASS) style |= ES_PASSWORD;
        if (fields[i].id == IDC_EDIT_DUTY) style |= ES_MULTILINE | WS_VSCROLL;
        HWND edit = CreateWindowW(L"EDIT", L"",
            style, 90, y,
            (fields[i].id == IDC_EDIT_DUTY) ? 200 : 200,
            (fields[i].id == IDC_EDIT_DUTY) ? 60 : 22,
            hwnd, (HMENU)fields[i].id, hInst, nullptr);

        // 编辑模式时填充现有值
        if (ctx && ctx->m_editMode) {
            const Member& m = ctx->m_editMember;
            const char* val = "";
            switch (fields[i].id) {
                case IDC_EDIT_NAME: val = m.name.c_str(); break;
                case IDC_EDIT_DEPT: val = m.dept.c_str(); break;
                case IDC_EDIT_POSITION: val = m.position.c_str(); break;
                case IDC_EDIT_DUTY: val = m.duty.c_str(); break;
                case IDC_EDIT_JOINDATE: val = m.joinDate.c_str(); break;
                case IDC_EDIT_LEAVEDATE: val = m.leaveDate.c_str(); break;
            }
            SetWindowTextW(edit, Utf8ToWide(val).c_str());
        }
        y += (fields[i].id == IDC_EDIT_DUTY) ? 70 : 30;
    }
    // 按钮
    CreateWindowW(L"BUTTON", L"确定",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
        90, y + 5, 80, 30, hwnd, (HMENU)IDC_EDIT_OK, hInst, nullptr);
    CreateWindowW(L"BUTTON", L"取消",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
        180, y + 5, 80, 30, hwnd, (HMENU)IDC_EDIT_CANCEL, hInst, nullptr);
}

INT_PTR CALLBACK MembersWindow::EditDlgProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_INITDIALOG: {
            // 动态创建控件
            CreateEditControls(hwnd, g_editCtx);
            SetWindowTextW(hwnd, g_editCtx && g_editCtx->m_editMode ? L"编辑成员" : L"添加成员");
            s_dlgHwnd = hwnd;
            return TRUE;
        }
        case WM_COMMAND: {
            if (LOWORD(wp) == IDC_EDIT_CANCEL) {
                EndDialog(hwnd, 0);
                return TRUE;
            }
            if (LOWORD(wp) == IDC_EDIT_OK) {
                if (!g_editCtx) { EndDialog(hwnd, 0); return TRUE; }
                // 读取输入
                wchar_t buf[512];
                Member m = g_editCtx->m_editMode ? g_editCtx->m_editMember : Member{};

                GetDlgItemTextW(hwnd, IDC_EDIT_NAME, buf, 512);
                m.name = WideToUtf8(buf);
                GetDlgItemTextW(hwnd, IDC_EDIT_DEPT, buf, 512);
                m.dept = WideToUtf8(buf);
                GetDlgItemTextW(hwnd, IDC_EDIT_POSITION, buf, 512);
                m.position = WideToUtf8(buf);
                GetDlgItemTextW(hwnd, IDC_EDIT_DUTY, buf, 512);
                m.duty = WideToUtf8(buf);
                GetDlgItemTextW(hwnd, IDC_EDIT_JOINDATE, buf, 512);
                m.joinDate = WideToUtf8(buf);
                GetDlgItemTextW(hwnd, IDC_EDIT_LEAVEDATE, buf, 512);
                m.leaveDate = WideToUtf8(buf);
                GetDlgItemTextW(hwnd, IDC_EDIT_PASS, buf, 512);

                if (m.name.empty()) {
                    MessageBoxW(hwnd, L"请输入姓名", L"提示", MB_OK | MB_ICONWARNING);
                    return TRUE;
                }

                std::string json = MemberToJson(m);
                HttpResponse resp;
                if (g_editCtx->m_editMode) {
                    // 编辑：PUT /api/member/<id>
                    std::string path = "/api/member/" + std::to_string(m.id);
                    resp = g_editCtx->m_http->Put(path, json);
                } else {
                    // 添加：POST /api/members（需要获取现有列表+新成员，整体替换）
                    // 简化：先获取现有列表，追加新成员，整体 POST
                    HttpResponse getList = g_editCtx->m_http->Get("/api/members");
                    std::vector<Member> all = ParseMembers(getList.body);
                    all.push_back(m);
                    // 构建数组 JSON
                    std::string arrJson = "[";
                    for (size_t i = 0; i < all.size(); ++i) {
                        if (i > 0) arrJson += ",";
                        arrJson += MemberToJson(all[i]);
                    }
                    arrJson += "]";
                    resp = g_editCtx->m_http->Post("/api/members", arrJson);
                }

                if (resp.success) {
                    MessageBoxW(hwnd, L"保存成功", L"提示", MB_OK | MB_ICONINFORMATION);
                    EndDialog(hwnd, 1);
                    g_editCtx->RefreshList();
                } else {
                    MessageBoxW(hwnd, Utf8ToWide("保存失败: " + resp.error).c_str(),
                                L"错误", MB_OK | MB_ICONERROR);
                }
                return TRUE;
            }
            break;
        }
        case WM_CLOSE:
            EndDialog(hwnd, 0);
            return TRUE;
    }
    return FALSE;
}
