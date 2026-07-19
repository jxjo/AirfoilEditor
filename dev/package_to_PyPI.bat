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

rem ---- upload package - wheel and sdist 

echo.
echo ------ Upload %PACKAGE_NAME% %PACKAGE_VERSION% wheel and sdist to PyPI 
echo.

echo ------ Build fresh wheel and sdist
echo.

hatch build
if %ERRORLEVEL% neq 0 goto end

echo.
dir dist /a:-d |find "%PACKAGE_NAME%-%PACKAGE_VERSION%"
echo.
pause
echo.

hatch publish --user __token__ 
echo.

echo ------ Install the same wheel locally
echo.

for /f "delims=" %%i in ('dir /b dist\%PACKAGE_NAME%-%PACKAGE_VERSION%-py3-none-any.whl') do set WHEEL_FILE=dist\%%i

if not exist "%WHEEL_FILE%" (
	echo ERROR: built wheel not found in dist.
	goto end
)

python -m pip install --force-reinstall --no-deps "%WHEEL_FILE%"
if %ERRORLEVEL% neq 0 goto end

echo.
python -c "import importlib.metadata as m; print(m.version('%PACKAGE_NAME%'))"
echo.

:end
cd %CUR_DIR%
pause
