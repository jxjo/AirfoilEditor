#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Airfoil Editor 

    Object model overview (a little simplified) 

    App                                         - Main 
        |-- App_Mode                            - different UI modes like View, Modify, Optimize 
            |-- Data_Panel                      - UI lower data panel for mode 
                |-- Panel_Geometry              - UI single panel with fields 

            |-- Airfoil_Diagram                 - UI upper diagram area 
                |-- Airfoil_Diagram_Item        - UI a single plot item within diagram
                    |-- Curvature_Artist        - UI curvature plot artist
            
        |-- App_Model                           - App shell around data model allowing signals
            |-- Airfoil                         - airfoil model object 
            |-- Case                            - handle different like optimize, modify 
                |-- Xo2_Input                   - main object optimization - represents an X02 input file 
        
"""

from ast import Add
import os
import sys
import argparse

from PyQt6.QtCore           import pyqtSignal, QMargins, Qt
from PyQt6.QtWidgets        import QApplication, QMainWindow, QWidget 
from PyQt6.QtWidgets        import QGridLayout
from PyQt6.QtGui            import QCloseEvent, QGuiApplication, QIcon

# DEV: when running app.py as main, set package property to allow relative imports
if __name__ == "__main__":  
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "airfoileditor"

from .resources              import get_icons_path, get_icon_path
from .base.common_utils      import * 

from .model.xo2_input        import Input_File
from .model.case             import Case_Optimize, Case_Direct_Design

from .base.panels            import Win_Util
from .base.widgets           import Icon, Widget
from .base.app_utils         import Settings, Update_Checker, Run_Checker, check_or_get_initial_file

from .ui.ae_widgets          import create_airfoil_from_path
from .ui.ae_diagrams         import Diagram_Airfoil_Polar

from .app_model              import App_Model, Mode_Id
from .app_modes              import Modes_Manager, Mode_View, Mode_Modify, Mode_Optimize, Mode_As_Bezier

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)

#-------------------------------------------------------------------------------
# The App   
#-------------------------------------------------------------------------------


APP_NAME         = "AirfoilEditor"
PACKAGE_NAME     = "airfoileditor"
__version__      = "4.2.5"                  # hatch "version dynamic" - PEP440 compliant version string
                                            # for Github use SemVer "4.2.0-beta.3"

CHANGE_TEXT      = "- Switch between polar diagram variables" # + \
                #    "- Revised Match Bezier UI<br>"


class Main (QMainWindow):
    '''
        App - Main Window 
    '''

    # Qt Signals 

    sig_xo2_about_to_run        = pyqtSignal()          # short before optimization starts
    sig_xo2_new_state           = pyqtSignal()          # Xoptfoil2 new info/state


    def __init__(self, initial_file):
        super().__init__()

        logger.info (f"Init Main Window")

        # --- init Settings, check for newer app version ---------------

        Settings.set_file (APP_NAME, file_extension= '.settings')

        is_first_run = Run_Checker.is_first_run (__version__)                 # to show Welcome message
        
        Update_Checker (self, APP_NAME, PACKAGE_NAME,  __version__) 


        # --- init App Model ---------------

        app_model = App_Model (workingDir_default=Settings.user_data_dir (APP_NAME))

        app_model.set_app_info (__version__, CHANGE_TEXT, is_first_run)

        # either airfoil file or Xoptfoil2 input file

        initial_file = check_or_get_initial_file (initial_file)

        if Input_File.is_xo2_input (initial_file):
            initial = initial_file
            mode_to_start = Mode_Id.OPTIMIZE
        else:
            airfoil = create_airfoil_from_path (self, initial_file, example_if_none=True, message_delayed=True)
            initial = airfoil
            mode_to_start = Mode_Id.VIEW

        # load initial settings like polar definitions 

        app_model.load_settings ()                                          # global settings (no airfoil set)
        app_model.sig_new_airfoil.connect (self._set_win_title)             # update title on new airfoil
        app_model.sig_new_mode.connect    (self._set_win_title)             # update title on new case

        self._app_model     = app_model                                     # keep for close 


        # --- init UI ---------------

        # main window style - dark or light mode

        self._set_win_style (app_icon_name='AE.ico')
        self._set_win_title ()
        self._set_win_geometry ()

        # app Modes and manager  
        
        logger.info (f"Init Modes Manager")

        modes_manager = Modes_Manager (app_model)
        modes_manager.add_mode (Mode_View       (app_model))
        modes_manager.add_mode (Mode_Modify     (app_model))
        modes_manager.add_mode (Mode_Optimize   (app_model))
        modes_manager.add_mode (Mode_As_Bezier  (app_model))

        modes_manager.set_mode (mode_to_start, initial)                     # set initial object in app_model
        modes_manager.sig_close_requested.connect (self.close)              # app close requested from mode view

        self._modes_manager = modes_manager                                 # keep as it hosts slots

        # main widgets and layout of app

        logger.info (f"Init UI - mode: {modes_manager.current_mode}")

        diagram     = Diagram_Airfoil_Polar (self,app_model)                # big diagram widget
        modes_panel = modes_manager.stacked_modes_panel()                   # stacked widget with mode data panels

        l = QGridLayout () 
        l.addWidget (diagram,     0,0)
        l.addWidget (modes_panel, 1,0)

        l.setRowStretch (0,1)
        l.setRowMinimumHeight (0,400)
        modes_manager.set_height (180, minimized=65)
        
        l.setSpacing (5)
        l.setContentsMargins (QMargins(5, 5, 5, 5))

        main = QWidget()
        main.setLayout (l) 
        self.setCentralWidget (main)

        self._diagram = diagram                                             # keep for close down


        # --- Enter event loop ---------------

        logger.info (f"{modes_manager.current_mode} ready - entering event loop")


    # --- private ---------------------------------------------------------


    def _set_win_title (self):
        """ set window title with airfoil or case name """

        case    = self._app_model.case
        airfoil = self._app_model.airfoil
        if isinstance (case, Case_Optimize):
            ext = f"[Case {case.name if case else '?'}]"
        elif isinstance (case, Case_Direct_Design):
            seed   = case.airfoil_seed.fileName  
            design = airfoil.name_to_show
            ext = f"[{design} on {seed}]"
        else: 
            ext = f"[{airfoil.fileName if airfoil else '?'}]"

        self.setWindowTitle (APP_NAME + "  v" + str(__version__) + "  " + ext)


    def _set_win_style (self, icons_path : Path = None, app_icon_name : str  = None):
        """ 
        Set window style according to settings
        """

        # set resources dir for Icons
        if icons_path is None:
            icons_path = get_icons_path()
        Icon.ICONS_PATH = icons_path

        # get and set app icon  
        app_icon_path = get_icon_path(app_icon_name) 
        if app_icon_path:
            self.setWindowIcon (QIcon (str(app_icon_path)))  

        # set dark or light mode
        scheme_name = Settings().get('color_scheme', Qt.ColorScheme.Unknown.name)   # either unknown (from System), Dark, Light
        QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme[scheme_name])    # set scheme of QT

        # set mode for Widgets
        Widget.light_mode = not (scheme_name == Qt.ColorScheme.Dark.name)          


    def _set_win_geometry (self):
        """ set window geometry from settings """

        app_settings = Settings()                      # load app settings

        geometry = app_settings.get('window_geometry', [])
        maximize = app_settings.get('window_maximize', False)
        Win_Util.set_initialWindowSize (self, size_frac= (0.80, 0.80), pos_frac=(0.1, 0.1),
                                        geometry=geometry, maximize=maximize)


    def _save_app_settings (self):
        """ save application settings to file """

        s = Settings()

        s.set ('window_maximize', self.isMaximized())
        s.set ('window_geometry', self.normalGeometry().getRect())

        airfoil = self._app_model.airfoil
        if airfoil and not airfoil.isExample: 
            s.set ('last_opened', airfoil.pathFileName_abs)
        else:
            s.set ('last_opened', None)

        s.save()


    @override
    def closeEvent  (self, event : QCloseEvent):
        """ main window is closed """

        # save airfoil settings in app settings
        self._app_model.save_settings (to_app_settings=True,
                                       add_key  = self._diagram.name, 
                                       add_value= self._diagram.settings())

        # terminate polar watchdog thread, clean up working dir 
        self._app_model.close()                            # finish app model

        # save e.g. diagram options 
        self._save_app_settings () 

        event.accept()


#-------------------------------------------------------------------------------


def start ():
    """ start the app """

    # init logging - can be overwritten within a module  

    init_logging (level= logging.INFO)             # INFO, DEBUG or WARNING

    # command line arguments? 
    
    parser = argparse.ArgumentParser(prog=APP_NAME, description='View and modify an airfoil')
    parser.add_argument("airfoil", nargs='*', help="Airfoil .dat or .bez file to show")
    args = parser.parse_args()
    if args.airfoil: 
        initial_file = args.airfoil[0]
    else: 
        initial_file = None

    # init Qt Application and style  

    logger.info (f"Starting {APP_NAME} v{__version__} - Initial file: {initial_file}")

    app = QApplication(sys.argv)
    app.setStyle('fusion')

    main = Main (initial_file)
    main.show()
    rc = app.exec()
    return rc 



if __name__ == "__main__":
    
    sys.exit (start())