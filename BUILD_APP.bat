@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Build Apple Frames Studio v1.5

set "APP=AppleFramesStudio"
set "ASSET_URL=https://cdn.macstories.net/AppleFrames401.zip"
set "APP_ICON=%CD%\apple_frames_studio.ico"
set "OUT_EXE=%CD%\dist\%APP%.exe"
set "MIN_EXE_SIZE=15000000"

echo ============================================================
echo              APPLE FRAMES STUDIO v1.5 BUILDER
echo ============================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python launcher ^(py.exe^) was not found.
    echo Install Python 3.10+ from https://www.python.org/downloads/windows/
    echo During setup, enable "Add Python to PATH".
    pause
    exit /b 1
)

for /f "tokens=2" %%V in ('py --version 2^>^&1') do echo [OK] Python %%V

echo.
echo [1/5] Installing / updating build dependencies...
py -m pip install --upgrade pip
if errorlevel 1 goto :fail
py -m pip install --upgrade pillow pillow-heif customtkinter pyinstaller
if errorlevel 1 goto :fail

if /I "%~1"=="refresh" goto :download_frames
if exist "Frames.zip" goto :frames_ready

:download_frames
echo.
echo [2/5] Downloading the current Apple Frames 4 asset pack...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '%ASSET_URL%' -OutFile 'Frames.download.zip'; if ((Get-Item 'Frames.download.zip').Length -lt 1000000) { throw 'Downloaded frame archive is unexpectedly small.' }; Move-Item -Force 'Frames.download.zip' 'Frames.zip'"
if errorlevel 1 (
    echo [ERROR] Could not download Frames.zip.
    echo If you already have Frames.zip, place it beside this BAT file and run again.
    pause
    exit /b 1
)

:frames_ready
if not exist "Frames.zip" goto :missing
if not exist "apple_frames_studio.py" goto :missing
if not exist "frames_engine.py" goto :missing
if not exist "%APP_ICON%" goto :missing
if not exist "apple_frames_studio_icon.png" goto :missing
if not exist "version_info.txt" goto :missing
for %%F in ("Frames.zip") do echo [OK] Frame archive ready: %%~zF bytes

echo.
echo [3/5] Cleaning previous build...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "%APP%.spec" del /q "%APP%.spec"

echo.
echo [4/5] Building one-file Windows application...
echo       The custom icon is embedded by PyInstaller during the build.
echo       The finished EXE is NEVER modified afterward.
py -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "%APP%" ^
  --icon "%APP_ICON%" ^
  --version-file "%CD%\version_info.txt" ^
  --collect-all customtkinter ^
  --collect-all pillow_heif ^
  --hidden-import PIL._tkinter_finder ^
  --add-data "Frames.zip;." ^
  --add-data "apple_frames_studio.ico;." ^
  --add-data "apple_frames_studio_icon.png;." ^
  apple_frames_studio.py
if errorlevel 1 goto :fail

if not exist "%OUT_EXE%" (
    echo [ERROR] PyInstaller finished but the EXE was not found.
    goto :fail
)

echo.
echo [5/5] Verifying the finished one-file executable...
for %%F in ("%OUT_EXE%") do set "EXE_SIZE=%%~zF"
echo [INFO] Finished EXE size: !EXE_SIZE! bytes
if !EXE_SIZE! LSS %MIN_EXE_SIZE% (
    echo [ERROR] The output EXE is unexpectedly small.
    echo A valid bundled build should be tens of megabytes because Frames.zip is embedded.
    echo The build will NOT be reported as successful.
    goto :fail
)

rem Verify that PyInstaller can still see its appended PKG/CArchive.
py -m PyInstaller.utils.cliutils.archive_viewer -l "%OUT_EXE%" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] PyInstaller cannot read the embedded archive from the EXE.
    echo The executable would not launch, so this build is rejected.
    goto :fail
)

echo [OK] PyInstaller archive verified.

rem Refresh Explorer's icon cache without touching the executable.
if exist "%SystemRoot%\System32\ie4uinit.exe" (
    "%SystemRoot%\System32\ie4uinit.exe" -ClearIconCache >nul 2>nul
    "%SystemRoot%\System32\ie4uinit.exe" -show >nul 2>nul
)

echo.
echo ============================================================
echo BUILD COMPLETE - VERIFIED
echo.
echo EXE:
echo   %OUT_EXE%
echo.
echo IMPORTANT:
echo   No post-build resource patcher is used in v1.5.
echo   Modifying a PyInstaller one-file EXE after linking can destroy
 echo   its appended PKG archive. The icon is now embedded safely at
 echo   build time from the multi-resolution ICO.
echo ============================================================
start "" "%CD%\dist"
pause
exit /b 0

:missing
echo [ERROR] One or more required project files are missing.
echo Make sure you extracted the full project ZIP before running this BAT.
pause
exit /b 1

:fail
echo.
echo [ERROR] Build failed or verification rejected the generated EXE.
echo Read the messages above for the failing step.
pause
exit /b 1
