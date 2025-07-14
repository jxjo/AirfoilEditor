@echo off
set airfoil=F3F_hicks_henne
rem is xoptfoil2 in the parent directory? 
 
set localPath=..\..\
if not exist %localPath%Xoptfoil2.exe set localPath=

%localPath%Xoptfoil2 -i %airfoil%.xo2

pause
