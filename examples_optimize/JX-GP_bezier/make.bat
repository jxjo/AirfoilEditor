@echo off
set airfoil=JX-GP_bezier

rem is xoptfoil2 in the parent directory? 
 
set localPath=..\..\
if not exist %localPath%Xoptfoil2.exe set localPath=

%localPath%Xoptfoil2 -i %airfoil%.inp -o %airfoil%_opt

pause
