#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  
Helper classes, dialogs, functions for an App
"""
import os
import requests

from datetime               import date, datetime
from platformdirs           import user_config_dir, user_data_dir

from packaging.version      import Version                                  # has to be installed
from PyQt6.QtCore           import QTimer
from PyQt6.QtWidgets        import QDialogButtonBox, QWidget

from .common_utils          import Parameters
from .panels                import Dialog
from .widgets               import *

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)




# ----------------------------------------------------------------------------

def check_or_get_initial_file (initial_file : str) -> str:
    """ check if initial file exists - otherwise get last opened file from settings """

    if initial_file and os.path.isfile (initial_file):
        return initial_file

    app_settings = Settings()                                           # load app settings

    last_opened = app_settings.get('last_opened', default=None) 
    if last_opened and os.path.isfile (last_opened):
        logger.info (f"Starting on 'last opened' airfoil file: {last_opened}")
        return last_opened
    else:
        if last_opened:
            logger.error (f"File '{last_opened}' doesn't exist")
            app_settings.delete ('last_opened', purge=True)              # remove invalid entry

    return None


# ----------------------------------------------------------------------------


class Settings (Parameters):
    """ Singleton: Handles a named app setting file with a json structure""" 

    _pathFileName = None                     # the filePath of the settings

    def __init__ (self):

        if self._pathFileName is None:
            raise RuntimeError ("Settings are not initialized")
        
        super().__init__(self._pathFileName)


    @staticmethod
    def user_data_dir (app_name, app_author = 'jxjo'):
        """ returns directory for app data 
        
        Args:
            app_name: name of app self will belong to 
            app_author : typical for Windows - something like 'Microsoft' of 'jxjo'  
        """

        return user_data_dir (app_name, app_author, ensure_exists=True) 


    @classmethod
    def set_file (cls, app_name, app_author = 'jxjo', name_suffix=None, file_extension= '.json'):
        """ static set of the file the settings will belong to 
        
        Args:
            app_name: name of app self will belong to 
            app_author : typical for Windows - something like 'Microsoft' of 'jxjo'  
            name_suffix: ... will be appended to appName - default '_settings'      
            file_extension: ... of the settings file - default 'json'       
        """

        fileName = app_name + name_suffix + file_extension if name_suffix else app_name + file_extension

        # get directory where self is located
        settings_dir  = user_config_dir (app_name, app_author, ensure_exists=True)

        cls._pathFileName = os.path.join(settings_dir, fileName)

        logger.info (f"Reading settings from {cls._pathFileName}")


class Run_Checker:
    """
    - Check if App runs the first time in this version 
    """

    @staticmethod
    def is_first_run (current_version : str) -> bool:
        """ returns if this is the first run of this version """

        settings = Settings()             # app settings 

        last_run_version = settings.get ("last_run_version", None)
        
        if last_run_version != current_version:
            # save current version as last run version 
            settings.set("last_run_version", current_version)
            settings.save()
            logger.info (f"First run of version {current_version}")
            return True
        else:
            return False


class Update_Checker:
    """
    - Check if update for package is available, 
    - Inform User
    """

    def __init__ (self, parent : QWidget, app_name : str, package_name : str, current_version : str):

        self._app_name = app_name
        self._package_name = package_name
        self._current_version = current_version

        self._latest_version = None
        self._settings = Settings()             # app settings 

        if self.is_newer_version_available():
            QTimer.singleShot (1000, lambda: self.show_user_info (parent))


    @property
    def latest_version (self) -> str:
        """ latest available version - None if not accessible"""
        return self._latest_version if self._latest_version else None


    def _get_pypi_latest_version (self, package_name : str) -> str:
        """ 
        API request to PYPI to get latest version as string.
            return "" if failed or not available  
        """
        latest_version = ""

        try: 
            response = requests.get(f'https://pypi.org/pypi/{package_name}/json')

            if response.status_code == 200:             # http     
                latest_version = response.json()['info']['version']
                logger.debug (f"Package {package_name} version {latest_version} found on PyPI")
            elif response.status_code == 404:
                logger.error (f"Package {package_name} not found on PyPI")
            else:
                logger.error (f"Error {response.status_code} on accessing PyPI for package {package_name}")

            # save check date and latest version in settings
            self._settings.set("update_last_check", str(date.today()))
            self._settings.set("update_latest_version", latest_version)
            self._settings.save()

        except: 
            pass

        return latest_version


    def is_newer_version_available (self) -> bool:
        """ returns if there is a newer version on PyPI"""

        # get date of last check from settings 
        last_check_date_str = self._settings.get ("update_last_check", None)
        if last_check_date_str:

            last_check_date = datetime.strptime(last_check_date_str, '%Y-%m-%d').date()
            if last_check_date  == date.today():
                # if already checked today - get version from settings
                self._latest_version = self._settings.get ("update_latest_version", "")
                logger.debug (f"Version check on PyPI already made for today (latest version: {self._latest_version})")
            else:
                logger.debug (f"Version check on PyPI made on {last_check_date_str}")


        if self._latest_version is None: 
            self._latest_version = self._get_pypi_latest_version (self._package_name)

        if self._latest_version and self._current_version:
            is_available = Version (self._latest_version) > Version (self._current_version)
        else: 
            is_available = False

        if is_available:
            logger.info (f"New version {self._latest_version} of {self._app_name} available on PyPI")
        else:
            logger.info (f"{self._app_name} is up-to-date")

        return is_available


    def show_user_info (self, parent):
        """ show info dialog about a new version"""

        dont_ask_for_version = self._settings.get ("update_dont_ask_for_version", None)

        if dont_ask_for_version != self._latest_version:

            dialog = Update_Info_Dialog (parent, self._app_name, self._package_name, self._latest_version)
            dialog.exec()

            if dialog.dont_ask_version:
                self._settings.set("update_dont_ask_for_version", self._latest_version)
                self._settings.save()



class Update_Info_Dialog (Dialog):
    """
    Inform user about a newer version of app
    """

    name = "Update Check"             # will be title 

    _width  = 420
    _height = 230 

    def __init__(self, parent, app_name : str, package_name, latest_version : str):

        self._app_name = app_name
        self._latest_version = latest_version
        self._package_name = package_name

        self._dont_ask_version = False

        super().__init__(parent)

    @property
    def dont_ask_version (self) -> bool:
        """ user doesn't want to show this dialog again"""
        return self._dont_ask_version
    
    def set_dont_ask_version (self, aBool):
        self._dont_ask_version = aBool

    def _init_layout(self):

        l = QGridLayout()

        r,c = 0, 0 
        lab = Label (l,r,c, rowSpan=4, height=30)
        icon = Icon(Icon.INFO)
        pixmap = icon.pixmap ((QSize(30, 30)))
        lab.setPixmap (pixmap)

        r,c = 0, 1 
        text =  f"There is a new version <b>{self._latest_version }</b> of {self._app_name} available.<br><br>" +   \
                f"Depending on your installation mode,<br><br>" + \
                f" - either update package with 'pip install {self._package_name} -U'<br>" + \
                f" - or download new version from <a href='https://github.com/jxjo/{self._app_name}/releases/'>GitHub" 
        lab = Label    (l,r,c, height=110, wordWrap=True, get=text)
        lab.setOpenExternalLinks(True)

        r += 1
        SpaceR (l,r)
        r += 1
        CheckBox (l,r,c, text="Don't show this message again",
                  get=self.dont_ask_version, set=self.set_dont_ask_version)

        l.setColumnMinimumWidth (0, 50)
        l.setColumnStretch (1,3)

        return l
    
    def _button_box (self) -> QDialogButtonBox:
        """ returns the QButtonBox with the buttons of self"""
        buttons = QDialogButtonBox.StandardButton.Ok 
        buttonBox = QDialogButtonBox(buttons)
        buttonBox.accepted.connect(self.accept)
        return buttonBox 