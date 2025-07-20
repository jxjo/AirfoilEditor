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
                |-- Airfoil_Diagram_Item        - Pygtgraph Plot item for airfoil contour
                |-- Curvature_Diagram_Item      - Pygtgraph Plot item for airfoil curvature 
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

# add directory of self to sys.path, so import is relative to self
modules_path = os.path.dirname(__file__)
if not modules_path in sys.path:
    sys.path.append(modules_path)
    # print ("\n".join(sys.path))

from model.airfoil          import Airfoil, usedAs
from model.airfoil_geometry import Panelling_Spline, Panelling_Bezier, Line
from model.polar_set        import Polar_Definition, Polar_Set, Polar_Task
from model.xo2_driver       import Worker, Xoptfoil2
from model.xo2_input        import Input_File
from model.case             import Case_Direct_Design, Case_Optimize, Case_Abstract

from base.common_utils      import * 
from base.panels            import Container_Panel, Win_Util, Toaster
from base.widgets           import *

from airfoil_widgets        import * 
from airfoil_dialogs        import (Airfoil_Save_Dialog, Blend_Airfoil_Dialog, Repanel_Airfoil_Dialog,
                                    Flap_Airfoil_Dialog)
from airfoil_diagrams       import Diagram_Airfoil_Polar            
from xo2_dialogs            import (Xo2_Run_Dialog, Xo2_Select_Dialog, Xo2_OpPoint_Def_Dialog, Xo2_New_Dialog)

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)



#-------------------------------------------------------------------------------
# The App   
#-------------------------------------------------------------------------------


APP_NAME         = "AirfoilEditor"
__version__      = "4.0.0b1"


