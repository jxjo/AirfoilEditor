#!/usr/bin/env pythonbutton_color
# -*- coding: utf-8 -*-

"""  

Higher level Widgets to handle Airfoil UI operations like Open and Select

"""

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

import os
import fnmatch             

from PyQt6.QtCore           import QMargins
from PyQt6.QtWidgets        import QHBoxLayout, QLayout
from PyQt6.QtWidgets        import QFileDialog, QWidget

from base.widgets           import * 
from base.panels            import Dialog 


from model.airfoil          import Airfoil, Airfoil_Bezier, Airfoil_Hicks_Henne
from model.airfoil          import GEO_BASIC, usedAs
from model.airfoil_examples import Example


# ----- common methods -----------

def create_airfoil_from_path (pathFilename) -> Airfoil:
    """
    Create and return a new airfoil based on pathFilename.
        Return None if the Airfoil couldn't be loaded  
    """

    if pathFilename == Example.fileName:
        airfoil = Example()
    else:
        extension = os.path.splitext(pathFilename)[1]
        if extension == ".bez":
            airfoil = Airfoil_Bezier (pathFileName=pathFilename)
        elif extension == ".hicks":
            airfoil = Airfoil_Hicks_Henne (pathFileName=pathFilename)
        else: 
            airfoil = Airfoil(pathFileName=pathFilename, geometry=GEO_BASIC)
    airfoil.set_usedAs (usedAs.NORMAL)
    airfoil.load()

    if airfoil.isLoaded:                      # could have been error in loading
        return airfoil
    else:
        logger.error (f"Could not load '{pathFilename}'")
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


    def __init__(self, *args,
                 set = None,                # will set new airfoil
                 asIcon = False,            # Button as icon 
                 **kwargs):
        super().__init__(*args, set=set, **kwargs)

        # build local HBox layout with the guest widget

        l = QHBoxLayout(self)
        l.setContentsMargins (QMargins(0, 0, 0, 0))
        l.setSpacing (0)
        l.setStretch (0,2)
        if asIcon:
            widget= ToolButton (l, icon=icon.OPEN, set=self._open, toolTip="Select airfoil")
            self._width = widget._width             # self shall have the same fixed width
        else: 
            widget = Button    (l, text="&Open", width=self._width, set=self._open, toolTip="Select airfoil")
        self.setLayout (l) 

        # normal widget handling 

        self._get_properties ()
        self._set_Qwidget_static ()
        self._set_Qwidget ()

        # assign widget to parent layout 

        self._layout_add ()


    def _open (self):
        """ open a new airfoil and load it"""

        filters  = "Airfoil files (*.dat);;Bezier files (*.bez);;Hicks Henne files (*.hicks)"
        newPathFilename, _ = QFileDialog.getOpenFileName(self, filter=filters)

        if newPathFilename:                         # user pressed open
            airfoil = create_airfoil_from_path (newPathFilename)
            if airfoil is not None: 

                #leave button callback and refresh in a few ms 
                timer = QTimer()                                
                timer.singleShot(10, lambda: self._set_value (airfoil))     # delayed emit 




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

    _width  = (120, None)

    def __init__(self, *args,
                 get = None,                # get current / initial airfoil 
                 set = None,                # will set new airfoil
                 addEmpty = False,          # add empty entry to fie list 
                 asSpin = True,             # ComboBox with spin buttons 
                 withOpen = False,          # include open button 
                 initialDir : Airfoil | str | None = None, # either an airfoil or a pathString 
                 **kwargs):
        super().__init__(*args, get=get, set=set, **kwargs)

        self._combo = None 
        self._initial_dir = initialDir
        self._addEmpty = addEmpty is True 

        # build local HBox layout with the guest widget

        l = QHBoxLayout(self)
        l.setContentsMargins (QMargins(0, 0, 0, 0))
        l.setSpacing (1)
        l.setStretch (0,2)
        l.setStretch (1,0)
        if asSpin: 
            self._combo = ComboSpinBox (l, get=self.airfoil_fileName, 
                                           set=self.set_airfoil_by_fileName, 
                                           options=self.airfoil_fileNames_sameDir,
                                           signal=False)
        else:             
            self._combo = ComboBox     (l, get=self.airfoil_fileName, 
                                           set=self.set_airfoil_by_fileName, 
                                           options=self.airfoil_fileNames_sameDir,
                                           signal=False)
        if withOpen:
            Airfoil_Open_Widget (l, asIcon=True, set=self.set_airfoil_from_open, signal=False)
        self.setLayout (l)

        # normal widget handling 

        self._get_properties ()
        self._set_Qwidget_static ()

        # assign self to parent layout 

        self._layout_add ()


    def _get_properties (self): 
        """
        Read all the properties like disablee, style as they can be 
            - bound methods
            - fixed values 
            - property (only for self._val)
        """
        super()._get_properties()
        # access value' either via property approach or via getter (bound method) 

    @property
    def airfoil (self) -> Airfoil:
        return self._val
    def set_airfoil (self, anAirfoil : Airfoil):

        #leave button callback and refresh in a few ms 
        timer = QTimer()                                
        timer.singleShot(10, lambda: self._set_value (anAirfoil))    
        # self._set_value (anAirfoil)           # call parent with new airfoil 


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

                if os.path.isfile (aPathFileName) or newFileName == Example.fileName:   # maybe it was deleted in meantime 
                     
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

        if self.airfoil is not None and self.airfoil.isExample:
            fileNames.append(Example.fileName)
        return fileNames


    def _open (self):
        """ open a new airfoil and load it"""

        filters  = "Airfoil files (*.dat);;Bezier files (*.bez);;Hicks Henne files (*.hicks)"
        newPathFilename, _ = QFileDialog.getOpenFileName(self, filter=filters)

        if newPathFilename:                         # user pressed open
            airfoil = create_airfoil_from_path (newPathFilename)
            if airfoil is not None: 
                self._set_value (airfoil)           # call parent with new airfoil 





