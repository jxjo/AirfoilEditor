#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Proxies to Xoptfoil2 and Worker 

If the programs aren't in path-environment or in 'assets directory'
the path to program location location must be set 

   Worker.exePath = "xy/z/"
"""


import os
from tempfile       import NamedTemporaryFile
from glob           import glob
from pathlib        import Path

import time 
import shutil
import logging
import datetime 
import fnmatch

from subprocess     import Popen, run, PIPE
if os.name == 'nt':                                 # startupinfo only available in windows environment  
    from subprocess import STARTUPINFO, CREATE_NEW_CONSOLE, STARTF_USESHOWWINDOW, CREATE_NO_WINDOW


import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


SW_NORMAL = 1 
SW_MINIMIZE = 6 

EXE_DIR_WIN    = 'assets/windows'                   # directory of exe files 
EXE_DIR_UNIX   = 'assets/linux'                    

TMP_INPUT_NAME = 'tmp~'                             # temporary input file (~1 will be appended)
TMP_INPUT_EXT  = '.inp'

#------- Helper function -----------------------------------------#

def is_younger (filePath, age_in_seconds): 
    """ returns true if filePathName is younger than age_in_seconds """

    younger = False 

    if os.path.isfile (filePath):
        now         = datetime.datetime.now()
        last_update = datetime.datetime.fromtimestamp(os.path.getmtime(filePath))
        tdelta = now - last_update
        seconds = tdelta.total_seconds()
        younger =  seconds < age_in_seconds

    return younger


def file_in_use (filePath):
    """ returns True if file is in use by another process"""
    
    in_use = False

    if os.path.exists(filePath):
        try:
            os.rename(filePath, filePath)
        except OSError as e:
            logger.warning (f"File {filePath} in use by another process")
            in_use = True 

    return in_use 



#------------------------------------------------------------------------------------

class X_Program:
    """ 
    Abstract superclass - Proxy to execute eg Xoptfoil2 and Worker 
    
        self will be executed in 'workingDir' which must be set 
            if it can't be extracted from airfoil path
    """

    NAME        = 'My_Program'
    NAME_EXE    = 'my_program'                             # stem of of exe file 

    version     = ''                                       # version of self - will be set in isReady
    exe_dir     = None                                     # where to find .exe 
    ready       = False                                    # is Worker ready to work 
    ready_msg   = ''                                       # ready or error message 


    def __init__ (self, workingDir : str = None):

        if workingDir and not os.path.isdir (workingDir):
            raise ValueError (f"Working directory '{workingDir}' does not exist" )

        self._workingDir        = workingDir                # directory in which self will be executed
        self._popen : Popen     = None                      # instance of subprocess when async
        self._returncode        = 0                         # returncode when async finished 
        self._pipe_error_lines  = None                      # errortext lines from stderr when finished
        self._pipe_out_lines    = []                        # output lines from stdout when finished

        self._tmp_inpFile       = None                      # tmpfile of this instance, to be deleted 


    def __repr__(self) -> str:
        """ nice representation of self """
        return f"<{type(self).__name__}>"


    @property
    def workingDir (self) -> str: 
        """ directory in which self will be executed"""
        return self._workingDir
    
   
    def isReady (self, project_dir : str, min_version : str = '') -> bool:
        """ 
        checks if self is available with min_version.

        Args: 
            project_dir: directory where there should be ./assets/... 
            min_version: check fpr min version number 
        """

        # ready already checked? 

        if self.ready: return True

        # find .exe

        version_ok = False
        ready_msg  = None 
        cls = self.__class__

        if self.exe_dir is None: 

            exe_dir, ready_msg = self._get_exe_dir (project_dir)

            if exe_dir is None:                                        # self not found anywhere
                cls.ready_msg = ready_msg
                logger.error (ready_msg)
                return 
            else:     
                cls.exe_dir = exe_dir
                logger.debug (ready_msg)

        # try to execute with -h help argument to get version 

        returncode = self._execute ('-h', workingDir=self._get_workingDir(), capture_output=True)


        # extract version and check version
        if returncode == 0 :
            for line in self._pipe_out_lines: 
                words = line.split()

                # first word is program name 
                if len (words) > 1 and words[0] == self.NAME:

                    # last word is version - compare single version numbers
                    cls.version = words[-1]
                    version_ok = True
                    min_nums = min_version.split(".") 

                    if len (min_nums[0]) > 0 :
                        cur_nums = self.version.split(".")
                        for i in range(len(min_nums)): 
                            try: 
                                cur_num = int(cur_nums[i])
                            except: 
                                cur_num = 0 
                            if cur_num < int(min_nums[i]):
                                version_ok = False
                    else: 
                        version_ok = False 
            
            if not version_ok:
                cls.ready_msg = f"wrong version {self.version} - need {min_version}"
            else: 
                cls.ready = True
                cls.ready_msg = f"Ready"

        else: 
            cls.ready_msg = f"{self.NAME_EXE} couldn't be executed"      

        if self.ready: 
            logger.info (f"{self.NAME} {self.version} {self.ready_msg}  (loading from: {self.exe_dir})" )
        else: 
            logger.error (f"{self.ready_msg}  (loading from: {self.exe_dir})" )

        return self.ready
    

    def isRunning (self) -> bool:
        """ still running when async - otherwise False"""

        isRunning = False
        if self._popen is not None: 

            self._popen.poll ()                 # check return code

            if self._popen.returncode is None: 

                isRunning = True

            else: 

                self._returncode       = self._popen.returncode

                new_lines = self._popen.stderr.readlines() if self._popen.stderr else []
                new_lines = [x.rstrip() for x in new_lines]                 # remove \r
                self._pipe_error_lines.extend(new_lines)
                
                new_lines = self._popen.stdout.readlines() if self._popen.stdout else []
                new_lines = [x.rstrip() for x in new_lines]
                self._pipe_out_lines.extend(new_lines)

                if self._returncode:
                    logger.error (f"... {self.NAME_EXE} returncode: {self._returncode} - {'\n'.join (self._pipe_error_lines)}")

                    # put minimum info in error_lines if it isn't standard error return code of Xoptfoil
                    if self._returncode > 1: 
                        self._pipe_error_lines = [f"Process error: {self._returncode}"]

                else: 
                    logger.debug (f"... {self.NAME_EXE} finished {'\n'.join (self._pipe_out_lines)}")
                 
                self._popen = None              # close down process instance 

        return isRunning


    def remove_tmp_file (self, iretry = 0):
        """ os remove of temporary input file"""

        if self._tmp_inpFile and os.path.isfile (self._tmp_inpFile):       # remove tmpfile of worker 
            try: 

                os.remove(self._tmp_inpFile) 
                self._tmp_inpFile = None 

            except OSError as exc: 
                if iretry < 5: 
                    iretry +=1
                    logger.warning (f"{self} Could not delete tmp input file '{self._tmp_inpFile}' - Retry {iretry}")
                    time.sleep (0.1)
                    self.remove_tmp_file (iretry=iretry)
                else: 
                    logger.error (f"Could not delete tmp input file '{self._tmp_inpFile}' - {exc}")
        else:
            self._tmp_inpFile = None


    @property
    def finished_returncode (self): 
        """ returncode of subprocess when finished"""
        return self._returncode


    @property
    def finished_errortext (self): 
        """ errortext from subprocess in case returncode !=0 """

        # scan stderr and stdout for a line with 'Error: ' 

        text = None
        line : str

        if self._pipe_error_lines:
            for line in self._pipe_error_lines:
                _,_,text = line.partition ("Error: ")
                if text: return text 

            # if process was aborted no piped error text from xoptfoil2 - but a minimum message 
            return self._pipe_error_lines[0]

        if self._pipe_out_lines:
            for line in self._pipe_out_lines:
                _,_,text = line.partition ("Error: ")
                if text: return text 

        return text


    def finalize (self):
        """ do cleanup actions """

        self.remove_tmp_file ()


    def terminate (self):
        """ terminate os process of self"""

        if self.isRunning():
            self._popen.terminate()
            self._popen = None 


    # ---------- Private --------------------------------------

    def _execute (self, args = [], workingDir = None, capture_output : bool =False):
        """sync execute self in workingDir 

        Args:
            args: arguments of subprocess as list of strings
            capture_output: capture output in pipe. Defaults to False.
        Returns:
            returncode: = 0 if no error
        """

        if workingDir and not os.path.isdir (workingDir):
            returncode = 1
            logger.error (f"Working directory '{workingDir}' does not exist" )
            return returncode

        returncode  = 0 
        self._pipe_out_lines    = []                        # output lines from stderr when finished
        self._pipe_error_lines  = []                        # errortext lines from stdout when finished

        # build list of args needed by subprocess.run 

        exe = os.path.join (self.exe_dir, self.NAME_EXE) 

        if isinstance (args, list):
            arg_list = [exe] + args
        elif isinstance (args, str):
            arg_list = [exe] + [args]
        else: 
            arg_list = [exe]

        try:

            # uses subproocess run which returns a completed process instance 

            curDir = os.getcwd()
            if workingDir:
                os.chdir (workingDir)

            if capture_output:
                # needed when running as pyinstaller .exe 
                # https://stackoverflow.com/questions/7006238/how-do-i-hide-the-console-when-i-use-os-system-or-subprocess-call/7006424#7006424
                if os.name == 'nt':
                    flags = CREATE_NO_WINDOW    
                else: 
                    flags  = 0                      # posix must be 0       

            logger.info (f"... {self.NAME_EXE} run sync: '{args}' in: {workingDir}")

            process = run (arg_list, text=True, capture_output=capture_output, creationflags=flags)

            returncode  = process.returncode

            if returncode:
                logger.error (f"... {self.NAME_EXE} ended: '{process}'")

            # finished - nice output strings 

            if process.stderr:  
                self._pipe_error_lines = process.stderr.split ("\n")
                logger.error (f"... {self.NAME_EXE} stderr: {"\n".join (self._pipe_error_lines)}")

                if self._pipe_error_lines[0] == "STOP 1":
                    # the error message will be in stdout
                    self._pipe_error_lines = []

            if capture_output and process.stdout: 
                self._pipe_out_lines = process.stdout.split ("\n")
                # logger.debug (f"... {self.NAME_EXE} stdout: {"\n".join (self._pipe_out_lines)}")

        except FileNotFoundError as exc:

            returncode = 1
            self._pipe_error_lines = str(exc)

            logger.error (f"... exception {self.NAME_EXE}: {exc}")

        finally: 

            os.chdir (curDir)

        return  returncode


    def _execute_async (self, args = [], workingDir = None, capture_output : bool =False):
        """async execute self in workingDir 

        Args:
            args: arguments of subprocess as list of strings
            capture_output: capture output in pipe. Defaults to False.
        Returns:
            returncode: = 0 if no error
        """

        if workingDir and not os.path.isdir (workingDir):
            raise ValueError (f"Working directory '{workingDir}' does not exist" )

        returncode  = 0 
        self._pipe_out_lines    = []                        # errortext lines from stderr when finished
        self._pipe_error_lines  = []                        # output lines from stdout when finished

        # build list of args needed by subprocess.run 

        exe = os.path.join (self.exe_dir, self.NAME_EXE) 

        if isinstance (args, list):
            arg_list = [exe] + args
        elif isinstance (args, str):
            arg_list = [exe] + [args]
        else: 
            arg_list = [exe]
        # run either sync or async 

        try:

            # uses subproccess Popen instance to start a subprocess

            curDir = os.getcwd()
            if workingDir:
                os.chdir (workingDir)

            if capture_output:
                stdout = PIPE                               # output is piped to suppress window 
                stderr = PIPE                               # Xoptfoil will write error to stderr
                # needed when running as pyinstaller .exe 
                # https://stackoverflow.com/questions/7006238/how-do-i-hide-the-console-when-i-use-os-system-or-subprocess-call/7006424#7006424
                if os.name == 'nt':
                    flags = CREATE_NO_WINDOW    
                else: 
                    flags  = 0                              # posix must be 0 
                startupinfo = self._get_popen_startupinfo (SW_NORMAL)  
            else: 
                stdout = None 
                stderr = PIPE                               # Xoptfoil will write error to stderr
                if os.name == 'nt':
                    flags  = CREATE_NEW_CONSOLE             # a new console is created (Xoptfoil) 
                else: 
                    flags  = 0                              # posix must be 0 
                startupinfo = self._get_popen_startupinfo (SW_MINIMIZE)  

            logger.info (f"... {self.NAME_EXE} run async: '{args}' in: {workingDir}")

            popen = Popen (arg_list, creationflags=flags, text=True, **startupinfo, 
                                stdout=stdout, stderr=stderr)  

            popen.poll()                            # update returncode

            returncode  = popen.returncode if popen.returncode is not None else 0   # async returns None 

            if returncode:
                logger.error (f"... {self.NAME_EXE} ended: '{popen}'")

                self._pipe_error_lines = popen.stderr.readlines()
                logger.error (f"... {self.NAME_EXE} stderr: {"\n".join (self._pipe_error_lines)}")

            # keep for later poll 
            self._popen = popen 

        except FileNotFoundError as exc:

            returncode = 1
            self._pipe_error_lines = str(exc)

            logger.error (f"... exception {self.NAME_EXE}: {exc}")

        finally: 

            os.chdir (curDir)

        return  returncode



    def _get_popen_startupinfo (self, show : int):
        """ returns popen startinfo parm to eg. minimize shell window - only windows"""

        if os.name == 'nt':
            if show != SW_NORMAL:
                startupinfo = STARTUPINFO()  
                startupinfo.dwFlags |= STARTF_USESHOWWINDOW       
                startupinfo.wShowWindow = show
                return dict(startupinfo=startupinfo)
        return dict(startupinfo=None) 


    def _get_exe_dir (self, project_dir : str): 
        """
        trys to find path to call programName
        
        If found, returns exePath and ready_msg
        If not, return None and ready_msg (error)"""

        exe_dir  = None
        ready_msg = None 

        if os.name == 'nt':
            assets_dir = EXE_DIR_WIN
        else: 
            assets_dir = EXE_DIR_UNIX  

        assets_dir = os.path.normpath (assets_dir)  
        check_dir1 = os.path.join (project_dir , assets_dir)                            # .\modules\assets\...
        check_dir2 = os.path.join (os.path.dirname (project_dir), assets_dir)           # .\assets\...

        if shutil.which (self.NAME_EXE, path=check_dir1) : 
            exe_dir  = os.path.abspath(check_dir1) 
            ready_msg = f"{self.NAME_EXE} found in: {exe_dir}"
        elif shutil.which (self.NAME_EXE, path=check_dir2) : 
            exe_dir  = os.path.abspath(check_dir2) 
            ready_msg = f"{self.NAME_EXE} found in: {exe_dir}"
        else: 
            exe_path = shutil.which (self.NAME_EXE)  
            if exe_path: 
                exe_dir = os.path.dirname (exe_path)
                ready_msg = f"{self.NAME_EXE} using OS search path to execute: {exe_dir}"
            else: 
                ready_msg = f"{self.NAME_EXE} not found either in '{assets_dir}' nor via OS search path" 
        return exe_dir, ready_msg


    def _get_workingDir (self, airfoil_path : str = None) -> str:
        """ 
        returns the actual working dir in which X_Program will be executed
            A workingDir set for self will have presetence, otherwise it is
            retrieved from airfoil_path or os current working dir is taken  
        """

        if self.workingDir:
            return self.workingDir
        elif airfoil_path and os.path.isfile (airfoil_path) : # and os.path.isabs(airfoil_path)
            return os.path.dirname (airfoil_path)
        else:
            return os.getcwd()



# ------------------------------------------------------------



class Xoptfoil2 (X_Program):
    """ 
    Proxy to execute Xoptfoil2
    
        self will be executed in 'workingDir' which must be set if is not current dir
        The 'inputfile' must be in 'workingDir' 
    """

    NAME        = 'Xoptfoil2'
    NAME_EXE    = 'xoptfoil2'                               # stem of of exe file 

    RUN_CONTROL = 'run_control'                             # file name of control file 
    STILL_ALIVE = 10                                        # max. age in seconds of run_control

    RESULT_DIR_POSTFIX = '_temp'                            # result directory of Xoptfoil2 postfix of 'outname'

    @staticmethod
    def remove_resultDir (airfoil_pathFileName : str, only_if_older = False):
        """ 
        deletes the Xoptfoil2 result directory 
        """ 

        resultDir = str(Path(airfoil_pathFileName).with_suffix('')) + Xoptfoil2.RESULT_DIR_POSTFIX
        shutil.rmtree(resultDir, ignore_errors=True)


    @property
    def run_control_filePath (self):
        """ returns filePath of run_control"""
        if self.workingDir: 
            return os.path.join(self.workingDir, Xoptfoil2.RUN_CONTROL)
        else:
            return Xoptfoil2.RUN_CONTROL


    def run (self, outname:str, input_file:str=None, seed_airfoil:str =None):
        """ run self async in self workingDir

        Args:
            outname: output name for generated airfoil
            inputfile: name of input file. Defaults to 'outname'.inp.
            seed_airfoil: optional seed airfoil filename.
        Returns: 
            returncode: = 0 - no errors (which could be retrieved via 'finished_errortext' )
        """

        args = []
        if seed_airfoil  : args.extend(['-a', seed_airfoil])
        if outname       : args.extend(['-o', outname])  
        
        if input_file is None: input_file = outname + '.inp'
        args.extend(['-i', input_file]) 

        # add 'mode' option - will write error to stderr
        args.extend(['-m', 'child']) 

        returncode = self._execute_async (args=args, workingDir=self.workingDir)

        return returncode


    def isRunning (self) -> bool:
        """ 
        - still running?    ... process when async
                            ... otherwise check run_control file if self was started from outside 
        """

        if self._popen:                         # started program myself as process
            running = super().isRunning ()
        else:                                   # Xoptfoil was started from outside 
            running = is_younger (self.run_control_filePath,  Xoptfoil2.STILL_ALIVE)

        if not running and os.path.isfile (self.run_control_filePath):
            # remove old run_control 
            os.remove (self.run_control_filePath)
 
        return running 



    def get_progress (self):
        """ returns no of steps, no of designs and objective function when running otherwise 0,0, 1.0 """

        # format of run_control 
            # !stop
            # !run-info; step: 3; design: 3; fmin:  0.9919478

        steps   = 0 
        designs = 0 
        objFun  = 1.0 
        lines = []

        if os.path.isfile (self.run_control_filePath):
            with open(self.run_control_filePath, 'r') as file:
                lines = file.readlines()
                file.close()

        for line in lines: 
            infos = line.split(";")
            if len(infos) == 4: 
                try: 
                    steps   = int(infos[1].split(":")[1])
                    designs = int(infos[2].split(":")[1])
                    objFun  = float(infos[3].split(":")[1])
                except: 
                    pass

        return steps, designs, objFun


    def stop (self):
        """
        tries to stop self with a 'stop' command in 'run_control' file 
            self must run in 'workingDir'
        """

        with open(self.run_control_filePath, 'w+') as file:
            file.write("stop")
            file.close()


# ------------------------------------------------------------



class Worker (X_Program):
    """ proxy to execute Worker commands"""

    NAME        = 'Worker'
    NAME_EXE    = 'worker'                             # stem of of exe file 


    # -- static methods --------------------------------------------

    @staticmethod
    def polarDir (airfoil_pathFileName : str) -> str:
        """ returns polar directory of airfoil having airfoil_pathFileName"""

        return str(Path(airfoil_pathFileName).with_suffix('')) + '_polars'

    @staticmethod
    def flapped_suffix (flap_angle:float, x_flap:float, y_flap:float, y_flap_spec:str) -> str:
        """ 
        name extension for flapped airfoil or polar file 
            '_f5.1' for defaults or 
            '_f-1.4_xf0.72_yf0.5_yspecYC' for non default values
        """
        if flap_angle == 0.0: return ''

        s_flap_angle = f"_f{flap_angle:.2f}".rstrip('0').rstrip('.') 
        s_x_flap     = f"_xf{x_flap:.2f}".rstrip('0').rstrip('.') if x_flap != 0.75 else ''
        s_y_flap     = f"_yf{y_flap:.2f}".rstrip('0').rstrip('.') if y_flap != 0.0  else ''
        s_y_spec     = f"_yspecYC" if y_flap_spec == 'y/c'  else ''

        return  f"{s_flap_angle}{s_x_flap}{s_y_flap}{s_y_spec}"


    @staticmethod
    def remove_polarDir (airfoil_pathFileName : str, only_if_older = False):
        """ 
        deletes polar directory 
        If only_if_older the directory is not removed if it is younger than of airfoilPathFileName
        """ 

        polarDir = Worker.polarDir (airfoil_pathFileName) if airfoil_pathFileName else None

        # sanity check 
        if not os.path.isdir(polarDir): return 

        remove = True 

        if only_if_older:
            if os.path.isfile(airfoil_pathFileName):

                # compare datetime of airfoil file and polar dir 
                ts = os.path.getmtime(polarDir)                 # file modification timestamp of a file
                polarDir_dt = datetime.datetime.fromtimestamp(ts)        # convert timestamp into DateTime object

                ts = os.path.getmtime(airfoil_pathFileName)              # file modification timestamp of a file
                airfoil_dt = datetime.datetime.fromtimestamp(ts)         # convert timestamp into DateTime object

                # add safety seconds (async stuff?) 
                if (airfoil_dt < (polarDir_dt + datetime.timedelta(seconds=2))):
                    remove = False 
            else: 
                remove = False 

        if remove: 
            shutil.rmtree(polarDir, ignore_errors=True)


    @staticmethod
    def get_existingPolarFile (airfoil_pathFileName, 
                               polarType : str, re : float, ma : float, ncrit : float,
                               flap_angle : float, x_flap : float, y_flap : float, y_flap_spec : str) -> str:
        """ 
        Get pathFileName of polar file if it exists 
        """      

        def parm_is_ok (id:str, val : float|None, decimals, args :list[str]) -> bool:
            """ inner func: check if paramter is in argunents of fileName"""
            if val is not None and decimals is not None: 
                val = round (val, decimals)

            for arg in args:
                if id == arg [:len(id)]:
                    if val is not None:
                        arg_val = arg[len(id):] if isinstance (val, str) else float(arg[len(id):])
                        if val == arg_val:                  # right arg 
                            return True                     #   right value
                        else:
                            return False                    #   wrong value
                    else: 
                        return False                        # this arg is too much
            
            if val is None: 
                return True                                 # this arg is correctly not there 
            else:
                return False                                # this arg is missing


        # remove a maybe older polarDir
        Worker.remove_polarDir (airfoil_pathFileName, only_if_older=True)    

        # build name of polar dir from airfoil file 
        polarDir = Worker.polarDir (airfoil_pathFileName)
        if os.path.isdir (polarDir):         

            fileNames = fnmatch.filter(os.listdir(polarDir), '*.txt')
            for fileName in fileNames:

                args = Path(fileName).stem.split('_')

                ok = True 

                # classic part 'T1_Re0.500_M0.00_N7.0'

                ok = ok and parm_is_ok ("Re", re/1000000, 3, args)
                ok = ok and parm_is_ok ("M",  ma, 2, args)
                ok = ok and parm_is_ok ("N",  ncrit, 1, args)
                ok = ok and parm_is_ok ("T",  int(polarType[1:]), 0, args)

                # flapped part '_f-1.4_xf0.72_yf0.5_yspecYC' for non default values

                ok = ok and parm_is_ok ("f", flap_angle, 1, args)

                x_flap_arg = None if x_flap ==0.75 else x_flap
                ok = ok and parm_is_ok ("xf", x_flap_arg, 2, args)

                y_flap_arg = None if y_flap ==0.0 else y_flap
                ok = ok and parm_is_ok ("yf", y_flap_arg, 2, args)

                y_flap_spec_arg = 'YC' if y_flap_spec =='y/c' else None
                ok = ok and parm_is_ok ("yspec", y_flap_spec_arg, None, args)

                if ok:
                    # logger.debug (f"<class Worker> found polar file {fileName} in {polarDir}")
                    return os.path.join (polarDir, fileName)        # return pathFileName

        logger.debug (f"<class Worker> No polar file in {polarDir}")
        return None


    #---------------------------------------------------------------


    def check_inputFile (self, inputFile=None):
        """ uses Worker to check an Xoptfoil2"""

        if not self.ready: return 1, self.NAME + " not ready"

        error_text = ""
        args = ['-w', 'check-input', '-i', inputFile]

        returncode = self._execute (args, capture_output=True)

        if returncode != 0:

            # worker output should something like ...
            #  Worker   -check-input jx-gt-10v3.inp
            #  - Processing input
            #    - Reading input jx-gt-10v3.inp
            #    - Output prefix jx-gt-10v3
            #  Error: max_speed should be between 0.001 and 0.5

            for line in self._pipe_out_lines:
                error_text = line.partition("Error:")[2].strip()
                if error_text != '': break 
            if error_text == '':
                raise ValueError ("Errortext not found in Workers")

        return returncode, error_text 


    def generate_polar (self, airfoil_pathFileName, 
                        polarType : str, 
                        re : float | list, 
                        ma : float | list, 
                        ncrit : float,
                        autoRange = True, spec = 'alpha', valRange= [-3, 12, 0.25], 
                        flap_angle : float | list = 0.0, x_flap=0.75, y_flap=0, y_flap_spec='y/t',
                        nPoints=None, run_async = True) -> int:
        """ 
        Generate polar for airfoilPathFileName in directory of airfoil.
        Returncode = 0 if successfully started (async) or finish (sync)
        """ 

        if not os.path.isfile(airfoil_pathFileName): 
            name = airfoil_pathFileName if len(airfoil_pathFileName) <= 40 else "..." + airfoil_pathFileName[-35:]
            raise ValueError (f"Airfoil '{name}' does not exist")

        if (polarType == 'T2'):
            polarTypeNo = 2
        else: 
            polarTypeNo = 1

        if spec == 'alpha':
            spec_al = True
        else: 
            spec_al = False

        if not isinstance (re, list): re = [re]
        if not isinstance (ma, list): ma = [ma]
        if flap_angle:
            if not isinstance (flap_angle, list): flap_angle = [flap_angle]
        else: 
            flap_angle=None

        # working directory in which self will execute 

        workingDir = self._get_workingDir (airfoil_pathFileName)

        # a temporary input file for polar generation is created

        self._tmp_inpFile = self._generate_polar_inputFile (workingDir, 
                                    re, ma, polarTypeNo, ncrit, autoRange, spec_al, valRange,
                                    flap_angles=flap_angle, x_flap=x_flap, y_flap=y_flap, y_flap_spec=y_flap_spec,
                                    nPoints=nPoints) 
        if not self._tmp_inpFile:
            raise RuntimeError (f"{self.NAME} polar generation failed: Couldn't create input file")

        # build args for worker - force outname as Worker wrongly uses airfoil name!

        # outname = Path(os.path.basename(airfoil_pathFileName)).stem
        outname = '' 

        args = self._build_worker_args ('polar-flapped',airfoil1=airfoil_pathFileName, inputfile=self._tmp_inpFile, outname=outname)

        # .execute either sync or async

        if run_async: 

            returncode = self._execute_async (args, capture_output=True, workingDir=workingDir)

        else:

            returncode = self._execute       (args, capture_output=True, workingDir=workingDir)

            self.remove_tmp_file ()         
        
        if returncode: 
            raise RuntimeError (f"Worker polar generation failed for {airfoil_pathFileName}")
            



    def set_flap (self, airfoil_fileName, 
                        x_flap : float = 0.75,
                        y_flap : float = 0.0,
                        y_flap_spec : str = 'y/t',
                        flap_angle : float | list = 0.0,
                        outname : str =None) -> int:
        """ 
        Set flap for airfoilPathFileName in directory of airfoil.

        Returns fileName of flapped airfoil in working Dir  
        """ 

        # sanity check airfoil_file 

        if self.workingDir:
            airfoil_pathFileName_abs = os.path.join(self.workingDir, airfoil_fileName)
        else: 
            airfoil_pathFileName_abs = airfoil_fileName

        if not os.path.isfile(airfoil_pathFileName_abs): 
            name = airfoil_pathFileName_abs if len(airfoil_pathFileName_abs) <= 40 else "..." + airfoil_pathFileName_abs[-35:]
            raise ValueError (f"Airfoil '{name}' does not exist")

        # name of the generated airfoil needed

        if not outname: 
            outname=f"{Path(airfoil_fileName).stem}{Worker.flapped_suffix (flap_angle, x_flap, y_flap, y_flap_spec)}"

        # working directory in which self will execute 

        workingDir = self._get_workingDir (airfoil_fileName)

        # a temporary input file for polar generation is created

        self._tmp_inpFile = self._generate_flap_inputFile (workingDir, x_flap, y_flap, y_flap_spec, flap_angle)         
        if not self._tmp_inpFile:
            raise RuntimeError (f"{self.NAME} setting flap failed: Couldn't create input file")

        # build args for worker 

        args = self._build_worker_args ('flap', airfoil1=airfoil_fileName, 
                                                inputfile=self._tmp_inpFile,
                                                outname=outname)
        # .execute  sync

        rc = self._execute (args, capture_output=True, workingDir=workingDir)

        if rc: 
            raise RuntimeError (f"Worker set flap failed: {self.finished_errortext}")
        else: 
            self.remove_tmp_file ()         

            flapped_fileName = outname + ".dat"
            # check if flapped airfoil was created  
            if os.path.isfile (os.path.join (workingDir, flapped_fileName)):
                return flapped_fileName
            else: 
                return None 


    def clean_workingDir (self, workingDir):
        """ 
        deletes temporary (older) files Worker creates in workingDir
        """ 
        if os.path.isdir(workingDir):

            # remove tmp input files of polar generation 
            match_path = os.path.join (workingDir, f"{TMP_INPUT_NAME}*{TMP_INPUT_EXT}")
            
            for f in glob(match_path):
                os.remove(f)


# ---------- Private --------------------------------------



    def _build_worker_args (self, action, actionArg='', airfoil1='', airfoil2='', outname='', inputfile=''):
        """ 
        return worker args as list of strings  
        """

        airfoil1_fileName = os.path.basename(airfoil1)
        airfoil2_fileName = os.path.basename(airfoil2)

        # info inputfile is in a dir - strip dir from path - local execution 

        local_inputfile = os.path.basename(inputfile) if inputfile else ''

        args = []

        if (action != ''): 
            if (action == 'help'): 
                args.extend(['-h'])
            else:                  
                args.extend(['-w', action])
                if (actionArg): args.extend([actionArg]) 
        else: 
            raise ValueError ('action for worker is mandatory')

        if (airfoil1 ): args.extend(['-a',  airfoil1_fileName])
        if (airfoil2 ): args.extend(['-a2', airfoil2_fileName])
        if (outname  ): args.extend(['-o',  outname]) 
        if (inputfile): args.extend(['-i',  local_inputfile])

        # add 'mode' option - will write error to stderr
        args.extend(['-m', 'child']) 

        return  args



    def _generate_polar_inputFile (self, 
                                  workingDir : str,         # if none self._workingDir is taken 
                                  reNumbers : list[float], maNumbers : list[float],
                                  polarType : int, ncrit : float,  
                                  autoRange : bool, spec_al: bool, valRange: list[float], 
                                  nPoints = None,
                                  flap_angles : list[float] = None, x_flap=None, y_flap=None, y_flap_spec=None,
                                   ) -> str:
        """ Generate a temporary polar input file for worker like this 

        &polar_generation
            generate_polars = .true.
            polar_reynolds  = 230000, 300000, 400000
            polar_mach      = 0.0, 0.2, 0.5
            type_of_polar = 1
            auto_Range = .true.
            op_mode = 'spec-al'
            op_point_range = -2.6, 11.0, 0.5
        /
        &xfoil_run_options
            ncrit = 7.0
        /
        &operating_conditions                          ! options to describe the optimization task
        x_flap                 = 0.75                  ! chord position of flap 
        y_flap                 = 0.0                   ! vertical hinge position 
        y_flap_spec            = 'y/c'                 ! ... in chord unit or 'y/t' relative to height
        flap_angle             = 0.0                   ! list of flap angles to be set


        Returns: 
            pathFilename of input file  """

        tmpFilePath = None

        # create tmp input file 

        with NamedTemporaryFile(mode="w", delete=False, dir=workingDir, prefix=TMP_INPUT_NAME, suffix=TMP_INPUT_EXT) as tmp:

            tmp.write ("&polar_generation\n")
            tmp.write ("  type_of_polar = %d\n" % polarType)  
            tmp.write ("  polar_reynolds  = %s\n" % (', '.join(str(e) for e in reNumbers))) 
            if max(maNumbers) > 0.0: 
                tmp.write ("  polar_mach  = %s\n" % (', '.join(str(e) for e in maNumbers))) 
            if autoRange:
                tmp.write ("  auto_range = .true.\n") 
                if valRange[2]:                                 # write only increment
                    tmp.write ("  op_point_range = , , %.2f \n" % (valRange[2])) 
            else:
                if spec_al:  tmp.write ("  op_mode = 'spec-al'\n") 
                else:        tmp.write ("  op_mode = 'spec-cl'\n") 
                tmp.write ("  op_point_range = %.2f , %.2f , %.2f \n" % (valRange[0], valRange[1], valRange[2])) 
            tmp.write ("/\n")

            tmp.write ("&xfoil_run_options\n")
            tmp.write ("  ncrit = %.1f\n" % ncrit)  
            tmp.write ("/\n")

            if flap_angles:
                tmp.write ("&operating_conditions\n")
                tmp.write (f"  x_flap = {x_flap}\n")  
                tmp.write (f"  y_flap = {y_flap}\n")  
                tmp.write (f"  y_flap_spec = '{y_flap_spec}'\n")  
                tmp.write (f"  flap_angle = {', '.join(str(f) for f in flap_angles)}\n") 
                tmp.write ("/\n")

            if nPoints is not None: 
                tmp.write ("&paneling_options\n")
                tmp.write (f"  npoint = {int(nPoints)}\n")  
                tmp.write ("/\n")

            tmpFilePath = tmp.name

        return tmpFilePath              



    def _generate_flap_inputFile (self, 
                                 workingDir : str = None,         # if none self._workingDir is taken 
                                  x_flap : float = 0.75,
                                  y_flap : float = 0.0,
                                  y_flap_spec : str = 'y/c',
                                  flap_angle : float | list = 0.0, 
                                  ) -> str:
        """ Generate a temporary polar input file for worker inworkingDir

        &operating_conditions                              ! options to describe the optimization task
            x_flap                 = 0.75                  ! chord position of flap 
            y_flap                 = 0.0                   ! vertical hinge position 
            y_flap_spec            = 'y/c'                 ! ... in chord unit or 'y/t' relative to height
            flap_angle             = 0.0                   ! list of flap angles to be applied        
        /

        Returns: 
            pathFilename of input file  """

        tmpFilePath = None

        flap_angles = flap_angle if isinstance (flap_angle, list) else [flap_angle]
        y_flap_spec = 'y/t' if y_flap_spec == 'y/t' else 'y/c'

        # create tmp input file 

        with NamedTemporaryFile(mode="w", delete=False, dir=workingDir, prefix=TMP_INPUT_NAME, suffix=TMP_INPUT_EXT) as tmp:

            tmp.write ("&operating_conditions\n")
            tmp.write (f"  x_flap = {x_flap:.2f}\n")  
            tmp.write (f"  y_flap = {y_flap:.2f}\n")  
            tmp.write (f"  y_flap_spec = '{y_flap_spec}'\n")  
            tmp.write (f"  flap_angle = {','.join(map(str, flap_angles))}\n")  
            tmp.write ("/\n")

            tmpFilePath = tmp.name

        return tmpFilePath              


# -------------- End --------------------------------------




# Main program for testing 
if __name__ == "__main__":

    # init logging 
    from base.common_utils      import init_logging
    init_logging (level= logging.DEBUG)


    Worker().isReady (project_dir="..\\..", min_version='1.0.3')

    if Worker.ready:

        worker = Worker()

        if os.path.isfile ('..\\..\\test_airfoils\\MH 30.dat'):
            airfoil = '..\\..\\test_airfoils\\MH 30.dat'
        elif os.path.isfile ('MH 30.dat'):
            airfoil = 'MH 30.dat'
        else: 
            logger.error (f"Airfoil file 'MH 30.dat' not found")
            exit()

        # build name of polar dir from airfoil file 
        polarDir = str(Path(airfoil).with_suffix('')) + '_polars'

        # ------- sync test ---------------------------------------------

        try: 
            worker.generate_polar (airfoil, 'T1', 700000, 0.0, 8.0, flap_angle=5.12, run_async=False)

            worker.generate_polar (airfoil, 'T1', 700000, 0.0, 8.0, run_async=False)

            logger.info ("\n".join (worker._pipe_out_lines))
            polar_file = worker.get_existingPolarFile (airfoil, 'T1', 700000, 0.0, 8.0, flap_angle=5.12)

            if polar_file:
                logger.info  (f"polar file found: {polar_file}")
            else: 
                logger.error (f"polar file not found")

            worker.finalize ()
            worker.remove_polarDir (airfoil)

        except ValueError as exc:
            logger.error (f"{exc}")
        except RuntimeError as exc:
            # logger.error (f"Polar failed: {exc}")
            logger.error (f"{worker}: {worker.finished_errortext}")

        

        # ------- async test ---------------------------------------------

        worker = Worker()

        try: 
            worker.generate_polar (airfoil, 'T1', 700000, 0.0, 8.0, run_async=True)

            secs = 0 
            while worker.isRunning ():
                time.sleep (0.5)
                secs += 0.5
                logger.debug (f"{worker} waiting: {secs}s")

            if worker.finished_returncode == 0:

                polar_file = worker.get_existingPolarFile (airfoil, 'T1', 700000, 0.0, 8.0)

                if polar_file:
                    logger.info  (f"polar file found: {polar_file}")
                else: 
                    logger.error (f"polar file not found")
            else: 
                logger.error (f"{worker}: {worker.finished_errortext}")

            worker.finalize ()
            worker.remove_polarDir (airfoil)

        except ValueError as exc:
            logger.error (f"{exc}")
        except RuntimeError as exc:
            # logger.error (f"Polar failed: {exc}")
            logger.error (f"{worker}: {worker.finished_errortext}")
