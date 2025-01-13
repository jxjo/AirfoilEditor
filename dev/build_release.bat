@echo off

set APP_VERSION=3.0 beta
set WIN_RELEASE=AirfoilEditor_%APP_VERSION%_win

echo.
echo ------ Packaging AirfoilEditor windows runtime into %WIN_RELEASE%
echo.
echo.  ? build_win_exe.bat run ?  (in .\dist is actual build version)  
echo.  ? README.pdf ready ?       (in VSCode export readme.md as pdf)
echo.
echo.
pause

cd ..
if     exist releases\%WIN_RELEASE% rd releases\%WIN_RELEASE% /s /q
if     exist releases\%WIN_RELEASE%.zip del releases\%WIN_RELEASE%.zip  /q

mkdir releases\%WIN_RELEASE%

xcopy README.pdf                   releases\%WIN_RELEASE%\               /i /q

xcopy dist\AirfoilEditor           releases\%WIN_RELEASE%\   /s /i /q

pause 

rem ----- zip with powershell ------------
cd releases
powershell Compress-Archive %WIN_RELEASE%\* %WIN_RELEASE%.zip
cd ..
dir releases\%WIN_RELEASE% 
pause