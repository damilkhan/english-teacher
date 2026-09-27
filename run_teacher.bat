@echo off
rem =========================================================
rem  RUN_TEACHER.BAT — запуск English Teacher
rem  Обычный режим : двойной клик (без окна консоли)
rem  Отладка       : run_teacher.bat debug
rem =========================================================
setlocal
cd /d "%~dp0"

if /i "%~1"=="debug" goto debug

rem --- обычный режим: через VBS, чтобы окно консоли не мигало ---
if exist "%~dp0English Teacher.vbs" (
    start "" wscript.exe "%~dp0English Teacher.vbs"
) else (
    start "" pythonw.exe "%~dp0launcher.pyw"
)
exit /b 0

:debug
echo ============================================
echo  Отладочный запуск (с окном консоли)
echo  Лог приложения : logs\app.log
echo  Лог сервера    : logs\llama-server.log
echo ============================================
python "%~dp0launcher.pyw"
echo.
echo -- Код выхода: %ERRORLEVEL% --
pause
exit /b %ERRORLEVEL%
