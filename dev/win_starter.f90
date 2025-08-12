!
! Little helper program to start a Python package in Windows.
!
!   - to add an icon resource when linking 
!
program main

    integer                     :: exitstat, nargs
    character(250)              :: arg, dev_mode_chars
    character (*), parameter    :: DEV_DIR = 'E:\\GitHub\\AirfoilEditor\\'
    logical                     :: dev_mode

#ifndef PACKAGE_NAME
#define PACKAGE_NAME ""
#endif

    if (PACKAGE_NAME == "") then
        print *, "Error: PACKAGE_NAME is not defined"
        stop 1
    end if

    ! check dev_mode - set bei environment variable 'dev_mode' 

    CALL get_environment_variable("dev_mode", dev_mode_chars)
    if (trim(dev_mode_chars) /= "") then
        dev_mode = .true.
    end if
    if (dev_mode) then
        print *, "Development mode is ON"
    else
        print *, "Development mode is OFF"
    end if

    ! get the command line argument, if any

    arg = ""
    nargs = iargc()
    if (nargs > 0) then
      call get_command_argument (1, arg) 
    end if

    ! execute the Python package

    if (.not. dev_mode) then
        ! use 'start /b' to run the package in the background without a console window
        call execute_command_line ("start /b "//PACKAGE_NAME//' "'//trim(arg)//'"', exitstat=exitstat) !wait=.false., doesn't work
        ! call execute_command_line (PACKAGE_NAME//' "'//trim(arg)//'"', exitstat=exitstat) !wait=.false., doesn't work
    else
        ! in development mode, use 'python' to run the package with a console window
        call chdir (DEV_DIR)
        print *, "Changed directory to ", DEV_DIR
        print *, "Executing ","python "//PACKAGE_NAME//'.py "'//trim(arg)//'"' 
        call execute_command_line ("python "//PACKAGE_NAME//'.py "'//trim(arg)//'"', exitstat=exitstat) 
    end if

    if (exitstat /= 0) then
        print *, "Error: "//PACKAGE_NAME//" command failed with status", exitstat
    end if

end program main    