#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Airfoil Editor 

    Object model overview (a little simplified) 

    App                                         - root frame 
        |-- Panel_Geometry                      - geometry data 
        |-- Panel_Coordinates                   - LE and TE coordinates
                ...                             - ...

        |-- Airfoil_Diagram                     - main airfoil view 
                :
                |-- Airfoil_Diagram_Item        - Pyqtgraph Plot item for airfoil contour
                |-- Curvature_Diagram_Item      - Pyqtgraph Plot item for airfoil curvature 
                ...                             - ...

        |-- Airfoil                             - airfoil model object 
"""

import os
import sys
import argparse

from PyQt6.QtCore           import pyqtSignal, QMargins, Qt
from PyQt6.QtWidgets        import QApplication, QMainWindow, QWidget 
from PyQt6.QtWidgets        import QGridLayout
from PyQt6.QtGui            import QCloseEvent, QGuiApplication

from model.xo2_input        import Input_File
from model.case             import Case_Optimize

from base.common_utils      import * 
from base.panels            import Win_Util
from base.widgets           import Icon, Widget
from base.app_utils         import Settings, Update_Checker

from ae_widgets             import create_airfoil_from_path
from ae_diagrams            import Diagram_Airfoil_Polar
from ae_app_model              import App_Model
from app_modes              import (Modes_Manager, Mode_View, Mode_Modify, Mode_Optimize, Mode_Id, 
                                    Mode_As_Bezier)

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


#-------------------------------------------------------------------------------
# The App   
#-------------------------------------------------------------------------------


APP_NAME         = "AirfoilEditor"
PACKAGE_NAME     = "airfoileditor"
__version__      = "4.2.0"                              # hatch "version dynamic" reads this version for build


class Main (QMainWindow):
    '''
        App - Main Window 
    '''

    # Qt Signals 

    sig_xo2_about_to_run        = pyqtSignal()          # short before optimization starts
    sig_xo2_new_state           = pyqtSignal()          # Xoptfoil2 new info/state

    sig_closing                 = pyqtSignal(str)       # the app is closing with an airfoils pathFilename


    def __init__(self, initial_file, parent_app=None):
        super().__init__(parent_app)


        # --- init Settings, check for newer app version ---------------

        Settings.set_file (APP_NAME, file_extension= '.settings')

        Update_Checker (self, APP_NAME, PACKAGE_NAME,  __version__)   


        # --- init App Model ---------------

        app_model = App_Model (workingDir_default=Settings.user_data_dir (APP_NAME))

        # either airfoil file or Xoptfoil2 input file

        initial_file = self._check_or_get_initial_file(initial_file)

        if Input_File.is_xo2_input (initial_file):
            initial = initial_file
            mode_to_start = Mode_Id.OPTIMIZE
        else:
            airfoil = create_airfoil_from_path (self, initial_file, example_if_none=True, message_delayed=True)
            initial = airfoil
            mode_to_start = Mode_Id.VIEW

        # load initial settings like polar definitions 

        app_model.load_settings ()                                          # either global or airfoil specific settings
        app_model.sig_new_airfoil.connect (self._set_win_title)             # update title on new airfoil
        app_model.sig_new_case.connect    (self._set_win_title)             # update title on new case

        self._app_model     = app_model                                     # keep for close 


        # --- App Modes and Manager ---------------
        
        modes_manager = Modes_Manager (app_model)
        modes_manager.add_mode (Mode_View       (app_model))
        modes_manager.add_mode (Mode_Modify     (app_model))
        modes_manager.add_mode (Mode_Optimize   (app_model))
        modes_manager.add_mode (Mode_As_Bezier  (app_model))

        modes_manager.sig_close_requested.connect (self.close)              # app close requested from mode view
        modes_manager.set_mode (mode_to_start, initial)                     # either in view mode or optimize mode

        self._modes_manager = modes_manager                                 # keep as it hosts slots


        # --- init UI ---------------
        
        logger.info (f"Initialize UI")

        self._set_win_title ()
        self._set_win_style (parent=parent_app)
        self._set_win_geometry ()

        # main widgets and layout of app

        diagram     = Diagram_Airfoil_Polar (app_model)                     # big diagram widget
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

        self._diagram = diagram                                             # keep for closedown


        # --- Enter event loop ---------------

        logger.info (f"{modes_manager.current_mode} ready")



    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"


    def _check_or_get_initial_file (self, initial_file : str) -> str:
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


    # --- private ---------------------------------------------------------


    def _set_win_title (self):
        """ set window title with airfoil or case name """

        case    = self._app_model.case
        airfoil = self._app_model.airfoil
        if isinstance (case, Case_Optimize):
            ext = f"[Case {case.name if case else '?'}]"
        else: 
            ext = f"[{airfoil.fileName if airfoil else '?'}]"

        self.setWindowTitle (APP_NAME + "  v" + str(__version__) + "  " + ext)


    def _set_win_style (self, parent : QWidget = None):
        """ 
        Set window style according to settings
            - if app has parent, self will be modal
        """

        self.setWindowIcon (Icon ('AE_ico.ico'))                                    # get icon either in modules or in icons 

        scheme_name = Settings().get('color_scheme', Qt.ColorScheme.Unknown.name)   # either unknown (from System), Dark, Light
        QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme[scheme_name])    # set scheme of QT
        Widget.light_mode = not (scheme_name == Qt.ColorScheme.Dark.name)           # set mode for Widgets

        if parent is not None:
            self.setWindowModality(Qt.WindowModality.ApplicationModal)  


    def _set_win_geometry (self):
        """ set window geometry from settings """

        app_settings = Settings()                      # load app settings

        geometry = app_settings.get('window_geometry', [])
        maximize = app_settings.get('window_maximize', False)
        Win_Util.set_initialWindowSize (self, size_frac= (0.85, 0.80), pos_frac=(0.1, 0.1),
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


        # inform parent (PlanformCreator) 
        if self._app_model.airfoil: 
            self.sig_closing.emit (self._app_model.airfoil.pathFileName)

        event.accept()




#--------------------------------

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

    app = QApplication(sys.argv)
    app.setStyle('fusion')

    main = Main (initial_file)
    main.show()
    rc = app.exec()
    return rc 



if __name__ == "__main__":
    
    sys.exit (start())