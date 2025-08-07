!
! Little helper program to start a Python package in Windows.
!
!   - to add an icon resource when linking 
!
program main

    integer                 :: exitstat, nargs
    character(250)          :: arg

#ifndef PACKAGE_NAME
#define PACKAGE_NAME ""
#endif

    if (PACKAGE_NAME == "") then
        print *, "Error: PACKAGE_NAME is not defined"
        stop 1
    end if

    nargs = iargc()
    if (nargs > 0) then
      call get_command_argument (1, arg) 
    else
        arg = ""
    end if

    ! call execute_command_line ("pyw -m "//PACKAGE_NAME//' "'//trim(arg)//'"', exitstat=exitstat) 
    call execute_command_line ("start /b "//PACKAGE_NAME//' "'//trim(arg)//'"', exitstat=exitstat) !wait=.false., doesn't work

    if (exitstat /= 0) then
        print *, "Error: "//PACKAGE_NAME//" command failed with status", exitstat
    end if

end program main    