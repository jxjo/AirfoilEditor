@echo off

set CUR_DIR=%cd%

if not exist pyproject.toml cd ..
if not exist pyproject.toml goto end

rem ---- get package name and version with hatch https://hatch.pypa.io/latest/cli/reference/

hatch project metadata name > tmpFile 
set /p PACKAGE_NAME= < tmpFile 
hatch project metadata version > tmpFile 
set /p PACKAGE_VERSION= < tmpFile 
del tmpFile 

rem ---- run Pytest  for *-test.py

echo ------ Pytest %PACKAGE_NAME% %PACKAGE_VERSION% 
echo.

Pytest modules\

rem ---- build package - wheel and sdist 

echo.
echo ------ Packaging %PACKAGE_NAME% %PACKAGE_VERSION% into .\dist 
echo.
pause

hatch clean
hatch build

:end
cd %CUR_DIR%
echo.
pause
