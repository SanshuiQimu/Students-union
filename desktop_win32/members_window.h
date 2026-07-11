#pragma once
#include <windows.h>
#include <commctrl.h>
#include <string>
#include <vector>
#include "http_client.h"

// ============================================================
// 成员管理窗口
// ============================================================
class MembersWindow {
public:
    MembersWindow(HINSTANCE hInst, HttpClient* http);
    ~MembersWindow();

    void Show();
    void RefreshList();

    static LRESULT CALLBACK WndProc(HWND, UINT, WPARAM, LPARAM);
    static INT_PTR CALLBACK EditDlgProc(HWND, UINT, WPARAM, LPARAM);

private:
    HINSTANCE m_hInst;
    HWND m_hwnd;
    HWND m_listView;
    HttpClient* m_http;
    std::vector<Member> m_members;

    void OnAdd();
    void OnEdit();
    void OnDelete();
    void OnRefresh();
    int GetSelectedIndex();
    void UpdateStatus(const std::wstring& text);
    void InitListView();
    void PopulateList();

    // 成员编辑对话框
    bool m_editMode;  // true=编辑 false=添加
    Member m_editMember;
};
