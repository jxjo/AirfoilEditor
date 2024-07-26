#!/usr/bin/env pythonbutton_color
# -*- coding: utf-8 -*-

"""  

Higher level Widgets to handle Airfoil UI operations like Open and Select

"""

import os
import fnmatch 
import logging

from PyQt6.QtCore       import QSize, QMargins
from PyQt6.QtWidgets    import QLayout, QGridLayout, QVBoxLayout, QHBoxLayout
from PyQt6.QtWidgets    import QFileDialog, QWidget

from ui.widgets         import * 

from model.airfoil            import Airfoil, Airfoil_Bezier, Airfoil_Hicks_Henne
from model.airfoil            import GEO_BASIC, GEO_SPLINE, NORMAL
from model.airfoil_geometry   import Geometry, Side_Airfoil_Bezier, UPPER, LOWER
from model.airfoil_geometry   import Match_Side_Bezier
from model.airfoil_examples   import Root_Example


# ----- common methods -----------

def create_airfoil_from_path (pathFilename) -> Airfoil:
    """
    Create and return a new airfoil based on pathFilename.
        Return None if the Airfoil couldn't be loaded  
    """

    if pathFilename == "Root_Example":
        airfoil = Root_Example()
    else:
        extension = os.path.splitext(pathFilename)[1]
        if extension == ".bez":
            airfoil = Airfoil_Bezier (pathFileName=pathFilename)
        elif extension == ".hicks":
            airfoil = Airfoil_Hicks_Henne (pathFileName=pathFilename)
        else: 
            airfoil = Airfoil(pathFileName=pathFilename, geometry=GEO_BASIC)
    airfoil.set_usedAs (NORMAL)
    airfoil.load()

    if airfoil.isLoaded:                      # could have been error in loading
        return airfoil
    else:
        return None 


def get_airfoil_files_sameDir (initialDir : Airfoil | str | None): 
    """ 
    Returns list of airfoil file path in the same directory as airfoil
    All .dat, .bez and .hicks files are collected 
    """

    if initialDir is None: return []

    if isinstance(initialDir, Airfoil):
        airfoil_dir = os.path.dirname(initialDir.pathFileName) 
    else: 
        airfoil_dir = initialDir

    if not airfoil_dir: airfoil_dir = '.'

    if os.path.isdir (airfoil_dir):
        dat_files = fnmatch.filter(os.listdir(airfoil_dir), '*.dat')
        bez_files = fnmatch.filter(os.listdir(airfoil_dir), '*.bez')
        hh_files  = fnmatch.filter(os.listdir(airfoil_dir), '*.hicks')
        airfoil_files = dat_files + bez_files + hh_files
        airfoil_files = [os.path.normpath(os.path.join(airfoil_dir, f)) \
                            for f in airfoil_files if os.path.isfile(os.path.join(airfoil_dir, f))]
        return sorted (airfoil_files, key=str.casefold)
    else:
        return []


# ----- widgets -----------



class Airfoil_Open_Widget (Widget, QWidget):
    """ 
    Button - either Text or Icon to open Airfoil with file select 

    When user successfully selected an airfoil file, 'set' is called with 
    the new <Airfoil> as argument 
    """

    default_width  = 80

    def __init__(self, *args,
                 set = None,                # will set new airfoil
                 asIcon = False,            # Button as icon 
                 **kwargs):
        super().__init__(*args, set=set, **kwargs)

        self._get_properties ()
        self._set_Qwidget_static ()

        if asIcon:
            widget= ToolButton (None, icon=ToolButton.ICON_OPEN, set=self._open)
        else: 
            widget = Button    (None, text="&Open", width=self.default_width, set=self._open)

        # assign widget to parent layout 

        self._layout_add (widget)


    def _open (self):
        """ open a new airfoil and load it"""

        filters  = "Airfoil files (*.dat);;Bezier files (*.bez);;Hicks Henne files (*.hicks)"
        newPathFilename, _ = QFileDialog.getOpenFileName(self, filter=filters)

        if newPathFilename:                         # user pressed open
            airfoil = create_airfoil_from_path (newPathFilename)
            if airfoil is not None: 
                self._set_value (airfoil)           # call parent with new airfoil 