class Main (QMainWindow):
    '''
        App - Main Window 
    '''

    WORKER_MIN_VERSION         = '1.0.6'
    XOPTFOIL2_MIN_VERSION      = '1.0.6'

    # Qt Signals 

    sig_new_airfoil             = pyqtSignal()          # new airfoil selected 
    sig_new_design              = pyqtSignal()          # new airfoil design created 

    sig_airfoil_changed         = pyqtSignal()          # airfoil data changed 
    sig_airfoil_2_changed       = pyqtSignal()          # 2nd airfoil data changed 
    sig_airfoils_ref_changed    = pyqtSignal()          # list of reference airfoils changed

    sig_bezier_changed          = pyqtSignal(Line.Type) # new bezier during match bezier 
    sig_panelling_changed       = pyqtSignal()          # new panelling
    sig_blend_changed           = pyqtSignal()          # new (intermediate) blend 
    sig_polar_set_changed       = pyqtSignal()          # new polar sets attached to airfoil
    sig_enter_panelling         = pyqtSignal()          # starting panelling dialog
    sig_enter_blend             = pyqtSignal()          # starting blend airfoil with
    sig_enter_flapping          = pyqtSignal(bool)      # start /end flapping dialog 
    sig_flap_changed            = pyqtSignal()          # flap setting (Flapper) changed 

    sig_mode_optimize           = pyqtSignal(bool)      # enter / leave mode optimize
    sig_new_case_optimize       = pyqtSignal()          # new case optimize selected
    sig_xo2_about_to_run        = pyqtSignal()          # short befure optimization starts
    sig_xo2_new_state           = pyqtSignal()          # Xoptfoil2 new info/state
    sig_xo2_input_changed       = pyqtSignal()          # data of Xoptfoil2 input changed
    sig_xo2_opPoint_def_selected= pyqtSignal()          # new opPoint definition selected somewhere 

    sig_closing                 = pyqtSignal(str)       # the app is closing with an airfoils pathFilename


    def __init__(self, initial_file, parent=None):
        super().__init__(parent)

        self._airfoil           = None                  # current airfoil 
        self._airfoil_org       = None                  # airfoil saved in mode_modify 
        self._airfoils_ref      = []                    # reference airfoils 
        self._airfoil_2         = None                  # 2nd airfoil for blend    

        self._polar_definitions = None                  # current polar definitions  
        self._watchdog          = None                  # polling thread for new olars

        self._mode_modify       = False                 # modifiy/view mode of app 
        self._mode_optimize     = False                 # optimize mode of app 
        self._case              = None                  # design Case holding all designs 

        self._panel_view        = None                  # main UI panels
        self._panel_modify      = None
        self._panel_optimize    = None
        self._diagram           = None

        self._xo2_opPoint_def_dialog = None             # singleton for this dialog 
        self._xo2_run_dialog    = None                  # singleton for this dialog 


        # if called from other applcation (PlanformCreator) make it modal to this 

        if parent is not None:
            self.setWindowModality(Qt.WindowModality.ApplicationModal)  

        # get icon either in modules or in icons 
        
        self.setWindowIcon (Icon ('AE_ico.ico'))

        # Qt color scheme, initial window size from settings

        Settings.set_path (APP_NAME, file_extension= '.settings')

        scheme_name = Settings().get('color_scheme', Qt.ColorScheme.Unknown.name)           # either unknown (from System), Dark, Light
        QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme[scheme_name])            # set scheme of QT
        Widget.light_mode = not (scheme_name == Qt.ColorScheme.Dark.name)                   # set mode for Widgets 

        geometry = Settings().get('window_geometry', [])
        maximize = Settings().get('window_maximize', False)
        Win_Util.set_initialWindowSize (self, size_frac= (0.85, 0.80), pos_frac=(0.1, 0.1),
                                        geometry=geometry, maximize=maximize)
        
        # load other settings

        self._load_settings ()

        # if no initial airfoil file, try to get last openend airfoil file 

        if not initial_file: 
            initial_file = Settings().get('last_opened', default=None) 

        # either airfoil or Xoptfoil2 input file 
        if Input_File.is_xo2_input (initial_file, workingDir=os.getcwd()):

            self.set_airfoil (Example(workingDir="example"), silent=True)  # dummy when returning from optimize
            self.optimize_airfoil (initial_file)
        else:

            airfoil = create_airfoil_from_path(self, initial_file, example_if_none=True, message_delayed=True)
            self.set_airfoil (airfoil, silent=True)


        # Worker for polar generation and Xoptfoil2 for optimization ready? 

        Worker().isReady (os.path.dirname(os.path.abspath(__file__)), min_version=self.WORKER_MIN_VERSION)
        if Worker.ready and self.airfoil:
            Worker().clean_workingDir (self.airfoil.pathName)

        Xoptfoil2().isReady (os.path.dirname(os.path.abspath(__file__)), min_version=self.XOPTFOIL2_MIN_VERSION)

        # init main layout of app

        l = QGridLayout () 

        l.addWidget (self.diagram,        0,0)
        l.addWidget (self.panel_view,     2,0)
        l.addWidget (self.panel_modify,   2,0)
        l.addWidget (self.panel_optimize, 2,0)

        l.setRowStretch (0,1)
        l.setRowMinimumHeight (1,5)
        l.setSpacing (0)
        l.setContentsMargins (QMargins(5, 5, 5, 5))

        main = QWidget()
        main.setLayout (l) 
        self.setCentralWidget (main)

        # ---- signals and slots --------------------------------------------------------------

        # install watchdog for poars generated by Worker 

        if Worker.ready:
             self._watchdog = Watchdog (self) 
             self._watchdog.sig_new_polars.connect       (self.diagram.on_new_polars)
             self._watchdog.sig_xo2_new_state.connect    (self._on_new_xo2_state)            
             self._watchdog.sig_xo2_new_design.connect   (self._on_new_xo2_design)                   # new current, update diagram  
             self._watchdog.start()

        # connect diagram signals to slots of self

        self.diagram.sig_airfoil_changed.connect           (self._on_airfoil_changed)
        self.diagram.sig_polar_def_changed.connect         (self.refresh_polar_sets)
        self.diagram.sig_airfoil_ref_changed.connect       (self.set_airfoil_ref)
        self.diagram.sig_airfoil_design_selected.connect   (self._on_airfoil_design_selected)
        self.diagram.sig_opPoint_def_selected.connect      (self._on_xo2_opPoint_def_selected)     # inform dialog 
        self.diagram.sig_opPoint_def_changed.connect       (self._on_xo2_opPoint_def_changed)      # inform dialog 
        self.diagram.sig_opPoint_def_changed.connect       (self._on_xo2_input_changed)            # save to nml
        self.diagram.sig_opPoint_def_dblClick.connect      (self.edit_opPoint_def)

        # connect self signals to slots of diagram

        self.sig_new_airfoil.connect            (self.diagram.on_airfoil_changed)
        self.sig_new_design.connect             (self.diagram.on_new_design)
        self.sig_airfoil_changed.connect        (self.diagram.on_airfoil_changed)
        self.sig_airfoil_2_changed.connect      (self.diagram.on_airfoil_2_changed)
        self.sig_bezier_changed.connect         (self.diagram.on_bezier_changed)
        self.sig_panelling_changed.connect      (self.diagram.on_airfoil_changed)
        self.sig_blend_changed.connect          (self.diagram.on_blend_changed)
        self.sig_polar_set_changed.connect      (self.diagram.on_polar_set_changed)
        self.sig_airfoils_ref_changed.connect   (self.diagram.on_airfoils_ref_changed)

        self.sig_mode_optimize.connect          (self.diagram.on_mode_optimize)
        self.sig_xo2_about_to_run.connect       (self.diagram.on_xo2_about_to_run)
        self.sig_xo2_new_state.connect          (self.diagram.on_xo2_new_state)
        self.sig_xo2_input_changed.connect      (self.diagram.on_xo2_new_state)
        self.sig_new_case_optimize.connect      (self.diagram.on_new_case_optimize)
        self.sig_xo2_opPoint_def_selected.connect (self.diagram.on_xo2_opPoint_def_selected)

        self.sig_enter_blend.connect            (self.diagram.on_blend_airfoil)
        self.sig_enter_panelling.connect        (self.diagram.on_enter_panelling)
        self.sig_enter_flapping.connect         (self.diagram.on_enter_flapping)
        self.sig_flap_changed.connect           (self.diagram.on_flap_changed)


    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"


    @property
    def panel_view (self) -> Container_Panel:
        """ lower UI main panel - view mode """
        if self._panel_view is None: 

            # lazy import to avoid circular references 
            from airfoil_panels      import (Panel_File_View, Panel_Geometry, Panel_LE_TE, Panel_Panels, 
                                             Panel_Bezier, Panel_Flap) 

            l = QHBoxLayout()
            l.addWidget (Panel_File_View       (self, lambda: self.airfoil, width=250, height=190))
            l.addWidget (Panel_Geometry        (self, lambda: self.airfoil))
            l.addWidget (Panel_Panels          (self, lambda: self.airfoil))
            l.addWidget (Panel_LE_TE           (self, lambda: self.airfoil))
            l.addWidget (Panel_Bezier          (self, lambda: self.airfoil))
            l.addWidget (Panel_Flap            (self, lambda: self.airfoil))
            l.addStretch (1)

            self._panel_view = Container_Panel (layout = l, hide=lambda: not self.mode_view)

        return self._panel_view 


    @property
    def panel_modify (self) -> Container_Panel:
        """ lower UI main panel - modifiy mode """
        if self._panel_modify is None: 

            # lazy import to avoid circular references 
            from airfoil_panels      import (Panel_File_Modify, Panel_Geometry, Panel_LE_TE, Panel_Panels, 
                                             Panel_Flap, Panel_Bezier, Panel_Bezier_Match) 

            l = QHBoxLayout()
            l.addWidget (Panel_File_Modify     (self, lambda: self.airfoil, width=250, height=190, lazy_layout=True))
            l.addWidget (Panel_Geometry        (self, lambda: self.airfoil, lazy_layout=True))
            l.addWidget (Panel_Panels          (self, lambda: self.airfoil, lazy_layout=True))
            l.addWidget (Panel_LE_TE           (self, lambda: self.airfoil, lazy_layout=True))
            l.addWidget (Panel_Flap            (self, lambda: self.airfoil, lazy_layout=True))
            l.addWidget (Panel_Bezier          (self, lambda: self.airfoil, lazy_layout=True))
            l.addWidget (Panel_Bezier_Match    (self, lambda: self.airfoil, lazy_layout=True))
            l.addStretch (1)

            self._panel_modify    = Container_Panel (layout = l, hide=lambda: not self.mode_modify)

        return self._panel_modify 


    @property
    def panel_optimize (self) -> Container_Panel:
        """ lower UI main panel - optimize mode """
        if self._panel_optimize is None: 

            # lazy import to avoid circular references 
            from xo2_panels             import (Panel_File_Optimize, Panel_Xo2_Advanced, Panel_Xo2_Case, Panel_Xo2_Curvature,
                                                Panel_Xo2_Geometry_Targets, Panel_Xo2_Operating_Conditions, Panel_Xo2_Operating_Points)

            l = QHBoxLayout()        
            l.addWidget (Panel_File_Optimize               (self, lambda: self.case, width=250, height=190, lazy_layout=True))
            l.addWidget (Panel_Xo2_Case                    (self, lambda: self.case, lazy_layout=True))
            l.addWidget (Panel_Xo2_Operating_Conditions    (self, lambda: self.case, lazy_layout=True))
            l.addWidget (Panel_Xo2_Operating_Points        (self, lambda: self.case, lazy_layout=True))
            l.addWidget (Panel_Xo2_Geometry_Targets        (self, lambda: self.case, lazy_layout=True))
            l.addWidget (Panel_Xo2_Curvature               (self, lambda: self.case, lazy_layout=True))
            l.addWidget (Panel_Xo2_Advanced                (self, lambda: self.case, lazy_layout=True))
            l.addStretch (1)

            self._panel_optimize = Container_Panel (layout = l, hide=lambda: not self.mode_optimize or self._xo2_run_dialog)

        return self._panel_optimize 


    @property
    def diagram (self) -> Diagram_Airfoil_Polar:
        """ the upper diagram area"""
        if self._diagram is None: 

            self._diagram       = Diagram_Airfoil_Polar (self, lambda: self.airfoils, 
                                                        polar_defs_fn = lambda: self.polar_definitions,
                                                        case_fn = lambda: self.case, 
                                                        diagram_settings= Settings().get('diagram_settings', []))
        return self._diagram


    @property
    def case (self) -> Case_Abstract:
        """ design or optimize case holding all design airfoils"""
        return self._case 


    def set_case (self, case : Case_Abstract | None):
        """ set new design or optimize case"""

        if isinstance (case, Case_Direct_Design) or isinstance (case, Case_Optimize):
            self._case = case
        else: 
            self._case = None 


    def set_case_optimize (self, case : Case_Abstract | None, silent=False):
        """ set new optimize case"""

        logger.debug (f"Set new case optimize: {case}")

        self.set_case (case)

        self.setWindowTitle (APP_NAME + "  v" + str(__version__) + "  [" + self._case.name + "]")

        if not silent: 
                self.refresh ()
                self.sig_new_case_optimize.emit()


    @property
    def airfoil (self) -> Airfoil:
        """ current airfoil """

        return self._airfoil 


    @property
    def airfoils (self) -> list [Airfoil]:
        """ list of airfoils (current, ref1 and ref2) """
        airfoils = []

        if self.airfoil:            airfoils.append (self.airfoil)
        if self.airfoil_seed:       airfoils.append (self.airfoil_seed)
        if self.airfoil_final:      airfoils.append (self.airfoil_final)
        if self.airfoil_2:          airfoils.append (self.airfoil_2)
        if self.airfoil_org:        airfoils.append (self.airfoil_org)
        if self.airfoils_ref:       airfoils.extend (self.airfoils_ref)

        # remove duplicates 

        path_dict = {}
        airfoil : Airfoil 
        for airfoil in airfoils [:]:
            if path_dict.get (airfoil.pathFileName_abs, False):
                airfoils.remove (airfoil)
            else: 
                path_dict [airfoil.pathFileName_abs] = True

        return airfoils


    def set_airfoil (self, aNew : Airfoil , silent=False):
        """ set new current aurfoil """

        # set airfoil and polarSets

        self._airfoil = aNew

        if aNew is not None: 
            self._airfoil.set_polarSet (Polar_Set (aNew, polar_def=self.polar_definitions, only_active=True))

            logger.debug (f"Set new airfoil {aNew.fileName} including polarSet")

        # set window title

        if self.mode_optimize:
            ext = f"[Case {self.case.name}]"
        else: 
            ext = f"[{self.airfoil.fileName if self.airfoil else ''}]"
        self.setWindowTitle (APP_NAME + "  v" + str(__version__) + "  " + ext)

        if not silent: 
            self.refresh()
            if aNew is not None and self._airfoil.usedAsDesign:
                self.sig_new_design.emit ()                    # new DESIGN - inform diagram
            else:
                self.sig_new_airfoil.emit ()


    @property
    def workingDir (self) -> str: 
        """ directory we are currently in (equals dir of airfoil)"""
        if self.case:                                         # case working dir has prio 
            return self.case.workingDir
        elif self._airfoil_org:                                 # modify mode use airfoil org   
            return self._airfoil_org.pathName
        elif self.airfoil:                                     
            return self.airfoil.pathName
        else:
            ""


    @property
    def polar_definitions (self) -> list [Polar_Definition]:
        """ list of current polar definitions """

        if self.mode_optimize:
            # check if polar defs changed in input file - if not keep current to retain active flag
            case_polar_defs = self._case.input_file.opPoint_defs.polar_defs()
            if len(self._polar_definitions) == len(case_polar_defs):
                for i, polar_def in enumerate (self._polar_definitions):
                    if not polar_def.is_equal_to (case_polar_defs[i], ignore_active=True):
                        self._polar_definitions = case_polar_defs
                        break
            else: 
                self._polar_definitions = case_polar_defs
        else:
            if not self._polar_definitions: 
                self._polar_definitions = [Polar_Definition()]

        return self._polar_definitions

      
    @property
    def airfoils_ref (self) -> list[Airfoil]:
        """ reference airfoils"""

        if self.mode_optimize:
            return self.case.airfoils_ref                           # take individual reference airfoils of case
        else:
            return self._airfoils_ref                               # normal handling
 
    
    def set_airfoil_ref (self, cur_airfoil_ref: Airfoil | None,
                               new_airfoil_ref: Airfoil | None):
        """ adds, replace, delete airfoil to the list of reference airfoils"""

        # check if already in list 
        if new_airfoil_ref in self.airfoils_ref: return 

        if new_airfoil_ref:
            new_airfoil_ref.set_polarSet (Polar_Set (new_airfoil_ref, polar_def=self.polar_definitions, only_active=True))
            new_airfoil_ref.set_usedAs (usedAs.REF)   

        if cur_airfoil_ref:
            # replace or delete existing 
            i = self.airfoils_ref.index (cur_airfoil_ref)
            if new_airfoil_ref:
               self.airfoils_ref[i] = new_airfoil_ref
            else: 
                del self.airfoils_ref [i]
        else:
            # add new  
            self.airfoils_ref.append(new_airfoil_ref)

        self.sig_airfoils_ref_changed.emit()

        if self.mode_optimize:                                      # reference airfoils are in input file
            self._on_xo2_input_changed ()


    @property
    def airfoil_2 (self) -> Airfoil:
        """ 2nd airfoil for blend etc"""
        return self._airfoil_2

    def set_airfoil_2 (self, airfoil: Airfoil | None = None) -> Airfoil:
        if self._airfoil_2:                                         # reset eventual current
            self._airfoil_2.set_usedAs (usedAs.NORMAL)
        if airfoil: 
            airfoil.set_usedAs (usedAs.SECOND)
        self._airfoil_2 = airfoil
        self.sig_airfoil_2_changed.emit()             


    @property
    def airfoil_seed (self) -> Airfoil | None:
        """ seed airfoil of optimization"""
        if self.mode_optimize and self.case:
            seed =  self.case.airfoil_seed
            if not seed.polarSet:
               seed.set_polarSet (Polar_Set (seed, polar_def=self.polar_definitions, only_active=True))
            return seed
        

    @property
    def airfoil_final (self) -> Airfoil | None:
        """ final airfoil of optimization"""
        if self.mode_optimize and self.case:
            final =  self.case.airfoil_final
            if final and not final.polarSet:
               final.set_polarSet (Polar_Set (final, polar_def=self.polar_definitions, only_active=True))
            return final


    @property
    def airfoil_org (self) -> Airfoil:
        """ the original airfoil during modify mode"""
        return self._airfoil_org if self.mode_modify else None


    @property
    def mode_view (self) -> bool: 
        """ True if self is in view mode"""
        return not (self.mode_modify or self.mode_bezier or self.mode_optimize)


    @property
    def mode_modify (self) -> bool: 
        """ True if self is modifiy mode"""
        return self._mode_modify


    def set_mode_modify (self, aBool : bool):
        """ switch modifiy / view mode """

        if self._mode_modify != aBool: 
            self._mode_modify = aBool
            
            if self._mode_modify:
                # save possible example to file to ease consistent further handling in widgets
                if self._airfoil.isExample: self._airfoil.save()
                self._airfoil_org = self._airfoil       # enter mode_modify - save original 
            else: 
                self._airfoil_org = None                # leave mode_modify - remove original 
        

    @property
    def mode_bezier (self) -> bool:
        """ True if self is in mode_modify and geo is Bezier """
        return self.mode_modify and self.airfoil.isBezierBased


    @property
    def mode_optimize (self) -> bool: 
        """ True if self is optimize mode"""
        return self._mode_optimize


    def set_mode_optimize (self, aBool : bool):
        """ switch optimize / view mode """

        if self._mode_optimize != aBool: 
            self._mode_optimize = aBool   

            if aBool: 
                self._airfoil_org = self._airfoil           # save current airfoil 
            else: 
                self._airfoil_org = None    


    def mode_modify_finished (self, ok=False):
        """ 
        modify airfoil finished - switch to view mode 
            - ok == False: modify mode was cancelled 
            - ok == True:  user wants to finish 
        """

        remove_designs  = None                              # let case.close decide to remove design dir 

        # sanity
        if not self.mode_modify: return 

        if ok:
            # create new, final airfoil based on actual design and path from airfoil org 
            case : Case_Direct_Design = self.case
            new_airfoil = case.get_final_from_design (self.airfoil_org, self.airfoil)

            # dialog to edit name, choose path, ..

            dlg = Airfoil_Save_Dialog (parent=self, getter=new_airfoil)
            ok_save = dlg.exec()

            if not ok_save: 
                return                                          # save was cancelled - return to modify mode 
            else: 
                remove_designs = dlg.remove_designs
                self._toast_message (f"New airfoil {new_airfoil.fileName} saved", toast_style=style.GOOD)

        # leave mode_modify  

        if not ok:
            new_airfoil = self._airfoil_org                     # restore original airfoil 

        # close case 

        self.case.close (remove_designs=remove_designs)       # shut down case
        self.set_case (None)                                

        self.set_mode_modify (False)  
        self.set_airfoil (new_airfoil, silent=False)



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

        next_airfoil = self.case.airfoil_final if  self.case.airfoil_final else self._airfoil_org
        next_airfoil.set_usedAs (usedAs.NORMAL)                 # normal AE color 
        
        self.set_case (None)  
        self.set_mode_optimize (False) 

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

        self.panel_view.refresh()
        self.panel_modify.refresh()
        self.panel_optimize.refresh()


    def refresh_polar_sets (self, silent=False):
        """ refresh polar sets of all airfoils"""

        changed = False 

        for airfoil in self.airfoils:

            new_polarSet = Polar_Set (airfoil, polar_def=self.polar_definitions, only_active=True)

            # check changes to avoid unnecessary refresh
            if not new_polarSet.is_equal_to (airfoil.polarSet):
                changed = True 
                airfoil.set_polarSet (new_polarSet)

        if not silent and changed: 
            self.refresh()
            self.sig_polar_set_changed.emit()




    # --- airfoil functions -----------------------------------------------


    def modify_airfoil (self):
        """ modify airfoil - switch to modify mode - create Case """
        if self.mode_modify: return 

        # info if airfoil is flapped 

        if self.airfoil.geo.isProbablyFlapped:

            text = "The airfoil is probably flapped and will be normalized.\n\n" + \
                   "Modifying the geometry can lead to strange results."
            button = MessageBox.confirm (self, "Modify Airfoil", text)
            if button == QMessageBox.StandardButton.Cancel:
                return

        # create new Design Case and get/create first design 

        self.set_case (Case_Direct_Design (self._airfoil))

        self.set_mode_modify (True)       
        self.set_airfoil (self.case.initial_airfoil_design(), silent=False)


    def optimize_airfoil (self, input_fileName : str =None, workingDir : str = None ):
        """ 
        optimize currrent airfoil with Xoptfoil2 - switch to optimize mode - create Case
            There must be an existing Xoptfoil2 inputfile for the airfoil
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
            self.set_airfoil (case.initial_airfoil_design(), silent=True)   # maybe there is already an existing design              
            self.refresh_polar_sets (silent=True)                           # replace polar definitions with the ones from Xo2 input file

            self.refresh()  

            if is_change_case:
                self.sig_new_case_optimize.emit()                           # signal change case                         
            else:
                self.sig_mode_optimize.emit(True)                           # signal enter / leave mode optimize for diagram


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



    def new_as_Bezier (self):
        """ create new Bezier airfoil based on current airfoil, create Case, switch to modify mode """

        # current airfoil should be normalized to achieve good results 

        if not self.airfoil.isNormalized:

            text = "The airfoil is not normalized.\n\n" + \
                   "Match Bezier will not lead to the best results."
            button = MessageBox.confirm (self, "Modify Airfoil", text)
            if button == QMessageBox.StandardButton.Cancel:
                return

        # create initial Bezier airfoil based on current

        airfoil_bez = Airfoil_Bezier.onAirfoil (self._airfoil)

        # create new Design Case and get/create first design 

        self.set_case (Case_Direct_Design (airfoil_bez))

        self.set_mode_modify (True)  
        self.set_airfoil (self.case.initial_airfoil_design() , silent=False)
  


    def do_blend_with (self): 
        """ blend with another airfoil - open blend airfoil dialog """ 

        self.sig_enter_blend.emit()

        dialog = Blend_Airfoil_Dialog (self, self.airfoil, self.airfoil_org, 
                                       parentPos=(0.25, 0.75), dialogPos=(0,1))  

        dialog.sig_blend_changed.connect (self.sig_blend_changed.emit)
        dialog.sig_airfoil_2_changed.connect (self.set_airfoil_2)

        dialog.exec()     

        if dialog.airfoil2 is not None: 
            # do final blend with high quality (splined) 
            self.airfoil.geo.blend (self.airfoil_org.geo, 
                                      dialog.airfoil2.geo, 
                                      dialog.blendBy) 
            self.set_airfoil_2 (None)
            self._on_airfoil_changed()


    def do_repanel (self): 
        """ repanel airfoil - open repanel dialog""" 

        self.sig_enter_panelling.emit()

        dialog = Repanel_Airfoil_Dialog (self, self.airfoil.geo,
                                         parentPos=(0.35, 0.75), dialogPos=(0,1))

        dialog.sig_new_panelling.connect (self.sig_panelling_changed.emit)
        dialog.exec()     

        if dialog.has_been_repaneled:
            # finalize modifications 
            self.airfoil.geo.repanel (just_finalize=True)                

            self._on_airfoil_changed()



    def do_flap (self): 
        """ set flaps - run set flap dialog""" 

        self.sig_enter_flapping.emit(True)

        dialog = Flap_Airfoil_Dialog (self, self.airfoil,
                                         parentPos=(0.55, 0.80), dialogPos=(0,1))

        dialog.sig_new_flap_settings.connect (self.sig_flap_changed.emit)
        dialog.exec()     

        if dialog.has_been_flapped:
            # finalize modifications 
            self.airfoil.do_flap ()              

            self._on_airfoil_changed()

        self.sig_enter_flapping.emit(False)


    def do_save_as (self): 
        """ save current airfoil as ..."""

        dlg = Airfoil_Save_Dialog (parent=self, getter=self.airfoil)
        ok_save = dlg.exec()

        if ok_save: 
            self.set_airfoil (self.airfoil)
            self._toast_message (f"New airfoil {self.airfoil.fileName} saved", toast_style=style.GOOD)


    def do_rename (self): 
        """ rename current airfoil as ..."""

        old_pathFileName = self.airfoil.pathFileName_abs

        dlg = Airfoil_Save_Dialog (parent=self, getter=self.airfoil, rename_mode=True, remove_designs=True)
        ok_save = dlg.exec()

        if ok_save: 

            # delete old one 
            if os.path.isfile (old_pathFileName):  
                os.remove (old_pathFileName)

            # a copy with new name was created 
            self.set_airfoil (self.airfoil)                                 # refresh with new 
            self._toast_message (f"Airfoil renamed to {self.airfoil.fileName}", toast_style=style.GOOD)


    def do_delete (self): 
        """ delete current airfoil ..."""

        if not os.path.isfile (self.airfoil.pathFileName_abs): return 

        text = f"Airfoil <b>{self.airfoil.fileName}</b> including temporary files will be deleted."
        button = MessageBox.warning (self, "Delete airfoil", text)

        if button == QMessageBox.StandardButton.Ok:
            
            next_airfoil = get_next_airfoil_in_dir(self.airfoil, example_if_none=True)

            self.do_delete_temp_files (silent=True)
            os.remove (self.airfoil.pathFileName_abs)                               # remove airfoil

            self._toast_message (f"Airfoil {self.airfoil.fileName} deleted", toast_style=style.GOOD)
            self.set_airfoil (next_airfoil)                                         # try to set on next airfoil

            if next_airfoil.isExample:
               button = MessageBox.info (self, "Delete airfoil", "This was the last airfoil in the directory.<br>" + \
                                               "Showing Example airfoil") 


    def do_delete_temp_files (self, silent=False): 
        """ delete all temp files and directories of current airfoil ..."""

        if not os.path.isfile (self.airfoil.pathFileName_abs): return 

        delete = True 

        if not silent: 
            text = f"All temporary files and directories of Airfoil <b>{self.airfoil.fileName}</b> will be deleted."
            button = MessageBox.warning (self, "Delete airfoil", text)
            if button != QMessageBox.StandardButton.Ok:
                delete = False
        
        if delete: 
            Case_Direct_Design.remove_design_dir (self.airfoil.pathFileName_abs)    # remove temp design files and dir 
            Worker.remove_polarDir (self.airfoil.pathFileName_abs)                  # remove polar dir 
            Xoptfoil2.remove_resultDir (self.airfoil.pathFileName_abs)              # remove Xoptfoil result dir 

            if not silent:
                self._toast_message (f"Temporary files of Airfoil {self.airfoil.fileName} deleted", toast_style=style.GOOD)


    def edit_opPoint_def (self, parent:QWidget, parentPos:Tuple, dialogPos:Tuple):
        """ open dialog to edit current xo2 opPoint def - relativ position with parent is provided"""

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
            return                                 # already openend?

        # open dialog 

        diag = Xo2_Run_Dialog (self.panel_optimize, self.case, parentPos=(0.02,0.8), dialogPos=(0,1))

        self._xo2_run_dialog = diag

        self.sig_xo2_about_to_run.connect (diag.on_about_to_run)

        # connect dialog to self and self to diag

        diag.sig_run.connect        (self.optimize_run)
        diag.sig_closed.connect     (self.optimize_closed_run)

        # connect watchdog of xo2 to dialog 

        self._watchdog.set_case_optimize (lambda: self.case)

        self._watchdog.sig_xo2_new_state.connect        (self.panel_optimize.refresh)
        self._watchdog.sig_xo2_new_state.connect        (diag.on_results)
        self._watchdog.sig_xo2_new_design.connect       (diag.on_results)
        self._watchdog.sig_xo2_new_step.connect         (diag.on_new_step)
        self._watchdog.sig_xo2_still_running.connect    (diag.refresh)

        # run immedately if ready and not finished (a re-run) 
        
        case: Case_Optimize = self.case
        # if  (case.xo2.isReady and not case.isFinished):
        if  case.xo2.isReady:
            self.optimize_run()                             # run xo2 

        # open dialog 

        diag.show()


    def optimize_closed_run (self):
        """ slot for Xo2_Run_Dialog finished"""

        diag = self._xo2_run_dialog

        self._watchdog.sig_xo2_new_state.disconnect     (self.panel_optimize.refresh)

        self._watchdog.sig_xo2_new_state.disconnect     (diag.on_results)
        self._watchdog.sig_xo2_new_design.disconnect    (diag.on_results)
        self._watchdog.sig_xo2_new_step.disconnect      (diag.on_new_step)
        self._watchdog.sig_xo2_still_running.disconnect (diag.refresh)
        self._watchdog.set_case_optimize (None)

        self._xo2_run_dialog.sig_run.disconnect         (self.optimize_run)
        self._xo2_run_dialog.sig_closed.disconnect      (self.optimize_closed_run)
        self._xo2_run_dialog = None

        # show again lower panel 
         
        self.panel_optimize.refresh()                   # show final airfoil 


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


    def _on_airfoil_changed (self):
        """ slot handle airfoil changed signal - save new design"""

        if self.mode_modify and self.airfoil.usedAsDesign: 

            case : Case_Direct_Design = self.case
            case.add_design(self.airfoil)

            self.set_airfoil (self.airfoil)                # new DESIGN - inform diagram   

            self._toast_message (f"New {self.airfoil.fileName} added")    

        self.refresh () 


    def _on_xo2_input_changed (self):
        """ slot handle change of xo2 input data"""

        logger.debug (f"{self} on_xo2_input_changed")

        # write back opPoint definitions and ref airfoils to namelist for change detection (save)
        case : Case_Optimize = self.case
        case.input_file.opPoint_defs.set_nml ()
        case.input_file.airfoils_ref_set_nml ()

        # polar definitions could have changed - update polarSets of airfoils 
        self.refresh_polar_sets (silent=True)

        # also refresh opPoint definition dialog if open 
        if self._xo2_opPoint_def_dialog:
            self._xo2_opPoint_def_dialog.refresh()

        self.refresh()
        self.sig_xo2_input_changed.emit()                                   # inform diagram 


    def _on_xo2_opPoint_def_changed (self):
        """ slot opPoint definiton changed in diagram"""

        if self._xo2_opPoint_def_dialog:
            self._xo2_opPoint_def_dialog.refresh_current ()
        self.refresh()            


    def _on_xo2_opPoint_def_selected (self):
        """ slot opPoint definiton selected either in panel or diagram"""

        if self._xo2_opPoint_def_dialog:
            self._xo2_opPoint_def_dialog.refresh_current ()
        self.sig_xo2_opPoint_def_selected.emit()
        self.refresh()            


    def _on_airfoil_design_selected (self, iDesign):
        """ slot to handle selection of new design airfoil in diagram """

        logger.debug (f"{str(self)} on airfoil design selected")
    
        try: 
            airfoil = self.case.airfoil_designs [iDesign]
            self.set_airfoil (airfoil)
        except: 
            pass


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

        self.sig_new_design.emit()                                          # refresh diagram 


    def _toast_message (self, msg, toast_style = style.HINT):

        # if self.mode_optimize:
        #     parent = self._xo2_panel
        # else: 
        #     parent = self._data_panel

        parent = self

        Toaster.showMessage (parent, msg, corner=Qt.Corner.BottomLeftCorner, margin=QMargins(10, 10, 10, 10),
                             toast_style=toast_style)


    def _save_settings (self):
        """ save settings to file """

        # get settings dict to avoid a lot of read/write
        settings = Settings().get_dataDict ()

        # save Window size and position 
        toDict (settings,'window_maximize', self.isMaximized())
        toDict (settings,'window_geometry', self.normalGeometry().getRect())

        # save panelling values 
        toDict (settings,'spline_nPanels',  Panelling_Spline().nPanels)
        toDict (settings,'spline_le_bunch', Panelling_Spline().le_bunch)
        toDict (settings,'spline_te_bunch', Panelling_Spline().te_bunch)

        toDict (settings,'bezier_nPanels',  Panelling_Bezier().nPanels)
        toDict (settings,'bezier_le_bunch', Panelling_Bezier().le_bunch)
        toDict (settings,'bezier_te_bunch', Panelling_Bezier().te_bunch)

        # save airfoils
        airfoil : Airfoil = self.airfoil_org if self.airfoil.usedAsDesign else self.airfoil

        if airfoil: 
            if airfoil.isExample:
                toDict (settings,'last_opened', None)
            else:
                toDict (settings,'last_opened', airfoil.pathFileName_abs)

        # reference airfoils 
        ref_list = []
        for airfoil in self.airfoils_ref:
            ref_entry = {}
            ref_entry ["path"] = airfoil.pathFileName_abs
            ref_entry ["show"] = airfoil.get_property ("show", True)
            ref_list.append (ref_entry)
        toDict (settings,'reference_airfoils', ref_list)

        # save polar definitions 
        def_list = []
        for polar_def in self.polar_definitions:
            def_list.append (polar_def._as_dict())
        toDict (settings,'polar_definitions', def_list)

        # save polar diagram settings 
        toDict (settings,'diagram_settings', self.diagram._as_dict_list())

        Settings().write_dataDict (settings)


    def _load_settings (self):
        """ load default settings from file """

        # panelling 

        nPanels  = Settings().get('spline_nPanels', None)
        le_bunch = Settings().get('spline_le_bunch', None)
        te_bunch = Settings().get('spline_te_bunch', None)

        if nPanels:     Panelling_Spline._nPanels = nPanels
        if le_bunch is not None:    Panelling_Spline._le_bunch = le_bunch
        if te_bunch is not None:    Panelling_Spline._te_bunch = te_bunch

        nPanels  = Settings().get('bezier_nPanels', None)
        le_bunch = Settings().get('bezier_le_bunch', None)
        te_bunch = Settings().get('bezier_te_bunch', None)

        if nPanels:     Panelling_Bezier._nPanels = nPanels
        if le_bunch is not None:    Panelling_Bezier._le_bunch = le_bunch
        if te_bunch is not None:    Panelling_Bezier._te_bunch = te_bunch

        # polar definitions 

        self._polar_definitions = []
        for def_dict in Settings().get('polar_definitions', []):
            self._polar_definitions.append(Polar_Definition(dataDict=def_dict))

        # reference airfoils 

        for ref_entry in Settings().get('reference_airfoils', []):
            if isinstance (ref_entry, str):                             # compatible with older version
                pathFileName = ref_entry
                show = True
            elif isinstance (ref_entry, dict):                          # mini dict with show boolean 
                pathFileName = ref_entry.get ("path", None)
                show         = ref_entry.get ("show", True)
            else:
                pathFileName = None 

            if pathFileName is not None: 
                try: 
                    airfoil = Airfoil.onFileType (pathFileName=pathFileName)
                    airfoil.load ()
                    airfoil.set_property ("show", show)
                    self.set_airfoil_ref (None, airfoil)
                except: 
                    pass


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
                self._toast_message (f"Options saved to Input file")


    @override
    def closeEvent  (self, event : QCloseEvent):
        """ main window is closed """

        # remove lost worker input files 
        if Worker.ready:
            Worker().clean_workingDir (self.airfoil.pathName)

        # terminate polar watchdog thread 

        if self._watchdog:
            self._watchdog.requestInterruption ()
            self._watchdog.wait()

        # save e..g diagram options 
        self._save_settings ()

        # inform parent (PlanformCreator) 
        self.sig_closing.emit (self.airfoil.pathFileName)

        event.accept()


# -----------------------------------------------------------------------------


class Watchdog (QThread):
    """ 
    Long running QThread to check if there is some new and signal parent
    
        - new polars generated - check Polar.Tasks 
        - airfoil removed or created again - check airfoils 
        - Xoptfoil2 state 

    """

    sig_new_polars          = pyqtSignal ()
    sig_xo2_new_state       = pyqtSignal ()
    sig_xo2_new_step        = pyqtSignal ()
    sig_xo2_new_design      = pyqtSignal (int)
    sig_xo2_still_running   = pyqtSignal ()


    def __init__ (self, parent = None):
        """ use .set_...(...) to put data into thread """

        super().__init__(parent)

        self._case_optimize_fn = None                           # Case_Optimize to watch      
        self._xo2_state        = None                           # last run state of xo2
        self._xo2_id           = None                           # instance id of xo2 for change detection
        self._xo2_nDesigns     = 0                              # last actual design    
        self._xo2_nSteps       = 0                              # last actual steps    


    def __repr__(self) -> str:
        """ nice representation of self """
        return f"<{type(self).__name__}>"


    def _check_case_optimize (self):
        """ check Case_Optimize for updates """

        if self._case_optimize_fn:

            case : Case_Optimize = self._case_optimize_fn ()

            # reset saved xo2 state for state change detection if there is new xo2 instance  

            if id(case.xo2) != self._xo2_id:
                case.results.set_results_could_be_dirty ()                      # ! will check for new Xoptfoil2 results
                self._xo2_id        = id(case.xo2)
                self._xo2_state     = case.xo2.state
                self._xo2_nDesigns  = case.xo2.nDesigns
                self._xo2_nSteps    = case.xo2.nSteps                           # new design will also update nsteps
                self.sig_xo2_new_state.emit()                                   # ensure, UI starts with current state 
                return 

            # detect state change of new design and siganl (if not first)

            if case.xo2.state != self._xo2_state:

                case.results.set_results_could_be_dirty ()                      # ! will check for new Xoptfoil2 results
                self._xo2_state = case.xo2.state
                self.sig_xo2_new_state.emit()

            elif case.xo2.nDesigns != self._xo2_nDesigns:

                case.results.set_results_could_be_dirty ()                      # ! will check for new Xoptfoil2 results
                self._xo2_nDesigns = case.xo2.nDesigns
                self._xo2_nSteps = case.xo2.nSteps                              # new design will also update nsteps
                self.sig_xo2_new_design.emit(case.xo2.nDesigns)

            elif case.xo2.nSteps != self._xo2_nSteps:

                case.results._reader_optimization_history.set_results_could_be_dirty(True)
                self._xo2_nSteps = case.xo2.nSteps
                self.sig_xo2_new_step.emit()
 
            elif case.isRunning:

                self.sig_xo2_still_running.emit()                             # update time elapsed etc.  


    def set_case_optimize (self, case_fn):
        """ set Case_Optimize to watch"""
        if (case_fn and isinstance (case_fn(), Case_Optimize)) or case_fn is None:
            self._case_optimize_fn = case_fn
            self.reset_watch_optimize ()


    def reset_watch_optimize (self):
        """ reset local state of optimization watch"""
        self._xo2_state        = None                           # last run state of xo2
        self._xo2_id           = None                           # instance id of xo2 for change detection
        self._xo2_nDesigns     = 0                              # last actual design    
        self._xo2_nSteps       = 0                              # last actual steps    


    @override
    def run (self) :
        # Note: This is never called directly. It is called by Qt once the
        # thread environment has been set up. 
        # Thread is started with .start()

        logger.info (f"{self} --> starting soon")
        self.msleep (1000)                                  # initial wait before polling begins 

        while not self.isInterruptionRequested():

            # check optimizer state 

            if self._case_optimize_fn:
                self._check_case_optimize ()

            # check for new polars 

            n_polars = 0 
            n_new_polars = 0 

            polar_tasks = Polar_Task.get_instances () 

            for task in polar_tasks: 

                n_polars     += task.n_polars
                n_new_polars += task.load_polars()

                if task.isCompleted():
                    task.finalize()
                else:
                    # this ensures, that polars are returned in the order tasks were generated
                    #   and not randomly by worker execution time 
                    #   -> more consistent diagram updates
                    break

            # if new polars loaded signal 

            if n_new_polars:

                self.sig_new_polars.emit()
                logger.debug (f"{self} --> {n_new_polars} new in {n_polars} polars")

            self.msleep (500)

        return 


#--------------------------------

def start ():

    dev_mode = os.path.isdir(os.path.dirname(os.path.realpath(__file__)) +"\\test_airfoils")

    # init logging - can be overwritten within a module  

    if dev_mode:   
        init_logging (level= logging.DEBUG)             # INFO, DEBUG or WARNING
    else:                       
        init_logging (level= logging.WARNING)

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
    # dev_mode = os.path.isdir(os.path.dirname(os.path.realpath(__file__)) +"\\test_airfoils")

    # # init logging - can be overwritten within a module  

    # if dev_mode:   
    #     init_logging (level= logging.DEBUG)             # INFO, DEBUG or WARNING
    # else:                       
    #     init_logging (level= logging.WARNING)

    # # command line arguments? 
    
    # parser = argparse.ArgumentParser(prog=APP_NAME, description='View and modify an airfoil')
    # parser.add_argument("airfoil", nargs='*', help="Airfoil .dat or .bez file to show")
    # args = parser.parse_args()
    # if args.airfoil: 
    #     initial_file = args.airfoil[0]
    # else: 
    #     initial_file = None

    # # init Qt Application and style  

    # app = QApplication(sys.argv)
    # app.setStyle('fusion')

    # main = Main_Window (initial_file)
    # main.show()
    # app.exec()
