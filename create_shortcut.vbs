' =========================================================
'  create_shortcut.vbs — создаёт ярлык «English Teacher» на рабочем столе
'  Запускать один раз: wscript "create_shortcut.vbs"
' =========================================================
Option Explicit

Dim fso, sh, baseDir, target, desktop, link, pyw, icon

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
target  = baseDir & "\English Teacher.vbs"
desktop = sh.SpecialFolders("Desktop")

If Not fso.FileExists(target) Then
    MsgBox "Не найден файл:" & vbCrLf & target, 16, "English Teacher"
    WScript.Quit 1
End If

' Иконка: pythonw.exe (если найдётся), иначе стандартная
pyw = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python310\pythonw.exe"

Set link = sh.CreateShortcut(desktop & "\English Teacher.lnk")
link.TargetPath       = target
link.WorkingDirectory = baseDir
link.Description      = "English Teacher - Jane (локальный ИИ-преподаватель английского)"
link.WindowStyle      = 1
If fso.FileExists(pyw) Then link.IconLocation = pyw & ",0"
link.Save

WScript.Echo "Ярлык создан:" & vbCrLf & desktop & "\English Teacher.lnk"