class Airfoil_Save_Dialog (Dialog):
    """ 
    Button - either Text or Icon to open Airfoil with file select 

    When user successfully selected an airfoil file, 'set' is called with 
    the new <Airfoil> as argument 
    """

    _width  = (500, None)
    _height = 250

    name = "Save Airfoil ..."

    @property
    def airfoil (self) -> Airfoil:
        return self.dataObject_copy


    def _init_layout(self) -> QLayout:

        l = QGridLayout()
        r = 0 
        SpaceR (l, r) 
        r += 1
        Field  (l,r,0, lab="Name", obj= self.airfoil, prop=Airfoil.name, width=(150,None),
                       style=self._style_names)
        Button (l,r,2, text="Use Filename", set=self.airfoil.set_name_from_fileName, width=90,
                       hide=self._names_are_equal, signal=True,
                       toolTip="Use filename as airfoil name")
        r += 1
        SpaceR (l, r, stretch=0) 
        r += 1
        Field  (l,r,0, lab="Filename", obj=self.airfoil, prop=Airfoil.fileName, width=(150,None))
        Button (l,r,2, text="Use Name", set=self.airfoil.set_fileName_from_name, width=90,
                       hide=self._names_are_equal, signal=True,
                       toolTip="Use airfoil name as filename")
        r += 1
        Field  (l,r,0, lab="Directory", obj=self.airfoil, prop=Airfoil.pathName, width=(150,None),
                       disable=True)
        ToolButton (l,r,2, icon=icon.OPEN, set=self._open_dir, signal=True,
                    toolTip = 'Select directory of airfoil') 
        r += 1
        SpaceR (l, r, stretch=1) 
        r += 1
        Label  (l,r,1, colSpan=4, get=self._messageText, style=style.COMMENT, height=(30,None))
        r += 1
        SpaceR (l, r, height=1, stretch=4) 
        l.setColumnStretch (1,5)
        l.setColumnMinimumWidth (0,80)
        l.setColumnMinimumWidth (2,35)
        return l


    def _on_widget_changed (self, *_):
        """ slot for change of widgets"""

        # delayed refresh as pressed button hides itsself 
        timer = QTimer()                                
        timer.singleShot(50, self.refresh)     # delayed emit 


    def _names_are_equal (self) -> bool: 
        """ is airfoil name different from filename?"""
        fileName_without = os.path.splitext(self.airfoil.fileName)[0]
        return fileName_without == self.airfoil.name


    def _style_names (self):
        """ returns style.WARNING if names are different"""
        if not self._names_are_equal(): 
            return style.WARNING
        else: 
            return style.NORMAL


    def _messageText (self): 
        """ info / wanrning text"""
        text = []
        if not self._names_are_equal():
             text.append("Name of airfoil and its filename are different.")
             text.append("You maybe want to 'sync' either the name or the filename.")
        text = '\n'.join(text)
        return text 



    def _open_dir (self):
        """ open directory and set to airfoil """

        select_dir = os.path.dirname(self.airfoil.pathName)     # take parent of current
        pathName_new = QFileDialog.getExistingDirectory(self, caption="Select directory",
                                                           directory=select_dir)
        if pathName_new:                         # user pressed open
            self.airfoil.set_pathName (pathName_new)



    def accept(self):
        """ Qt overloaded - ok - save airfoil"""

        # set original airfoil with data 
        airfoil : Airfoil = self.dataObject 
        airfoil_copy : Airfoil = self.dataObject_copy

        airfoil.set_name (airfoil_copy.name)
        airfoil.set_pathFileName (airfoil_copy.pathFileName, noCheck=True)

        airfoil.save ()

        super().accept() 