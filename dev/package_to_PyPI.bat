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

rem ---- build package - wheel and sdist 

echo.
echo ------ Upload %PACKAGE_NAME% %PACKAGE_VERSION% wheel and sdist to PyPI 
echo.
dir dist /s /a:-d |find "%PACKAGE_NAME%-%PACKAGE_VERSION%"
echo.
if not exist "dist\%PACKAGE_NAME%-%PACKAGE_VERSION%-py3-none-any.whl" goto end

pause
rem py -m twine upload dist/*
echo.

:end
cd %CUR_DIR%
pause
