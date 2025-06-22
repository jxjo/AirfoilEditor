#!/usr/bin/env pythonbutton_color
# -*- coding: utf-8 -*-

"""  

Handle Airfoil UI operations like Open and Select

"""

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

import os
import fnmatch             

from PyQt6.QtCore           import QMargins
from PyQt6.QtWidgets        import QHBoxLayout
from PyQt6.QtWidgets        import QFileDialog, QWidget

from base.widgets           import * 
from base.panels            import MessageBox

from model.airfoil          import Airfoil, Airfoil_Bezier, Airfoil_Hicks_Henne
from model.airfoil          import GEO_BASIC
from model.airfoil_examples import Example


# ------ colors of modes ----------------------------------


class mode_color:
    """ colors as kwargs for the different modes """

    MODIFY        = {'color': 'deeppink',          'alpha' : 0.2 }
    OPTIMIZE      = {'color': 'mediumspringgreen', 'alpha' : 0.2 }  # darkturquoise


# ----- common methods -----------


def create_airfoil_from_path (parent, pathFilename, example_if_none=False, message_delayed=False) -> Airfoil:
    """
    Create and return a new airfoil based on pathFilename.
        Return None if the Airfoil couldn't be loaded 
        or 'Example' airfoil if example_if_none == True  
    """

    file_found     = False
    airfoil_loaded = False
    airfoil        = None

    try: 
        airfoil = Airfoil.onFileType(pathFilename, geometry=GEO_BASIC)
        airfoil.load()
        airfoil_loaded = airfoil.isLoaded
        file_found     = True
    except:
        pass

    if not airfoil_loaded:

        airfoil = Example() if example_if_none else None

        if pathFilename: 
            fileName = os.path.basename (pathFilename)
            
            msg     = f"<b>{fileName}</b> does not exist." if not file_found else f"<b>{fileName}</b> couldn't be loaded."
            example = "\nUsing example airfoil." if example_if_none else ""

            if message_delayed:
                QTimer.singleShot (100, lambda: MessageBox.error   (parent,'Load Airfoil', f"{msg}{example}", min_height= 60))
            else:
                MessageBox.error   (parent,'Load Airfoil', f"{msg}{example}", min_height= 60)

    return airfoil  



def get_airfoil_fileNames_sameDir (airfoil_or_dir : Airfoil | str | None) -> list[str]: 
    """ 
    Returns list of airfoil file names in the same directory as airfoil
        airfoil can be either an Airfoil or a subdirectory
    Returns all .dat, .bez and .hicks files 
    """

    if airfoil_or_dir is None: return []

    if isinstance(airfoil_or_dir, Airfoil):
        airfoil : Airfoil = airfoil_or_dir
        if airfoil.pathFileName_abs is not None: 
            airfoil_dir = os.path.dirname(airfoil.pathFileName_abs) 
        else:
            airfoil_dir = None 
    else: 
        airfoil_dir = airfoil_or_dir

    if not airfoil_dir: airfoil_dir = '.'

    if os.path.isdir (airfoil_dir):
        dat_files = fnmatch.filter(os.listdir(airfoil_dir), '*.dat')
        bez_files = fnmatch.filter(os.listdir(airfoil_dir), '*.bez')
        hh_files  = fnmatch.filter(os.listdir(airfoil_dir), '*.hicks')
        airfoil_files = dat_files + bez_files + hh_files
        return sorted (airfoil_files, key=str.casefold)
    else:
        return []


def get_next_airfoil_in_dir (anAirfoil : Airfoil, example_if_none=False) -> Airfoil: 
    """ 
    Returns next airfoil following anAirfoil in the same directory 
        - or the last airfoil in the directory if anAirfoil was already the last one
        - Example.dat if there are no more airfoil files in the directory 
    """

    airfoil_files = get_airfoil_fileNames_sameDir (anAirfoil)

    # get index 
    try: 
        iair = airfoil_files.index(anAirfoil.fileName)
    except: 
        iair = None

    # get next 
    if iair is not None and len(airfoil_files) > 1: 
        if iair == (len (airfoil_files) - 1):
            next_file = airfoil_files [iair - 1] 
        else:
            next_file = airfoil_files [iair + 1]
    elif iair is not None and len(airfoil_files) == 1: 
        next_file = None
    else: 
        next_file = airfoil_files [0] if airfoil_files else None 

    if next_file: 
        next_airfoil = Airfoil.onFileType(next_file, workingDir = anAirfoil.pathName_abs, geometry=GEO_BASIC)
        next_airfoil.load()
    elif example_if_none:
        next_airfoil = Example()
    else: 
        next_airfoil = None 
 
    return next_airfoil




