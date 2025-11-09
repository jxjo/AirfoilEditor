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
from shutil                 import copyfile
from typing                 import Tuple

from PyQt6.QtCore           import QMargins, QThread
from PyQt6.QtWidgets        import QApplication, QMainWindow, QWidget, QDialog 
from PyQt6.QtWidgets        import QHBoxLayout, QMessageBox
from PyQt6.QtGui            import QCloseEvent, QGuiApplication

from model.airfoil          import Airfoil, usedAs
from model.airfoil_geometry import Panelling_Spline, Panelling_Bezier, Line
from model.polar_set        import Polar_Definition, Polar_Set, Polar_Task
from model.xo2_driver       import Worker, Xoptfoil2
from model.xo2_input        import Input_File
from model.case             import Case_Direct_Design, Case_Optimize, Case_Abstract, Case_As_Bezier

from base.common_utils      import * 
from base.panels            import Container_Panel, Win_Util, Toaster
from base.widgets           import *
from base.app_utils         import *

from airfoil_widgets        import * 
from airfoil_dialogs        import Airfoil_Save_Dialog
from airfoil_diagrams       import Diagram_Airfoil_Polar            
from xo2_dialogs            import (Xo2_Run_Dialog, Xo2_Select_Dialog, Xo2_OpPoint_Def_Dialog, Xo2_New_Dialog)

