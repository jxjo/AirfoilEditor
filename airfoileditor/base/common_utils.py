#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Common Utility functions for convenience - no dependencies from other modules  
"""

import os
import json
from enum                   import StrEnum
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


class StrEnum_Extended (StrEnum):
    """Enum extension with convenience access to raw values."""

    @classmethod
    def values (cls):
        return [c.value for c in cls]


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
# Dictionary handling
#------------------------------------------------------------------------------

def fromDict(aDict : dict, key, default='no default'):
    """
    returns a value from dict. If ky is not in the dict and there is no default value an error
    will be raised 

    Args:
        dict: the dictionary to look in 
        key: the key to look for       
        default: the value if key is missing
    """
    if not isinstance(aDict, dict):
        aDict = {}

    preferred_type = None

    if default != 'no default':
        if isinstance (default, float):
           preferred_type = float
        elif isinstance (default, bool):
            preferred_type = bool
        elif isinstance (default, int):
            preferred_type = int

    def _copy_default(val):
        if isinstance(val, list):
            return val.copy()
        if isinstance(val, dict):
            return val.copy()
        if isinstance(val, set):
            return val.copy()
        return val

    if aDict and key in aDict:
        value = aDict[key]
        if value is None and default != 'no default':
            value = _copy_default(default)
    else:
        if default == 'no default':
            value = None
            logger.error ('Mandatory parameter \'%s\' not specified'  % key)
        else:
            value = _copy_default(default)
            if value:
                logger.debug ('Parameter \'%s\' not specified, using default-value \'%s\'' % (key, str(value)))

    if preferred_type == float:
        value = float(value)
    elif preferred_type == int:
        value = int(value)
    elif preferred_type == bool:
        value = bool(value)

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
# Settings and Parameter file 
#------------------------------------------------------------------------------


class Parameters (dict):
    """ Handles a parameter file with a json structure representing a dictionary of parameters""" 

    def __init__ (self, pathFileName : str = None):
        super().__init__()

        self._pathFileName = pathFileName

        if pathFileName is not None:
            self.load()


    def __repr__ (self) -> str:
        """ nice representation of self """
        return f"<{type(self).__name__}>"


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


    def delete (self, key, purge: bool = True):
        """ deletes 'key' from self - optionally saves self after deletion"""
        self.pop(key, None)
        if purge:
            self.save()


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
                logger.debug (f"Parameter file {self.pathFileName} not found")

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
            Path (self.pathFileName).unlink()
            self.clear()
            logger.debug (f"Parameter file '{self.pathFileName}' deleted")
        except Exception as e:
            logger.error (f"Failed to delete parameter file '{self.pathFileName}': {e}")



#------------------------------------------------------------------------------
# File, Path handling 
#------------------------------------------------------------------------------

def relative_path (path : str | Path | None, start : str | Path | None = None) -> str | None:
    """ 
    Returns 'path' relative to 'start' (default: cwd) as string. 
    Returns 'path' unchanged if it's on a different drive or if the relative path would be longer.
    """
    if path is None: 
        return None
    
    abs_path = Path(path).absolute()
    abs_start = Path(start).absolute() if start else Path.cwd()

    try: 
        rel = str(abs_path.relative_to (abs_start, walk_up=True))
    except ValueError:                                  # different drive
        return str(path)
    
    return str(path) if len(rel) > len(str(path)) else rel


def absolute_path (path : str | Path, start : str | Path | None = None) -> str:
    """ Returns 'path' as normalized absolute path. A relative 'path' is based on 'start' (default: cwd) """
    base = Path(start) if start else Path.cwd()
    return os.path.normpath (base / path)           # pathlib can't collapse '..' lexically


