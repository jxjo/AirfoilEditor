@echo off

echo.
echo ------ clean examples directories 
echo.
pause

set CUR_DIR=%cd%

if not exist pyproject.toml cd ..
if not exist pyproject.toml goto end

cd examples_optimize

if not exist F3B_bezier goto end

cd SD7003_fast
del /q "SD7003_fast.bez" >nul 2>&1
del /q "SD7003_fast.dat" >nul 2>&1
cd ..

cd F3F_hicks_henne
del /q "F3F_hicks_henne.bez" >nul 2>&1
del /q "F3F_hicks_henne.dat" >nul 2>&1
cd ..

cd F3B_bezier
del /q "F3B_bezier.bez" >nul 2>&1
del /q "F3B_bezier.dat" >nul 2>&1
cd ..


echo.
echo ------ remove all run_control files recursively

if not exist F3B_bezier goto end

for /f "delims=" %%F in ('dir /s /b /a:-d run_control 2^>nul') do (
	echo removing %%F
	del /q "%%F" >nul 2>&1
)

echo.
echo ------ remove all *_polars directories recursively
for /d /r %%D in (*_polars) do (
	echo removing %%~fD
	rmdir /s /q "%%~fD" >nul 2>&1
)

echo.
echo ------ remove all *_temp directories recursively
for /d /r %%D in (*_temp) do (
	echo removing %%~fD
	rmdir /s /q "%%~fD" >nul 2>&1
)


pause 

:end
cd %CUR_DIR%
pause