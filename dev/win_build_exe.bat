@echo off
setlocal

if not exist pyproject.toml cd ..
if not exist pyproject.toml (
  echo ERROR: pyproject.toml not found.
  pause
  exit /b 1
)

python dev\win_build.py exe
set ERR=%ERRORLEVEL%

pause
exit /b %ERR%