from app_model              import App_Model
from app_modes              import (Modes_Manager, Mode_View, Mode_Modify, Mode_Optimize, Mode_Id, 
                                    Mode_Abstract, Mode_As_Bezier)

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# print ("\n".join(sys.path))

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

    sig_new_airfoil             = pyqtSignal()          # new airfoil selected 
    sig_geometry_changed        = pyqtSignal()          # airfoil geometry changed 
    sig_etc_changed             = pyqtSignal()          # reference airfoils etc changed

    sig_bezier_changed          = pyqtSignal(Line.Type) # new bezier during match bezier 
    sig_panelling_changed       = pyqtSignal()          # new panelling
    
    sig_polar_set_changed       = pyqtSignal()          # new polar sets attached to airfoil
    sig_enter_panelling         = pyqtSignal()          # starting panelling dialog

    sig_mode_optimize           = pyqtSignal(bool)      # enter / leave mode optimize
    sig_xo2_about_to_run        = pyqtSignal()          # short before optimization starts
    sig_xo2_new_state           = pyqtSignal()          # Xoptfoil2 new info/state
    sig_xo2_input_changed       = pyqtSignal()          # data of Xoptfoil2 input changed
    sig_xo2_opPoint_def_selected= pyqtSignal()          # new opPoint definition selected somewhere 

    sig_closing                 = pyqtSignal(str)       # the app is closing with an airfoils pathFilename


    def __init__(self, initial_file, parent=None):
        super().__init__(parent)


        # --- init Settings, check for newer app version ---------------

        Settings.set_file (APP_NAME, file_extension= '.settings')

        update = Update_Checker (APP_NAME, PACKAGE_NAME,  __version__)   
        if update.is_newer_version_available():
            QTimer.singleShot (1000, lambda: update.show_user_info (self))        


        # --- init Airfoil Model ---------------

        initial_file = self._check_or_get_initial_file(initial_file)

        # either airfoil or Xoptfoil2 input file

        app_model = App_Model (workingDir_default=Settings.user_data_dir (APP_NAME))

        if Input_File.is_xo2_input (initial_file):
            #todo: optimize mode from xo2 input file
            # # case = create_case_from_path (self, initial_file, message_delayed=True)
            # if case: 
            #     app_model.set_case (case, silent=True)    
            # else: 
            #     app_model.set_airfoil (Example())                           # just show example airfoil 
            pass                            
        else:

            airfoil = create_airfoil_from_path(self, initial_file, example_if_none=True, message_delayed=True)
            app_model.set_airfoil (airfoil)

        # load settings like polar definitions either from airfoil or app settings

        app_model.load_settings ()
        app_model.sig_new_airfoil.connect (self._set_win_title)           # update title on new airfoil

        self._app_model     = app_model                                     # keep for close 


        # --- init UI ---------------
        
        logger.info (f"Initialize UI")

        self._set_win_title ()
        self._set_win_style (parent=parent)
        self._set_win_geometry ()

        # setup App modes and Mode Manager

        modes_manager = Modes_Manager ()
        modes_manager.add_mode (Mode_View       (app_model))
        modes_manager.add_mode (Mode_Modify     (app_model))
        # modes_manager.add_mode (Mode_Optimize   (app_model))
        modes_manager.add_mode (Mode_As_Bezier  (app_model))

        self._modes_manager = modes_manager

        # main widgets and layout of app

        diagram     = Diagram_Airfoil_Polar (self, app_model)               # big diagram widget
        modes_panel = modes_manager.modes_panel                             # stacked widget with mode specific panels

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

        self._diagram       = diagram                                       # keep for closedown

        # --- final set of UI depending on mode View or Optimize ---------------

        modes_manager.sig_close_requested.connect (self.close)              # app close requested from mode view
        modes_manager.set_mode (Mode_Id.VIEW)                               # start in view mode



        # if self.mode_optimize:
        #     self.sig_mode_optimize.emit(True)                             # signal enter / leave mode optimize for diagram

        logger.info (f"Ready for action ...")


    # ----------- end __init__ -------------------------------------------

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


    @property
    def mode_optimize (self) -> bool: 
        """ True if self is optimize mode"""
        return self._mode_optimize


    def set_mode_optimize (self, aBool : bool):
        """ switch optimize / view mode """

        if self._mode_optimize != aBool: 
            self._mode_optimize = aBool   



    def mode_optimize_finished (self):
        """ 
        optimize airfoil finished - switch back to view mode 
        """

        if not self.mode_optimize: return 

        # close open opPoint_def dialog 
        if self._xo2_opPoint_def_dialog:
             self._xo2_opPoint_def_dialog.close()

        # be sure input file data is written to file 
        self._save_xo2_nml (ask=True)

        # set next airfoil to show when finsihing optimize mode
        if  self.case.airfoil_final:
            next_airfoil = self.case.airfoil_final
        elif self.case.airfoil_seed:
            next_airfoil = self.case.airfoil_seed
        else:
            next_airfoil = Example()                            # should not happen
        next_airfoil.set_usedAs (usedAs.NORMAL)                 # normal AE color 
        

        self.set_airfoil (next_airfoil, silent=True)            # set next airfoil to show      

        self.refresh()  
        self.sig_mode_optimize.emit(False)                      # signal leave mode optimize for diagram


    def optimize_change_case (self, input_fileName : str, workingDir):
        """ change current optimization case to new input file """

        # check if changes were made in current case 
        self._save_xo2_nml (ask=True)

        # close open opPoint_def dialog 
        if self._xo2_opPoint_def_dialog:
             self._xo2_opPoint_def_dialog.close()

        self.optimize_airfoil (input_fileName=input_fileName, workingDir=workingDir)


    def case_optimize_new_version (self): 
        """ create new version of an existing optimization case self.input_file"""

        cur_case : Case_Optimize = self.case 
        cur_fileName = cur_case.input_file.fileName
        new_fileName = Input_File.new_fileName_version (cur_fileName, self.workingDir)

        if new_fileName:

            copyfile (os.path.join (self.workingDir,cur_fileName), os.path.join (self.workingDir,new_fileName))
            self.optimize_change_case (new_fileName, self.workingDir)

            self._toast_message (f"New version {new_fileName} created", toast_style=style.GOOD) 
        else: 
            MessageBox.error   (self,'Create new version', f"New Version of {cur_fileName} could not be created.",
                                min_width=350)


    def refresh(self):
        """ refreshes all child panels of edit_panel """

        logger.debug (f"{self} refresh main panels")

        if self._panel_view:            self.panel_view.refresh()               # refresh panels - if UI is visible   
        if self._panel_view_small:      self.panel_view_small.refresh()               
        if self._panel_modify:          self.panel_modify.refresh()
        if self._panel_modify_small:    self.panel_modify_small.refresh()
        if self._panel_xo2:             self.panel_xo2.refresh()
        if self._panel_xo2_small:       self.panel_xo2_small.refresh()






    # --- airfoil functions -----------------------------------------------



    def optimize_airfoil (self, input_fileName : str =None, workingDir : str = None ):
        """ 
        optimize current airfoil with Xoptfoil2 - switch to optimize mode - create Case
            There must be an existing Xoptfoil2 input file for the airfoil
        """
        
        if self.mode_optimize: 
            is_change_case = True                                           # change between cases
        else: 
            is_change_case = False                                          # enter optimization

        if input_fileName is None: 
            input_fileName = Input_File.fileName_of (self.airfoil)
        if workingDir is None: 
            workingDir = self.workingDir

        if input_fileName:

            case = Case_Optimize (input_fileName, workingDir=workingDir)

            self.set_case_optimize (case, silent=True)    
        
            self.set_mode_optimize (True)                                   # switch UI 
            self.refresh_polar_sets (silent=True)                           # replace polar definitions with the ones from Xo2 input file

            self.refresh()  



    def optimize_select (self):
        """ 
        open selection dialog to choose what to optimize
        """
        
        if not Xoptfoil2.ready : return 

        diag = Xo2_Select_Dialog (self, None, self.airfoil, parentPos=(0.2,0.5), dialogPos=(0,1))
        rc = diag.exec()

        if rc == QDialog.DialogCode.Accepted:

            if diag.input_fileName:
                self.optimize_airfoil (input_fileName=diag.input_fileName, workingDir=diag.workingDir)
            else: 
                self.optimize_new ()


    def optimize_new (self): 
        """ 
        open new optimization case dialog based on current airfoil"""
        
        if not Xoptfoil2.ready : return 

        seed_airfoil = self.airfoil_seed if self.mode_optimize else self.airfoil
        workingDir   = seed_airfoil.pathName_abs

        diag = Xo2_New_Dialog (self, workingDir, seed_airfoil, parentPos=(0.2,0.5), dialogPos=(0,0.5))
        
        self._watchdog.sig_new_polars.connect  (diag.refresh)           # we'll need polars

        rc = diag.exec()

        self._watchdog.sig_new_polars.disconnect  (diag.refresh)

        if rc == QDialog.DialogCode.Accepted:
            self.optimize_airfoil (input_fileName=diag.input_fileName, workingDir=diag.workingDir)



  

    def edit_opPoint_def (self, parent:QWidget, parentPos:Tuple, dialogPos:Tuple):
        """ open dialog to edit current xo2 opPoint def - relative position with parent is provided"""

        if self._xo2_opPoint_def_dialog is None:

            diag = Xo2_OpPoint_Def_Dialog (parent, lambda: self.case, parentPos=parentPos, dialogPos=dialogPos) 

            diag.sig_opPoint_def_changed.connect  (self._on_xo2_input_changed)
            diag.sig_finished.connect             (self.edit_opPoint_def_finished)

            self._xo2_opPoint_def_dialog = diag             # singleton 

        else: 
            self._xo2_opPoint_def_dialog.activateWindow ()

        self._xo2_opPoint_def_dialog.show () 


    def edit_opPoint_def_finished (self, diag : Xo2_OpPoint_Def_Dialog):
        """ slot - dialog to edit current opPoint def finished"""

        diag.sig_opPoint_def_changed.disconnect  (self._on_xo2_input_changed)
        diag.sig_finished.disconnect             (self.edit_opPoint_def_finished)


        self._xo2_opPoint_def_dialog = None     


    def optimize_open_run (self):
        """ open optimize dialog"""

        if self._xo2_run_dialog: 
            self._xo2_run_dialog.activateWindow()
            return                                 # already opened?

        # open dialog 

        diag = Xo2_Run_Dialog (self.panel_xo2, self.case, parentPos=(0.02,0.8), dialogPos=(0,1))

        self._xo2_run_dialog = diag

        self.sig_xo2_about_to_run.connect (diag.on_about_to_run)

        # connect dialog to self and self to diag

        diag.sig_run.connect        (self.optimize_run)
        diag.sig_closed.connect     (self.optimize_closed_run)

        # connect watchdog of xo2 to dialog 

        self._watchdog.set_case_optimize (lambda: self.case)

        self._watchdog.sig_xo2_new_state.connect        (self.panel_xo2.refresh)
        self._watchdog.sig_xo2_new_state.connect        (diag.on_results) 
        self._watchdog.sig_xo2_new_step.connect         (diag.on_new_step)
        self._watchdog.sig_xo2_still_running.connect    (diag.refresh)

        # run immediately if ready and not finished (a re-run) 
        
        case: Case_Optimize = self.case
        # if  (case.xo2.isReady and not case.isFinished):
        if  case.xo2.isReady:
            self.optimize_run()                             # run xo2 

        # open dialog 

        diag.show()


    def optimize_closed_run (self):
        """ slot for Xo2_Run_Dialog finished"""

        diag = self._xo2_run_dialog

        self._watchdog.sig_xo2_new_state.disconnect     (self.panel_xo2.refresh)

        self._watchdog.sig_xo2_new_state.disconnect     (diag.on_results)
        self._watchdog.sig_xo2_new_step.disconnect      (diag.on_new_step)
        self._watchdog.sig_xo2_still_running.disconnect (diag.refresh)
        self._watchdog.set_case_optimize (None)

        self._xo2_run_dialog.sig_run.disconnect         (self.optimize_run)
        self._xo2_run_dialog.sig_closed.disconnect      (self.optimize_closed_run)
        self._xo2_run_dialog = None

        # show again lower panel 
         
        self.refresh()                  # show final airfoil 


    def optimize_run (self): 
        """ run optimizer"""

        case : Case_Optimize = self.case

        # reset current xo2 controller if there was an error 
        if case.xo2.isRun_failed:
            case.xo2_reset()

        if case.xo2.isReady:

            # be sure input file data is written to file 

            self._save_xo2_nml (ask=False, toast=False)

            # clear previous results - prepare UI 

            case.clear_results ()
            self._watchdog.reset_watch_optimize ()
            self.set_airfoil (None, silent=True)
            self.sig_xo2_about_to_run.emit()
            
            # close other dialogs

            if self._xo2_opPoint_def_dialog:
                self._xo2_opPoint_def_dialog.close()

            # let's go

            case.run()


    # --- private ---------------------------------------------------------



    def _on_xo2_input_changed (self, silent=False):
        """ slot handle change of xo2 input data"""

        logger.debug (f"{self} on_xo2_input_changed")

        # write back opPoint definitions and ref airfoils to namelist for change detection (save)
        case : Case_Optimize = self.case
        case.input_file.opPoint_defs.set_nml ()
        case.input_file.airfoils_ref_set_nml ()

        # polar definitions could have changed - update polarSets of airfoils 
        self.refresh_polar_sets (silent=True)

        if not silent: 
            # also refresh opPoint definition dialog if open 
            if self._xo2_opPoint_def_dialog:
                self._xo2_opPoint_def_dialog.refresh()

            self.refresh()
            self.sig_xo2_input_changed.emit()                                   # inform diagram 


    def _on_xo2_opPoint_def_changed (self):
        """ slot opPoint definition changed in diagram"""

        if self._xo2_opPoint_def_dialog:
            self._xo2_opPoint_def_dialog.refresh_current ()
        self.refresh()            


    def _on_xo2_opPoint_def_selected (self):
        """ slot opPoint definition selected either in panel or diagram"""

        if self._xo2_opPoint_def_dialog:
            self._xo2_opPoint_def_dialog.refresh_current ()
        self.sig_xo2_opPoint_def_selected.emit()
        self.refresh()            


    def _on_new_xo2_state (self):
        """ slot to handle new state during Xoptfoil2 run"""

        # during run airfoil designs had no polar set - now assign to show polar 

        case : Case_Optimize = self.case
        if case.isFinished and case.airfoil_designs:
            self.set_airfoil (self.airfoil, silent=True)                      # will assign polarSet

        # now refresh panels and diagrams

        self.refresh ()

         # inform diagram a little delayed so refresh can take place 
        QTimer.singleShot (100, self.sig_xo2_new_state.emit)                


    def _on_new_xo2_design (self, iDesign):
        """ slot to handle new design during Xoptfoil2 run"""

        if not self.case.airfoil_designs: return 

        logger.debug (f"{str(self)} on Xoptfoil2 new design {iDesign}")

        airfoil_design = self.case.airfoil_designs [-1]
        
        self.set_airfoil (airfoil_design, silent=True)                      # new current airfoil

        # remove polar set of design airfoil (during optimization) - so no polar creation 
        airfoil_design.set_polarSet (Polar_Set (airfoil_design, polar_def=[]))

        self.sig_new_airfoil.emit()                                          # refresh diagram 


    def _set_win_title (self):
        """ set window title with airfoil or casename """

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


    def _toast_message (self, msg, toast_style = style.HINT):
        """ show toast message """
        
        Toaster.showMessage (self, msg, corner=Qt.Corner.BottomLeftCorner, margin=QMargins(10, 10, 10, 10),
                             toast_style=toast_style)


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




    def _save_xo2_nml (self, ask = False, toast=True): 
        """ save xo2 input options - optionally ask user"""

        case: Case_Optimize = self.case
        if not isinstance (case, Case_Optimize): return 

        # check if changes were made in current case 

        if case.input_file.isChanged:
            if ask: 
                text = f"Save changes made for {case.name}?"
                button = MessageBox.save (self, "Save Case", text,
                                          buttons = QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard)
                if button == QMessageBox.StandardButton.Discard:
                    return 
                
            case.input_file.save_nml()

            if toast:
                self._toast_message (f"Parameters saved to Input file", toast_style=style.GOOD)


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