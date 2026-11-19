@echo off

rem ---- install the newest wheel of folder dist as package - see package_build.bat

set CUR_DIR=%cd%

if not exist pyproject.toml cd ..
if not exist pyproject.toml goto end

set WHEEL=
for /f "delims=" %%F in ('dir /b /o-d dist\*.whl 2^>nul') do (
	set WHEEL=%%F
	goto found
)

:found
if "%WHEEL%"=="" (
	echo.
	echo ------ No wheel found in %cd%\dist - run package_build.bat first
	goto end
)

echo.
echo ------ pip install dist\%WHEEL%
echo.

rem uninstall first: an installed version with the same number (or an editable install) would be kept otherwise 
python -m pip uninstall -y airfoileditor
python -m pip install dist\%WHEEL%

echo.
echo ------ Finished
echo.

:end
cd %CUR_DIR%
pause
