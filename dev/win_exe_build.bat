@echo off

setlocal
set CUR_DIR=%cd%
set APP_NAME=airfoileditor
set DIST_DIR=dist


if not exist pyproject.toml cd ..
if not exist pyproject.toml goto end

rem ---- get package name and version with hatch https://hatch.pypa.io/latest/cli/reference/

hatch project metadata name > tmpFile 
set /p PACKAGE_NAME= < tmpFile 
hatch project metadata version > tmpFile 
set /p PACKAGE_VERSION= < tmpFile 
del tmpFile 

set WIN_EXE_DIR=%PACKAGE_NAME%-%PACKAGE_VERSION%_win_exe

rem ---- run Pytest  for *-test.py

echo ------ Pytest %PACKAGE_NAME% %PACKAGE_VERSION% 
echo.
rem Pytest modules\

rem ---- run pyinstaller 

echo.
echo ------ Pyinstaller: Build ...win.exe on %PACKAGE_NAME% %PACKAGE_VERSION% in %DIST_DIR%
echo.

pause

rem needed for pyinstaller to avoid "WARNING: lib not found: api-ms-win-crt ..." 
setlocal
set PATH=%PATH%;C:\Windows\System32\downlevel

rem to show missing imports: 			--debug imports ^
rem also look in modules for imports!: 	--paths modules ^
rem more infos during build:		 	--log-level=INFO
rem suppress console  	--noconsole    ^
pyinstaller --noconfirm --log-level=INFO  --onedir  --noconsole   ^
    --distpath %DIST_DIR% ^
	--icon=./modules/AE_ico.ico ^
	--paths modules ^
    --add-data="./modules/base/icons;./icons" ^
    --add-data="./modules/AE_ico.ico;./icons" ^
    --add-data="./assets/windows/worker.exe;./assets/windows" ^
    --add-data="./assets/windows/xoptfoil2.exe;./assets/windows" ^
    --add-data="./examples_optimize;./examples_optimize" ^
 	--exclude-module matplotlib ^
	--runtime-tmpdir="mySuperTemp" ^
    %APP_NAME%.py 

rem ---- rename target

echo.
echo ------ rename %APP_NAME% in %DIST_DIR%
echo.

cd %DIST_DIR%

if exist %WIN_EXE_DIR% rd /S /Q %WIN_EXE_DIR%
ren %APP_NAME% %WIN_EXE_DIR%

rem ---- zip directory 

echo.
echo ------ zip %WIN_EXE_DIR% in %DIST_DIR%
echo.
pause

if exist %WIN_EXE_DIR%.zip del %WIN_EXE_DIR%.zip
powershell Compress-Archive %WIN_EXE_DIR%\* %WIN_EXE_DIR%.zip

dir


:end
cd %CUR_DIR%
pause