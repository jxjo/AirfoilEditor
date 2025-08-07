@echo off

set PACKAGE_NAME=airfoileditor
set ICON=../modules/AE_ico.ico
set STARTER_NAME=AE_starter

echo.
echo Create starter '%STARTER_NAME%' for package exe '%PACKAGE_NAME%' having icon '%ICON%'
echo.
pause 

rem -- create resource file for icon

echo IDI_ICON ICON "%ICON%"  > %STARTER_NAME%.rc
windres %STARTER_NAME%.rc -O coff %STARTER_NAME%.res

rem - compile exe 

gfortran win_starter.f90 %STARTER_NAME%.res -cpp -static -mwindows -DPACKAGE_NAME=\"%PACKAGE_NAME%\" -o %STARTER_NAME% 

del %STARTER_NAME%.res
del %STARTER_NAME%.rc

echo.
echo Move '%STARTER_NAME%' to '..\assests\windows'

copy %STARTER_NAME%.exe ..\assets\windows
del  %STARTER_NAME%.exe 

echo.
pause 
