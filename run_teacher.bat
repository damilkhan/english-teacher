@echo off
rem =========================================================
rem  RUN_TEACHER.BAT — запуск English Teacher двойным кликом
rem  Обычный режим : двойной клик по этому файлу
rem  Отладка       : run_teacher.bat debug  (с окном консоли)
rem =========================================================
setlocal
cd /d "%~dp0"

rem --- находим pythonw.exe рядом с python.exe (без окна консоли) ---
set "PYDIR="
for /f "delims=" %%i in ('python -c "import sys,os;print(os.path.dirname(sys.executable))" 2^>nul') do set "PYDIR=%%i"

if defined PYDIR if exist "%PYDIR%\pythonw.exe" (
    set "PYW=%PYDIR%\pythonw.exe"
) else (
    set "PYW=pythonw"
)

rem --- режим отладки: запуск в консоли, вывод на экран ---
if /i "%~1"=="debug" (
    echo Debug: запуск launcher.pyw в консоли...
    python launcher.pyw
    echo.
    echo -- Код выхода: %ERRORLEVEL% --
    pause
    exit /b %ERRORLEVEL%
)

rem --- обычный режим: без консоли ---
start "" "%PYW%" "launcher.pyw"
exit /b 0
