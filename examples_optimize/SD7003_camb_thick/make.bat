@echo off
set airfoil=SD7003_cdmin

rem is Xoptfoil2 in the parent directory? 
 
set localPath=..\..\
if not exist %localPath%Xoptfoil2.exe set localPath=

%localPath%Xoptfoil2 -i %airfoil%.inp -o %airfoil%_opt

pause


