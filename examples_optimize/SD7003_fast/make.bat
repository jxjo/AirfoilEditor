@echo off
set airfoil=SD7003_fast

rem is Xoptfoil2 in the parent directory? 
 
set localPath=..\..\
if not exist %localPath%xoptfoil2.exe set localPath=

%localPath%xoptfoil2 -i %airfoil%.xo2 -o %airfoil%

pause


