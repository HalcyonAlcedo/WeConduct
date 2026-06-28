; --- WeConduct NSIS Installer ----------------------------------
; 构建时通过 -D 传入 VERSION、SOURCE_DIR、OUTPUT_FILE

!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef SOURCE_DIR
  !define SOURCE_DIR "dist\WeConduct"
!endif
!ifndef OUTPUT_FILE
  !define OUTPUT_FILE "WeConduct-setup.exe"
!endif

Unicode true
Name "WeConduct"
OutFile "${OUTPUT_FILE}"
InstallDir "$PROGRAMFILES\WeConduct"
RequestExecutionLevel admin

; --- UI ---
!include "MUI2.nsh"
!define MUI_ICON "..\..\assets\icons\weconduct.ico"
!define MUI_UNICON "..\..\assets\icons\weconduct.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

; --- Install ---
Section "Install"
  SetOutPath "$INSTDIR"

  ; Copy all bundled files
  File /r "${SOURCE_DIR}\*.*"

  ; Desktop shortcut
  CreateShortCut "$DESKTOP\WeConduct.lnk" "$INSTDIR\WeConduct.exe"

  ; Start Menu
  CreateDirectory "$SMPROGRAMS\WeConduct"
  CreateShortCut "$SMPROGRAMS\WeConduct\WeConduct.lnk" "$INSTDIR\WeConduct.exe"
  CreateShortCut "$SMPROGRAMS\WeConduct\卸载.lnk" "$INSTDIR\Uninstall.exe"

  ; Write uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Registry for Add/Remove Programs
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeConduct" \
    "DisplayName" "WeConduct"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeConduct" \
    "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeConduct" \
    "Publisher" "WeConduct"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeConduct" \
    "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeConduct" \
    "DisplayIcon" "$INSTDIR\WeConduct.exe"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeConduct" \
    "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeConduct" \
    "NoRepair" 1
SectionEnd

; --- Uninstall ---
Section "Uninstall"
  Delete "$DESKTOP\WeConduct.lnk"
  RMDir /r "$SMPROGRAMS\WeConduct"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeConduct"
SectionEnd
