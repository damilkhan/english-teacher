' =========================================================
'  English Teacher.vbs — запуск приложения БЕЗ окна консоли
' =========================================================
'  Двойной клик по этому файлу = обычный запуск программы.
'  Окно cmd не появляется вообще: VBS запускает pythonw.exe
'  скрыто (0 = скрытое окно), и весь вывод идёт в logs\.
' =========================================================
Option Explicit

Dim fso, sh, baseDir, pyw, fallback

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = baseDir

' pythonw.exe = тот же Python, но без консоли.
' Сначала ищем его по стандартному пути, потом берём из PATH.
pyw = "pythonw.exe"
fallback = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python310\pythonw.exe"
If fso.FileExists(fallback) Then
    pyw = """" & fallback & """"
End If

If Not fso.FileExists(baseDir & "\launcher.pyw") Then
    MsgBox "Не найден launcher.pyw рядом с этим файлом." & vbCrLf & _
           "Проверьте папку: " & baseDir, 16, "English Teacher"
    WScript.Quit 1
End If

' 0 = скрытое окно, False = не ждать завершения приложения
sh.Run pyw & " ""launcher.pyw""", 0, False
