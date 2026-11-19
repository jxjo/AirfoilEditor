@echo off

rem ---- install the current repo as (editable) package for development

set CUR_DIR=%cd%

if not exist pyproject.toml cd ..
if not exist pyproject.toml goto end

echo.
echo ------ pip install -e . in %cd%
echo.

python -m pip install -e .

echo.
echo ------ Finished
echo.

:end
cd %CUR_DIR%
pause