# ----- widgets -----------


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
    _height = 26 

    def __init__(self, *args,
                 get = None,                # get current / initial airfoil 
                 set = None,                # will set new airfoil
                 addEmpty = False,          # add empty entry to fie list 
                 asSpin = False,            # ComboBox with spin buttons 
                 withOpen = True,           # include open button 
                 textOpen = "Open",         # text for Open button 
                 widthOpen = 100,           # width of open text button 
                 initialDir : Airfoil | str | None = None, # either an airfoil or a pathString 
                 **kwargs):
        super().__init__(*args, get=get, set=set, **kwargs)

        self._combo_widget  = None 
        self._button_widget = None 
        self._icon_widget   = None 

        self._no_files_here = None
        self._addEmpty = addEmpty is True 
        if isinstance (initialDir, Airfoil):
            airfoil : Airfoil = initialDir
            self._initial_dir = airfoil.pathName_abs
        else:
            self._initial_dir = initialDir

        # get initial properties  (cur airfoil) 
        self._get_properties ()

        # build local HBox layout with the guest widget

        l = QHBoxLayout(self)
        l.setContentsMargins (QMargins(0, 0, 0, 0))
        if asSpin: 
            self._combo_widget = ComboSpinBox (l, get=self.airfoil_fileName, 
                                                set=self.set_airfoil_by_fileName, 
                                                options=self.airfoil_fileNames_sameDir,
                                                hide=self.no_files_here,
                                                toolTip=None,               # is set separately 
                                                signal=False)
        else:             
            self._combo_widget = ComboBox      (l, get=self.airfoil_fileName, 
                                                set=self.set_airfoil_by_fileName, 
                                                options=self.airfoil_fileNames_sameDir,
                                                hide=self.no_files_here, 
                                                toolTip=None,               # is set separately 
                                                signal=False)
        if withOpen:

            # either text button if nothing is there
            self._button_widget = Button (l, text=textOpen, set=self._open_airfoil, 
                                                signal=False, width = widthOpen,
                                                hide=lambda: not self.no_files_here() ) 
            # ... or icon button together with combo box 
            self._icon_widget =   ToolButton (l, icon=Icon.OPEN, set=self._open_airfoil, signal=False,
                                                hide=self.no_files_here,
                                                toolTip="Select an airfoil in a different directory")
            # l.insertStretch (-1)

        l.setContentsMargins (QMargins(0, 0, 0, 0))

        if self.no_files_here():                                # show only open button
            l.setSpacing (0)
            l.setStretch (0,0)
            l.setStretch (2,2)
        else:                                                   # combobox with open 
            l.setSpacing (1)
            l.setStretch (0,2)
            l.setStretch (2,0)

        self.setLayout (l)

        # normal widget handling 

        self._layout_add ()                                     # put into layout - so it gets parent early

        self._get_properties ()
        self._set_Qwidget_static ()
        self._set_Qwidget ()
        self._set_comboBox_tooltip ()


    @override
    def refresh (self, disable=None):

        self._no_files_here = None                              # reset cached vlaue 
        super().refresh(disable) 

        if self._combo_widget:
            self._combo_widget.refresh (disable) 
            self._set_comboBox_tooltip ()
        if self._button_widget:
            self._button_widget.refresh (disable) 
        if self._icon_widget:
            self._icon_widget.refresh (disable) 

        l : QHBoxLayout = self.layout()
        if self.no_files_here():                                # show only open button
            l.setSpacing (0)
            l.setStretch (0,0)
            l.setStretch (2,2)
        else:                                                   # combobox with open 
            l.setSpacing (1)
            l.setStretch (0,2)
            l.setStretch (2,0)


    def _open_airfoil (self):
        """ open a new airfoil and load it"""

        filters  = "Airfoil files (*.dat);;Bezier files (*.bez);;Hicks Henne files (*.hicks)"

        if isinstance (self._val, Airfoil):
            directory = self._val.pathName_abs
        else:
            directory = None 
        newPathFilename, _ = QFileDialog.getOpenFileName(self, filter=filters, directory=directory)

        if newPathFilename:                         # user pressed open
            airfoil = create_airfoil_from_path (self, newPathFilename)
            if airfoil is not None: 

                #leave button callback and refresh in a few ms 
                timer = QTimer()                                
                timer.singleShot(10, lambda: self.set_airfoil (airfoil))     # delayed emit 


    def no_files_here (self) -> bool:
        """ True if no files to select in combo """

        if self._no_files_here is None: 
            n = len (self.airfoil_fileNames_sameDir())
            if n== 1:
                # there can be a blank or exmaple entry as the first item 
                fileName_first = self.airfoil_fileNames_sameDir()[0]
                no =  fileName_first == ""
            elif n == 0: 
                no =  True
            else: 
                no = False
            self._no_files_here = no 
        return self._no_files_here


    @property
    def airfoil (self) -> Airfoil:
        return self._val
    def set_airfoil (self, anAirfoil : Airfoil):

        self._no_files_here = None                      # reset cached value 

        self._set_value (anAirfoil)

        # refresh the sub widgets -> hide / show 
        w : Widget
        for w in self.findChildren (Widget):
            w.refresh()

        self._set_comboBox_tooltip()


    def airfoil_fileName (self) -> str | None:
        return self.airfoil.fileName if self.airfoil is not None else None


    def set_airfoil_by_fileName (self, newFileName): 
        """ set new current airfoil bei filename""" 

        # Empty selected - set airfoil to None
        if not newFileName:
            self.set_airfoil (None)
            return 

        # is fileName in directory ?

        fileNames = get_airfoil_fileNames_sameDir (self.airfoil if self.airfoil else self._initial_dir)

        if newFileName in fileNames: 

            # create and set new airfoil

            workingDir = self.airfoil.pathName_abs if self.airfoil else self._initial_dir
            try:
                new_airfoil = Airfoil.onFileType(newFileName, workingDir = workingDir, geometry=GEO_BASIC)
                new_airfoil.load()
                self.set_airfoil (new_airfoil)
            except:
                logger.error (f"Couldn't create Airfoil {newFileName}")
        

    def airfoil_fileNames_sameDir (self): 
        """ list of airfoil filenames in the same dir as current airfoil"""


        fileNames = get_airfoil_fileNames_sameDir (self.airfoil if self.airfoil else self._initial_dir)

        if self._addEmpty: 
            fileNames.insert (0,"")  
        return fileNames


    def _set_comboBox_tooltip (self):
        """ set tooltip for comboBox - normally pathFileName of airfoil"""

        if self._combo_widget:

            toolTip = self.airfoil.info_as_html if self.airfoil else self._toolTip 

            self._combo_widget.setToolTip (toolTip)  
