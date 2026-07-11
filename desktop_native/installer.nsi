; ==========================================================
;  学生会人事管理系统 —— NSIS 安装程序脚本
;  使用 LZMA 压缩，将所有文件打包为单一安装程序
;  目标：安装程序体积 < 100MB（实际约 15-25MB）
; ==========================================================
!include "MUI2.nsh"
!include "LogicLib.nsh"

Name "学生会人事管理系统"
OutFile "学生会人事管理系统_安装程序.exe"
Unicode true

; LZMA 固实压缩（极致压缩率，可将 Python 运行时等大幅压缩）
SetCompressor /SOLID lzma
SetCompressorDictSize 64

InstallDir "$LOCALAPPDATA\HGStudentsUnion"
RequestExecutionLevel user
ShowInstDetails show
ShowUnInstDetails show

; ==========================================================
; MUI 界面配置
; ==========================================================
!define MUI_ICON "school-logo.ico"
!define MUI_UNICON "school-logo.ico"
!define MUI_ABORTWARNING

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

; ==========================================================
; 安装内容
; ==========================================================
Section "主程序" SecMain
  SectionIn RO

  SetOutPath "$INSTDIR"

  ; --- C++ 原生主程序 ---
  File "build\bin\学生会人事管理系统.exe"

  ; --- WebView2 加载器（如系统未内置则使用）---
  File "WebView2Loader.dll"

  ; --- 前端页面 + 图标 ---
  File "..\index.html"
  File "..\school-logo.png"

  ; --- Flask 后端 ---
  File "..\main.py"

  ; --- Python 嵌入式运行时（约 10MB，LZMA 后约 4MB）---
  File /r "python\*.*"

  ; --- 依赖包 ---
  File /r "site-packages\*.*"

  ; --- 创建快捷方式 ---
  CreateDirectory "$SMPROGRAMS\学生会人事管理系统"
  CreateShortcut "$SMPROGRAMS\学生会人事管理系统\学生会人事管理系统.lnk" \
    "$INSTDIR\学生会人事管理系统.exe"
  CreateShortcut "$SMPROGRAMS\学生会人事管理系统\卸载.lnk" \
    "$INSTDIR\uninstall.exe"
  CreateShortcut "$DESKTOP\学生会人事管理系统.lnk" \
    "$INSTDIR\学生会人事管理系统.exe"

  ; --- 注册卸载信息 ---
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\HGStudentsUnion" \
    "DisplayName" "学生会人事管理系统"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\HGStudentsUnion" \
    "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\HGStudentsUnion" \
    "DisplayIcon" "$INSTDIR\学生会人事管理系统.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\HGStudentsUnion" \
    "Publisher" "学生会"

SectionEnd

; ==========================================================
; 卸载
; ==========================================================
Section "Uninstall"
  SetOutPath "$TEMP"

  ; 删除文件
  Delete "$INSTDIR\学生会人事管理系统.exe"
  Delete "$INSTDIR\WebView2Loader.dll"
  Delete "$INSTDIR\index.html"
  Delete "$INSTDIR\school-logo.png"
  Delete "$INSTDIR\main.py"
  Delete "$INSTDIR\uninstall.exe"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\site-packages"

  ; 删除快捷方式
  Delete "$DESKTOP\学生会人事管理系统.lnk"
  RMDir /r "$SMPROGRAMS\学生会人事管理系统"

  ; 删除安装目录
  RMDir "$INSTDIR"

  ; 删除注册表
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\HGStudentsUnion"

SectionEnd
