@echo off
if exist "%SystemRoot%\System32\ie4uinit.exe" (
  "%SystemRoot%\System32\ie4uinit.exe" -ClearIconCache
  "%SystemRoot%\System32\ie4uinit.exe" -show
)
echo Windows icon cache refresh requested.
pause