class Airfoil_Select_Open_Widget (Widget, QWidget):
    """ 
    Compound widget to either select or open new airfoil 
        - ComboBox (optional with spin) with files in same directory
        - optional Open button to select new airfoil 
        - optional Delete button to delete current   

    When user successfully selected an airfoil file, 'set' is called with 
    the new <Airfoil> as argument 

    When user deleted, 'set' is called with None 
    """

    default_width  = (120, None)

    def __init__(self, *args,
                 get = None,                # get current / initial airfoil 
                 set = None,                # will set new airfoil
                 addEmpty = False,           # add empty entry to fie list 
                 asSpin = True,             # ComboBox with spin buttons 
                 withOpen = False,          # include open button 
                 initialDir : Airfoil | str | None = None, # either an airfoil or a pathString 
                 **kwargs):
        super().__init__(*args, get=get, set=set, **kwargs)

        self._combo = None 
        self._initial_dir = initialDir
        self._addEmpty = addEmpty is True 

        self._get_properties ()
        self._set_Qwidget_static ()

        # build local HBox layout 

        l = QHBoxLayout(self)
        l.setContentsMargins (QMargins(0, 0, 0, 0))
        l.setSpacing (1)
        l.setStretch (0,2)

        if asSpin: 
            self._combo = ComboSpinBox (l, get=self.airfoil_fileName, 
                                           set=self.set_airfoil_by_fileName, 
                                           options=self.airfoil_fileNames_sameDir)
        else:             
            self._combo = ComboBox     (l, get=self.airfoil_fileName, 
                                           set=self.set_airfoil_by_fileName, 
                                           options=self.airfoil_fileNames_sameDir)
        if withOpen:
            Airfoil_Open_Widget (l, asIcon=True, set=self.set_airfoil_from_open)

        self.setLayout (l)

        # assign self to parent layout 

        self._layout_add ()

    @property
    def airfoil (self) -> Airfoil:
        return self._val
    def set_airfoil (self, anAirfoil : Airfoil):
        self._set_value (anAirfoil)           # call parent with new airfoil 


    def set_airfoil_from_open (self, anAirfoil : Airfoil):
        self.set_airfoil (anAirfoil)  
        self._combo.refresh()         


    def airfoil_fileName (self) -> str | None:
        return self.airfoil.fileName if self.airfoil is not None else None

    def set_airfoil_by_fileName (self, newFileName): 
        """ set new current airfoil bei filename""" 

        # Empty selected - set airfoil to None
        if not newFileName:
            self.set_airfoil (None)
            return 

        # get full path of new fileName 
        if self.airfoil is None:
            sameDir = self._initial_dir
        else: 
            sameDir = self.airfoil

        for aPathFileName in get_airfoil_files_sameDir (sameDir):
            if newFileName == os.path.basename(aPathFileName):

                if os.path.isfile (aPathFileName) or newFileName == 'Root_Example':   # maybe it was deleted in meantime 
                     
                    airfoil = create_airfoil_from_path (aPathFileName)
                    if airfoil is not None: 
                        self.set_airfoil (airfoil)
                break


    def airfoil_fileNames_sameDir (self): 
        """ list of airfoil filenames in the same dir as current airfoil"""

        if self.airfoil is None:
            sameDir = self._initial_dir
        else: 
            sameDir = self.airfoil

        fileNames = []
        if self._addEmpty: 
            fileNames.append ("")
           
        for aFileName in get_airfoil_files_sameDir (sameDir):
            fileNames.append(os.path.basename(aFileName))
        return fileNames


    def _open (self):
        """ open a new airfoil and load it"""

        filters  = "Airfoil files (*.dat);;Bezier files (*.bez);;Hicks Henne files (*.hicks)"
        newPathFilename, _ = QFileDialog.getOpenFileName(self, filter=filters)

        if newPathFilename:                         # user pressed open
            airfoil = create_airfoil_from_path (newPathFilename)
            if airfoil is not None: 
                self._set_value (airfoil)           # call parent with new airfoil 

