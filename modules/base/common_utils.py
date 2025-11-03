#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Common Utility functions for convinience - no dependencies from other moduls  
"""

import os
import json
from pathlib                import Path
from typing                 import override
from termcolor              import colored
from collections.abc        import Iterable

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)


#------------------------------------------------------------------------------
# base type utils  
#------------------------------------------------------------------------------


def clip(val, min_, max_):
    """ clip aVal to be between min and max"""
    return min_ if val < min_ else max_ if val > max_ else val



#------------------------------------------------------------------------------
# logging 
#------------------------------------------------------------------------------

def init_logging (level= logging.WARNING):
    """ initialize logging with level"""

    ch = logging.StreamHandler()

    ch.setFormatter(CustomFormatter())

    logging.basicConfig(format='%(levelname)-8s- %(message)s', 
                        handlers=[ch], 
                        level=level)  # DEBUG or WARNING
    # suppress debug messages from these modules 
    # logging.getLogger('PIL.PngImagePlugin').disabled = True
    # logging.getLogger('dxf_utils').disabled = True


class CustomFormatter(logging.Formatter):
    """ colored formatting of logging stream"""

    # format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"

    FORMATS = {
        logging.DEBUG:    colored(" - %(levelname)s - %(message)s", 'yellow', attrs=["dark"]) + colored(" (%(filename)s:%(lineno)d)", 'white', attrs=["dark"]),                          # grey + format + reset,
        logging.INFO:     colored(" - %(message)s", 'white', attrs=["dark"]),
        logging.WARNING:  colored("WARNING - ", 'yellow') + "%(message)s",
        logging.ERROR:    colored("ERROR - ", 'red') + "%(message)s",
        logging.CRITICAL: colored("ERROR - ", 'red', attrs=["bold"]) + "%(message)s"
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)
    

#------------------------------------------------------------------------------
# Dictonary handling
#------------------------------------------------------------------------------

def fromDict(aDict : dict, key, default='no default'):
    """
    returns a value from dict. If ky is not in the dict and there is no default value an error
    will be raised 

    Args:
        dict: the dictonary to look in 
        key: the key to look for       
        default: the value if key is missing
    """
    preferedType = None

    if default != 'no default':
        if isinstance (default, float):
           preferedType = float
        elif isinstance (default, bool):
            preferedType = bool
        elif isinstance (default, int):
            preferedType = int

    if aDict and key in aDict:
        value = aDict[key]
        if preferedType == float:
            value = float(value)
        elif preferedType == int:
            value = int(value)
        elif preferedType == bool:
            value = bool(value)
    else:
        if default == 'no default':
            value = None
            logger.error ('Mandatory parameter \'%s\' not specified'  % key)
        else:
            value = default 
            if value:
                logger.debug ('Parameter \'%s\' not specified, using default-value \'%s\'' % (key, str(value)))
    return value


def toDict(aDict : dict, key, value):
    """
    writes t0 the parameter dictionary. If 'value' is None the key is not written 
    """
    if isinstance (aDict,dict):
        if not value is None: 
            # limit decimals in file 
            if isinstance  (value, float):
                value = round (value,6)
            aDict [key] = value
        else: 
            # remove key from dictionary  - so default values will be used 
            aDict.pop(key, None)

        
#------------------------------------------------------------------------------
# Settings and Paramter file 
#------------------------------------------------------------------------------


class Parameters (dict):
    """ Handles a parameter file with a json structure representing a dictionary of paramteres""" 

    def __init__ (self, pathFileName : str = None):
        super().__init__()

        self._pathFileName = pathFileName

        if pathFileName is not None:
            self.load()
        

    @property
    def pathFileName (self) -> str:
        """ returns the path file name of the parameter file """
        return self._pathFileName

    def set_pathFileName (self, pathFileName : str):
        """ sets the path file name of the parameter file """
        self._pathFileName = pathFileName
        

    @override
    def get(self, key, default=None):
        """
        Returns value of 'key' 
        If a default is given, the returned value will be cast to the type of default
        """

        val = super().get(key, default)

        if default is not None and val is not None:
            if isinstance (default, float):
                val = float(val)
            elif isinstance (default, bool):
                val = bool(val)
            elif isinstance (default, int):
                val = int(val)
            elif isinstance (default, str):
                val = str(val)
        return val


    def set(self, key, value):
        """
        Sets 'key' with 'value'. If value is ... 
        - float, it will be rounded to 6 decimals
        - None or [] or {} or '' the key will be removed from the dictionary 
        """
        # avoid empty entries in settings
        if value is None or (isinstance(value, Iterable) and len(value) == 0):
            self.pop(key, None)
        else:
            # limit decimals in file
            if isinstance(value, float):
                value = round(value, 6)

            self[key] = value


    def load (self):
        """
        load self from json file
        """
        dataDict = {}
        if self.pathFileName:
            try:
                fs = open(self.pathFileName)
                try:
                    dataDict = json.load(fs)
                    fs.close()
                except ValueError as e:
                    logger.error (f"Invalid json expression '{e}' in parameter file '{self.pathFileName}'")
                    fs.close()
                    dataDict = {}
            except:
                logger.debug (f"Paramter file {self.pathFileName} not found")

        self.clear()
        self.update(dataDict)


    def replace_all (self, newParams : dict):
        """ replaces all parameters of self with newParams """
        self.clear()
        self.update(newParams)


    def save (self):
        """ writes self to json file"""

        with open(self.pathFileName, 'w+') as fs:

            try:
                json.dump(self, fs, indent=2, separators=(',', ':'))
                logger.debug (f"{type(self).__name__} saved to {self.pathFileName}" )

            except ValueError as e:
                logger.error (f"Invalid json expression '{e}'. Failed to save data to '{self.pathFileName}'")
            except Exception as e:
                logger.error (f"{e}. Failed to save data to '{self.pathFileName}'")

        return


    def delete_file (self):
        """ deletes the parameter file of self """
        try:
            os.remove (self.pathFileName)
            self.clear()
            logger.debug (f"Parameter file '{self.pathFileName}' deleted")
        except Exception as e:
            logger.error (f"Failed to delete parameter file '{self.pathFileName}': {e}")



#------------------------------------------------------------------------------
# File, Path handling 
#------------------------------------------------------------------------------

class PathHandler(): 
    """ handles relative Path of actual files to a workingDir """

    def __init__ (self, workingDir=None, onFile=None): 
        """  Pathhandler for working directory either from 'workinfDir' directly or based 'onFile' """
        self._workingDir = None

        if workingDir is not None: 
           self.workingDir = workingDir 
        elif onFile is not None:
           self.set_workingDirFromFile (onFile)

    @classmethod
    def relPath(cls, pathFilename, start = None):
        """Return a relative version of a path - like os.path.relpath - but checks for same drive

        Args:
            :start: start dir - default: cwd (current working Dir)
        """
        if start is None: start = os.getcwd()

        if Path(pathFilename).anchor == Path(start).anchor: 
            relPath = os.path.relpath(pathFilename, start = start)
        else: 
            relPath = pathFilename
        return relPath  


    @property 
    def workingDir (self):
        return self._workingDir if (not self._workingDir is None) else ''
    
    @property 
    def workingDir_name (self): 
        """ the directory name of workingDir """
        return os.path.basename(os.path.normpath(self.workingDir))
    
    @workingDir.setter
    def workingDir (self, newDir):

        if newDir is None: 
            self._workingDir = os.getcwd ()      # if no directory set, take current working Dir 
        elif not newDir: 
            self._workingDir = os.getcwd ()      # if no directory set, take current working Dir 
        elif not os.path.isdir(newDir): 
            os.makedirs(newDir)  
            self._workingDir = os.path.normpath(newDir)    
        else: 
            self._workingDir = os.path.normpath(newDir) 

    def set_workingDirFromFile (self, aFilePath):

        if aFilePath is None: 
            self.workingDir = None
        elif not aFilePath: 
            self.workingDir = os.getcwd ()      # if no directory set, take current working Dir 
        else: 
            self.workingDir = os.path.dirname(aFilePath) 
            if not os.path.isdir(self.workingDir):
                os.makedirs(self.workingDir)

    def relFilePath (self, aFilePath):
        """ returns the relative path of aFilePath to the workingDir of self"""
        if aFilePath is None: 
            return None
        else: 
            try: 
                relPath =  os.path.normpath(os.path.relpath(aFilePath, start = self.workingDir))
                if len(relPath) > len(aFilePath): 
                    return aFilePath                # relPath would be more complicated
                else: 
                    return relPath 
            except:                                 # aFilePath is on different drive 
                return aFilePath 
    
    def fullFilePath (self, aRelPath):
        """ returns the full path of relative aRelPath and the workingDir of self"""

        if aRelPath is None: 
            return self.workingDir
        else: 
            if os.path.isabs (aRelPath): 
                # maybe we can make a rel path out of it? 
                newPath = self.relFilePath (aRelPath)
                if os.path.isabs (newPath):
                    return aRelPath                 # we surrender - it's absolute
                else: 
                    aRelPath = newPath              # now we have a real rel path 
            return os.path.normpath(os.path.join (self.workingDir, aRelPath))


