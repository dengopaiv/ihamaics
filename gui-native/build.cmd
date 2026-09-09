@echo off
rem Build the native SAM GUI: one self-contained exe, no Python.
rem Usage:  gui-native\build.cmd [x64|x86]      (default x64)
setlocal enabledelayedexpansion
set "HERE=%~dp0"
set "ROOT=%HERE%.."
set "ARCH=%~1"
if "%ARCH%"=="" set "ARCH=x64"

set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "!VSWHERE!" (
    echo ERROR: vswhere.exe not found - is Visual Studio installed?
    exit /b 1
)
set "VSPATH="
for /f "usebackq tokens=*" %%i in (`"!VSWHERE!" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSPATH=%%i"
if not defined VSPATH (
    echo ERROR: no MSVC C++ toolset found. Install "Desktop development with C++".
    exit /b 1
)

if not exist "%ROOT%\native\data\sam.dict" (
    echo ERROR: native\data\sam.dict is missing.
    echo Run:  python native\tools\gen_dict.py
    exit /b 1
)

if not exist "%HERE%build" mkdir "%HERE%build"

call "%VSPATH%\VC\Auxiliary\Build\vcvarsall.bat" %ARCH% >nul || exit /b 1
cd /d "%HERE%build"

echo === compiling resources (%ARCH%) ===
rc /nologo /fo "%HERE%build\sam_gui.res" /i "%HERE%." "%HERE%sam_gui.rc" || exit /b 1

echo === compiling and linking (%ARCH%) ===
rem /MT so the exe carries the CRT and needs no redistributable.
cl /nologo /EHsc /MT /O2 /W4 /WX /DUNICODE /D_UNICODE ^
   /I "%ROOT%\native\include" /I "%ROOT%\native\src" /I "%HERE%." ^
   "%HERE%sam_gui.cpp" ^
   "%ROOT%\native\src\sam_render.c" ^
   "%ROOT%\native\src\sam_frames.c" ^
   "%ROOT%\native\src\sam_tables.c" ^
   "%ROOT%\native\src\sam_text.c" ^
   "%ROOT%\native\src\sam_parser.c" ^
   "%ROOT%\native\src\sam_reciter.c" ^
   "%ROOT%\native\src\sam_parser_tables.c" ^
   "%ROOT%\native\src\sam_reciter_tables.c" ^
   "%ROOT%\native\src\sam_cmudict_tables.c" ^
   /Fe:"%HERE%build\sam_gui-%ARCH%.exe" ^
   /link /SUBSYSTEM:WINDOWS /INCREMENTAL:NO "%HERE%build\sam_gui.res" || exit /b 1

echo.
echo Done: %HERE%build\sam_gui-%ARCH%.exe
for %%F in ("%HERE%build\sam_gui-%ARCH%.exe") do echo Size: %%~zF bytes
exit /b 0
