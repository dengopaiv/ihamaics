@echo off
rem Build sam_render DLLs for both architectures NVDA ships.
rem Usage:  native\build.cmd          (run from anywhere)
setlocal enabledelayedexpansion
set "HERE=%~dp0"
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
echo Using %VSPATH%

if not exist "%HERE%build" mkdir "%HERE%build"

call :build x64 || exit /b 1
call :build x86 || exit /b 1
echo.
echo Done. DLLs in %HERE%build
exit /b 0

:build
echo === building %1 ===
setlocal
call "%VSPATH%\VC\Auxiliary\Build\vcvarsall.bat" %1 >nul || exit /b 1
cd /d "%HERE%build"
cl /nologo /LD /MT /O2 /W4 /WX /DSAM_BUILD_DLL /I "%HERE%include" /I "%HERE%src" "%HERE%src\sam_render.c" "%HERE%src\sam_frames.c" "%HERE%src\sam_tables.c" /Fe:"%HERE%build\sam_render-%1.dll" /link /INCREMENTAL:NO || exit /b 1
endlocal
exit /b 0
