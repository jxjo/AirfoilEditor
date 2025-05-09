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
from pathlib import Path

from PyQt6.QtCore           import QMargins, QThread
from PyQt6.QtWidgets        import QApplication, QMainWindow, QWidget 
from PyQt6.QtWidgets        import QVBoxLayout, QHBoxLayout, QMessageBox
from PyQt6.QtGui            import QCloseEvent, QGuiApplication

# let python find the other modules in modules relativ to path of self - ! before python system modules
# common modules hosted by AirfoilEditor 
# sys.path.insert (1,os.path.join(Path(__file__).parent , 'modules'))

# let python find the other modules in modules relativ to path of self  
sys.path.append(os.path.join(Path(__file__).parent , 'modules'))

from model.airfoil          import Airfoil, usedAs
from model.airfoil_geometry import Panelling_Spline, Panelling_Bezier
from model.polar_set        import Polar_Definition, Polar_Set
from model.xo2_driver       import Worker, Xoptfoil2
from model.xo2_controller   import xo2_state
from model.case             import Case_Direct_Design

from base.common_utils      import * 
from base.panels            import Container_Panel, Win_Util, Toaster
from base.widgets           import *

from airfoil_widgets        import * 
from airfoil_diagrams       import * 

from airfoil_dialogs        import Airfoil_Save_Dialog, Blend_Airfoil_Dialog, Repanel_Airfoil_Dialog
from airfoil_ui_panels      import * 

from xo2_dialogs            import Xo2_Run_Dialog, Xo2_Choose_Optimize_Dialog
from xo2_panels             import *

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)



#-------------------------------------------------------------------------------
# The App   
#-------------------------------------------------------------------------------


APP_NAME         = "Airfoil Editor"
APP_VERSION      = "4.0 dev Optimizer"


class App_Main (QMainWindow):
    '''
        The Airfoil Editor App
    '''

    name = APP_NAME  

    WORKER_MIN_VERSION         = '1.0.5'
    XOPTFOIL2_MIN_VERSION      = '1.0.5'


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

    sig_mode_optimize           = pyqtSignal(bool)      # enter / leave mode optimize
    sig_new_case_optimize       = pyqtSignal()          #  new case optimize selected
    sig_xo2_new_state           = pyqtSignal()          # Xoptfoil2 new info/state
    sig_xo2_input_changed       = pyqtSignal()          # data of Xoptfoil2 input changed
    sig_opPoint_def_selected    = pyqtSignal(object)    # new opPoint definition selected somewhere 
    sig_opPoint_def_changed     = pyqtSignal(object)    # opPoint definition changed (in diagram) 

    sig_closing                 = pyqtSignal(str)       # the app is closing with an airfoils pathFilename


    def __init__(self, airfoil_file, parent=None):
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

        self._data_panel        = None                  # main panels of app
        self._file_panel        = None
        self._diagram           = None

        self._xo2_panel         = None                 
        self._xo2_opPoint_def_dialog = None             # singleton for this dialog 
        self._xo2_run_dialog    = None                  # singleton for this dialog 

        # if called from other applcation (PlanformCreator) make it modal to this 

        if parent is not None:
            self.setWindowModality(Qt.WindowModality.ApplicationModal)  

        # get icon either in modules or in icons 
        
        self.setWindowIcon (Icon ('AE_ico.ico'))

        # get initial window size from settings

        Settings.belongTo (__file__, nameExtension=None, fileExtension= '.settings')
        geometry = Settings().get('window_geometry', [])
        maximize = Settings().get('window_maximize', False)
        Win_Util.set_initialWindowSize (self, size_frac= (0.85, 0.80), pos_frac=(0.1, 0.1),
                                        geometry=geometry, maximize=maximize)
        
        # load settings

        self._load_settings ()


        # if no initial airfoil file, try to get last openend airfoil file 

        if not airfoil_file: 
            airfoil_file = Settings().get('last_opened', default=None) 

        airfoil = create_airfoil_from_path(self, airfoil_file, example_if_none=True, message_delayed=True)

        self.set_airfoil (airfoil, silent=True)


        # Worker for polar generation and Xoptfoil2 for optimization ready? 

        Worker().isReady (os.path.dirname(os.path.abspath(__file__)), min_version=self.WORKER_MIN_VERSION)
        if Worker.ready:
            Worker().clean_workingDir (self.airfoil().pathName)

        Xoptfoil2().isReady (os.path.dirname(os.path.abspath(__file__)), min_version=self.XOPTFOIL2_MIN_VERSION)


        # init main layout of app

        self._data_panel    = Container_Panel (title="Data panel", hide=lambda:     self.mode_optimize)
        self._xo2_panel     = Container_Panel (title="Xo2 panel",  hide=lambda: not self.mode_optimize)
        self._file_panel    = Container_Panel (title="File panel", width=250)
        self._diagram       = Diagram_Airfoil_Polar (self, self.airfoils, 
                                                     polar_defs_fn = self.polar_definitions,
                                                     case_fn = lambda: self.case, 
                                                     diagram_settings= Settings().get('diagram_settings', []))

        l_main = self._init_layout() 

        container = QWidget()
        container.setLayout (l_main) 
        self.setCentralWidget (container)


        # ---- signals and slots --------------------------------------------------------------

        # install watchdog for poars generated by Worker 

        if Worker.ready:
             self._watchdog = Watchdog (self) 
             self._watchdog.sig_new_polars.connect       (self._diagram.on_new_polars)
             self._watchdog.sig_xo2_new_state.connect    (self._on_new_xo2_state)            
             self._watchdog.sig_xo2_new_design.connect   (self._on_new_xo2_design)                   # new current, update diagram  
             self._watchdog.start()

        # connect diagram signals to slots of self

        self._diagram.sig_airfoil_changed.connect           (self._on_airfoil_changed)
        self._diagram.sig_polar_def_changed.connect         (self.refresh_polar_sets)
        self._diagram.sig_airfoil_ref_changed.connect       (self.set_airfoil_ref)
        self._diagram.sig_airfoil_design_selected.connect   (self.set_airfoil)
        self._diagram.sig_opPoint_def_selected.connect      (self.sig_opPoint_def_selected.emit)    # inform dialog 
        self._diagram.sig_opPoint_def_changed.connect       (self.sig_opPoint_def_changed.emit)     # inform dialog 
        self._diagram.sig_opPoint_def_changed.connect       (self._on_xo2_input_changed)            # save to nml
        self._diagram.sig_opPoint_def_dblClick.connect      (self.edit_opPoint_def)

        # connect self signals to slots of diagram

        self.sig_new_airfoil.connect            (self._diagram.on_airfoil_changed)
        self.sig_new_design.connect             (self._diagram.on_new_design)
        self.sig_airfoil_changed.connect        (self._diagram.on_airfoil_changed)
        self.sig_airfoil_2_changed.connect      (self._diagram.on_airfoil_2_changed)
        self.sig_bezier_changed.connect         (self._diagram.on_bezier_changed)
        self.sig_panelling_changed.connect      (self._diagram.on_airfoil_changed)
        self.sig_blend_changed.connect          (self._diagram.on_airfoil_changed)
        self.sig_polar_set_changed.connect      (self._diagram.on_polar_set_changed)
        self.sig_airfoils_ref_changed.connect   (self._diagram.on_airfoils_ref_changed)

        self.sig_mode_optimize.connect          (self._diagram.on_mode_optimize)
        self.sig_xo2_new_state.connect          (self._diagram.on_new_xo2_state)
        self.sig_xo2_input_changed.connect      (self._diagram.on_new_xo2_state)
        self.sig_new_case_optimize.connect      (self._diagram.on_new_case_optimize)

        self.sig_enter_blend.connect            (self._diagram.on_blend_airfoil)
        self.sig_enter_panelling.connect        (self._diagram.on_enter_panelling)


    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"


    def _init_layout (self): 
        """ init main layout with the different panels """

        #  ||               lower                         >||
        #  || file panel ||        data panel             >||
        #                 | Geometry  | Coordinates | ... >| 

        l_xo2 = QHBoxLayout()        
        l_xo2.addWidget (Panel_Xo2_Case                    (self, lambda: self.case))
        l_xo2.addWidget (Panel_Xo2_Shape_Bezier            (self, lambda: self.case))
        l_xo2.addWidget (Panel_Xo2_Shape_Hicks_Henne       (self, lambda: self.case))
        l_xo2.addWidget (Panel_Xo2_Shape_Camb_Thick        (self, lambda: self.case))
        l_xo2.addWidget (Panel_Xo2_Operating_Conditions    (self, lambda: self.case))
        l_xo2.addWidget (Panel_Xo2_Geometry_Targets        (self, lambda: self.case))
        l_xo2.addWidget (Panel_Xo2_Curvature               (self, lambda: self.case))
        
        l_xo2.setContentsMargins (QMargins(0, 0, 0, 0))
        self._xo2_panel.setLayout (l_xo2)

        l_data = QHBoxLayout()        
        l_data.addWidget (Panel_Geometry        (self, self.airfoil))
        l_data.addWidget (Panel_Panels          (self, self.airfoil))
        l_data.addWidget (Panel_LE_TE           (self, self.airfoil))
        l_data.addWidget (Panel_Bezier          (self, self.airfoil))
        l_data.addWidget (Panel_Bezier_Match    (self, self.airfoil))
        l_data.setContentsMargins (QMargins(0, 0, 0, 0))
        self._data_panel.setLayout (l_data)

        l_file = QHBoxLayout()
        l_file.addWidget (Panel_File_Modify     (self, self.airfoil))
        l_file.addWidget (Panel_File_Optimize   (self, lambda: self.case))
        l_file.addWidget (Panel_File_View       (self, self.airfoil))
        l_file.setContentsMargins (QMargins(0, 0, 0, 0))
        self._file_panel.setLayout (l_file)

        l_lower = QGridLayout()
        l_lower.addWidget (self._file_panel, 0, 0, 1, 1)
        l_lower.addWidget (self._data_panel, 0, 1, 1, 1)
        l_lower.addWidget (self._xo2_panel , 0, 1, 1, 1)
        l_lower.setHorizontalSpacing (5)
        l_lower.setColumnStretch (2,1)
        l_lower.setContentsMargins (QMargins(0, 0, 0, 0))

        lower = QWidget ()
        lower.setMinimumHeight(180)
        lower.setMaximumHeight(180)
        lower.setLayout (l_lower)

        # main layout with diagram panel and lower 

        l_main = QVBoxLayout () 
        l_main.addWidget (self._diagram, stretch=2)
        l_main.addWidget (lower)
        l_main.setContentsMargins (QMargins(5, 5, 5, 5))

        return l_main 

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

        self.setWindowTitle (APP_NAME + "  v" + str(APP_VERSION) + "  [" + self._case.name + "]")

        if not silent: 
                self.refresh ()
                self.sig_new_case_optimize.emit()


    def airfoil (self) -> Airfoil:
        """ encapsulates current airfoil. Childs should acces only via this function
        to enable a new airfoil to be set """
        return self._airfoil 


    def airfoils (self) -> list [Airfoil]:
        """ list of airfoils (current, ref1 and ref2) """
        airfoils = []

        if self.airfoil():          airfoils.append (self.airfoil())
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

        self._airfoil = aNew

        if aNew is not None: 
            self._airfoil.set_polarSet (Polar_Set (aNew, polar_def=self.polar_definitions(), only_active=True))

            logger.debug (f"Load new airfoil: {aNew.name}")
            self.setWindowTitle (APP_NAME + "  v" + str(APP_VERSION) + "  [" + self._airfoil.fileName + "]")

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
        elif self.airfoil():                                     
            return self.airfoil().pathName
        else:
            ""


    def polar_definitions (self) -> list [Polar_Definition]:
        """ list of current polar definitions """

        if self.mode_optimize:
            # get polar definitions from xo2 input file 
            return self._case.polar_definitions_of_input()
        else:
            if not self._polar_definitions: 
                self._polar_definitions = [Polar_Definition()]
            return self._polar_definitions

      
    @property
    def airfoils_ref (self) -> list[Airfoil]:
        """ reference airfoils"""
        return self._airfoils_ref
    
    def set_airfoil_ref (self, cur_airfoil_ref: Airfoil | None,
                               new_airfoil_ref: Airfoil | None):
        """ adds, replace, delete airfoil to the list of reference airfoils"""

        # check if already in list 
        if new_airfoil_ref in self.airfoils_ref: return 

        if new_airfoil_ref:
            new_airfoil_ref.set_polarSet (Polar_Set (new_airfoil_ref, polar_def=self.polar_definitions(), only_active=True))
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
               seed.set_polarSet (Polar_Set (seed, polar_def=self.polar_definitions(), only_active=True))
            return seed
        

    @property
    def airfoil_final (self) -> Airfoil | None:
        """ final airfoil of optimization"""
        if self.mode_optimize and self.case:
            final =  self.case.airfoil_final
            if final and not final.polarSet:
               final.set_polarSet (Polar_Set (final, polar_def=self.polar_definitions(), only_active=True))
            return final


    @property
    def airfoil_org (self) -> Airfoil:
        """ the original airfoil during modify mode"""
        return self._airfoil_org if self.mode_modify else None

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
            new_airfoil = self.case.get_final_from_design (self.airfoil_org, self.airfoil())

            # dialog to edit name, chose path, ..

            dlg = Airfoil_Save_Dialog (parent=self, getter=new_airfoil)
            ok_save = dlg.exec()

            if not ok_save: 
                return                                          # save was cancelled - return to modify mode 
            else: 
                remove_designs = dlg.remove_designs

        # leave mode_modify  

        if not ok:
            new_airfoil = self._airfoil_org                     # restore original airfoil 

        # close case 

        self.case.close (remove_designs=remove_designs)       # shut down case
        self.set_case (None)                                

        self.set_mode_modify (False)  
        self.set_airfoil (new_airfoil, silent=False)



    def mode_optimize_finished (self, ok=False):
        """ 
        optimize airfoil finished - switch to view mode 
            - ok == False: optimize mode was cancelled 
            - ok == True:  user wants to finish 
        """

        remove_designs  = None                              # let case.close decide to remove design dir 

        # sanity
        if not self.mode_optimize: return 

        if ok:
            # be sure input file data is written to file 
            case: Case_Optimize = self.case
            if case.input_file.isChanged:
                case.input_file.save_nml()

            new_airfoil = self.case.airfoil_final
        else: 
            new_airfoil = self._airfoil_org                 # restore original airfoil 

        # close open opPoint_def dialog 
        if self._xo2_opPoint_def_dialog:
             self._xo2_opPoint_def_dialog.close()

        # self.case.close (remove_designs=remove_designs)     # shut down case
        self.set_case (None)  
        self.set_mode_optimize (False) 
        self.set_airfoil (new_airfoil, silent=True)         # refresh will be don later 
   

        self.refresh()  
        self.sig_mode_optimize.emit(False)                  # signal leave mode optimize for diagram


    def change_case_optimize (self, input_fileName : str, workingDir):
        """ change current optimization case to new input file """

        # check if changes were made in current case 
        case: Case_Optimize = self.case
        if isinstance (case, Case_Optimize):
            if case.input_file.isChanged:
                text = f"Save changes made for {case.name}?"
                button = MessageBox.save (self, "Save Case", text)
                if button == QMessageBox.StandardButton.Save:
                    case.input_file.save_nml()
                elif button == QMessageBox.StandardButton.Discard:
                    pass
                else:
                    return

        # close open opPoint_def dialog 
        if self._xo2_opPoint_def_dialog:
             self._xo2_opPoint_def_dialog.close()

        # set new case 
        self.set_case_optimize (Case_Optimize (input_fileName, workingDir=workingDir))

        self.set_airfoil (self.case.initial_airfoil_design(), silent=True)     # maybe there is already an existing design 

        # replace polar definitions with the ones defined by Xo2 input file 
        self.refresh_polar_sets (silent=True)

        self.refresh()  
        self.sig_new_case_optimize.emit()                                   # signal for diagram


    def refresh(self):
        """ refreshes all child panels of edit_panel """

        logger.debug (f"{self} refresh main panels")

        self._xo2_panel.refresh()
        self._data_panel.refresh()
        self._file_panel.refresh()


    def refresh_polar_sets (self, silent=False):
        """ refresh polar sets of all airfoils"""

        changed = False 

        for airfoil in self.airfoils():

            new_polarSet = Polar_Set (airfoil, polar_def=self.polar_definitions(), only_active=True)

            # check changes to avoid unnecessary refresh
            if not new_polarSet.is_equal_to (airfoil.polarSet):
                changed = True 
                airfoil.set_polarSet (new_polarSet)

        if not silent and changed: 
            self._xo2_panel.refresh()
            self.sig_polar_set_changed.emit()




    # --- airfoil functions -----------------------------------------------


    def modify_airfoil (self):
        """ modify airfoil - switch to modify mode - create Case """
        if self.mode_modify: return 

        # create new Design Case and get/create first design 

        self.set_case (Case_Direct_Design (self._airfoil))

        self.set_mode_modify (True)       
        self.set_airfoil (self.case.initial_airfoil_design(), silent=False)


    def optimize_airfoil (self):
        """ optimize airfoil with Xoptfoil2 - switch to optimize mode - create Case """
        
        if self.mode_modify or not Xoptfoil2.ready : return 

        case = None 

        input_fileNames = Case_Optimize.input_fileNames_in_dir (self.workingDir)

        if input_fileNames:
            # change directly to mode optimize if there is an input file in directory
            input_fileName   = Case_Optimize.input_fileName_of (self.airfoil())
            initial_fileName = input_fileName if input_fileName is not None else input_fileNames [0]

            case = Case_Optimize (initial_fileName, workingDir=self.workingDir)

        else:
            # otherwise open selection dailog 
            diag = Xo2_Choose_Optimize_Dialog (self, None, self.airfoil(), parentPos=(0.15,0.9), dialogPos=(0,1))
            rc = diag.exec()

            if rc == QDialog.DialogCode.Accepted:
                case = Case_Optimize (diag.input_fileName, workingDir=diag.workingDir)
            else:
                return

        self.set_case_optimize (case, silent=True)    

        if case:
            
            self.set_mode_optimize (True)                                   # switch UI 
            self.set_airfoil (case.initial_airfoil_design(), silent=True)     # maybe there is already an existing design 

            # replace polar definitions with the ones defined by Xo2 input file 
            self.refresh_polar_sets (silent=True)

            self.refresh()  
            self.sig_mode_optimize.emit(True)                               # signal enter / leave mode optimize for diagram



    def new_as_Bezier (self):
        """ create new Bezier airfoil based on current airfoil, create Case, switch to modify mode """

        # create initial Bezier airfoil based on current

        airfoil_bez = Airfoil_Bezier.onAirfoil (self._airfoil)

        # create new Design Case and get/create first design 

        self.set_case (Case_Direct_Design (airfoil_bez))

        self.set_mode_modify (True)  
        self.set_airfoil (self.case.initial_airfoil_design() , silent=False)
  


    def blend_with (self): 
        """ run blend airfoil with dialog to blend current with another airfoil""" 

        self.sig_enter_blend.emit()

        dialog = Blend_Airfoil_Dialog (self, self.airfoil(), self.airfoil_org, 
                                       parentPos=(0.25, 0.75), dialogPos=(0,1))  

        dialog.sig_blend_changed.connect (self.sig_blend_changed.emit)
        dialog.sig_airfoil_2_changed.connect (self.set_airfoil_2)
        dialog.exec()     

        if dialog.airfoil2 is not None: 
            # do final blend with high quality (splined) 
            self.airfoil().geo.blend (self.airfoil_org.geo, 
                                      dialog.airfoil2.geo, 
                                      dialog.blendBy) 
        self.set_airfoil_2 (None)

        self._on_airfoil_changed()


    def repanel_airfoil (self): 
        """ run repanel dialog""" 

        self.sig_enter_panelling.emit()

        dialog = Repanel_Airfoil_Dialog (self, self.airfoil().geo,
                                         parentPos=(0.35, 0.75), dialogPos=(0,1))

        dialog.sig_new_panelling.connect (self.sig_panelling_changed.emit)
        dialog.exec()     

        if dialog.has_been_repaneled:
            # finalize modifications 
            self.airfoil().geo.repanel (just_finalize=True)                

        self._on_airfoil_changed()


    def edit_opPoint_def (self, parent:QWidget, parentPos:Tuple, dialogPos:Tuple, opPoint_def : OpPoint_Definition):
        """ open dialog to edit current xo2 opPoint def - relativ position with parent is provided"""

        if self._xo2_opPoint_def_dialog is None:

            diag = Xo2_OpPoint_Def_Dialog (parent, self.case, opPoint_def, parentPos=parentPos, dialogPos=dialogPos) 

            # connect to selected signals from panel and diagram 
            self.sig_opPoint_def_selected.connect (diag.set_opPoint_def)
            self.sig_opPoint_def_changed.connect  (diag.set_opPoint_def)

            diag.sig_opPoint_def_changed.connect  (self._on_xo2_input_changed)
            diag.sig_finished.connect             (self.edit_opPoint_def_finished)

            self._xo2_opPoint_def_dialog = diag             # singleton 

        else: 
            self._xo2_opPoint_def_dialog.activateWindow ()

        self._xo2_opPoint_def_dialog.show () 


    def edit_opPoint_def_finished (self, diag : Xo2_OpPoint_Def_Dialog):
        """ slot - dialog to edit current opPoint def finished"""

        # diag.sig_opPoint_def_changed.disconnect  (self.sig_xo2_input_changed.emit)
        # diag.sig_finished.disconnect             (self.edit_opPoint_def_finished)

        self.sig_opPoint_def_selected.disconnect (diag.set_opPoint_def)
        self.sig_opPoint_def_changed.disconnect  (diag.set_opPoint_def)

        self._xo2_opPoint_def_dialog = None     


    def optimize_run (self):
        """ open optimize dialog"""

        if self._xo2_run_dialog: 
            self._xo2_run_dialog.activateWindow()
            return                                 # already openend?

        # be sure input file data is written to file 

        case: Case_Optimize = self.case
        saved = case.input_file.save_nml()


        diag = Xo2_Run_Dialog (self._file_panel, self.case, dx=100, dy=-400)

        diag.sig_finished.connect (self._optimize_run_finished)

        # connect watchdog of xo2 to dialog 

        self._watchdog.set_case_optimize (lambda: self.case)

        self._watchdog.sig_xo2_new_state.connect        (self._data_panel.refresh)
        self._watchdog.sig_xo2_new_state.connect        (self._file_panel.refresh)
        self._watchdog.sig_xo2_new_state.connect        (diag.on_results)
        self._watchdog.sig_xo2_new_design.connect       (diag.on_results)
        self._watchdog.sig_xo2_still_running.connect    (diag.refresh)

        # run immedately if ready (and not finished)

        if  (case.xo2.isReady and not case.isFinished):
            diag.run_optimize()                             # run xo2 
            diag.refresh()                                  # ensure the right panel when shown 

        diag.show()

        self._xo2_run_dialog = diag


    def _optimize_run_finished (self):
        """ slot for Xo2_Run_Dialog finished"""

        diag = self._xo2_run_dialog

        self._watchdog.sig_xo2_new_state.disconnect     (self._data_panel.refresh)
        self._watchdog.sig_xo2_new_state.disconnect     (self._file_panel.refresh)

        self._watchdog.sig_xo2_new_state.disconnect     (diag.on_results)
        self._watchdog.sig_xo2_new_design.disconnect    (diag.on_results)
        self._watchdog.sig_xo2_still_running.disconnect (diag.refresh)
        self._watchdog.set_case_optimize (None)

        self._xo2_run_dialog = None


    # --- private ---------------------------------------------------------


    def _on_airfoil_changed (self):
        """ slot handle airfoil changed signal - save new design"""

        if self.mode_modify and self.airfoil().usedAsDesign: 

            self.case.add_design(self.airfoil())

            self.set_airfoil (self.airfoil())                # new DESIGN - inform diagram       

        self.refresh () 


    def _on_xo2_input_changed (self):
        """ slot handle change of xo2 input data"""

        logger.debug (f"{self} on_xo2_input_changed")

        # write back opPoint definitions to namelist for change detection (save)
        case : Case_Optimize = self.case
        case.input_file.opPoint_defs.set_nml ()

        # polar definitions could have changed - update polarSets of airfoils 
        self.refresh_polar_sets (silent=True)

        # also refresh opPoint definition dialog if open 
        if self._xo2_opPoint_def_dialog:
            self._xo2_opPoint_def_dialog.refresh()

        self.refresh()
        self.sig_xo2_input_changed.emit()                                   # inform diagram 


    def _on_new_xo2_state (self):
        """ slot to handle new state during Xoptfoil2 run"""

        self.refresh ()

         # inform diagram a little delayed so reffresh can take place 
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


    def _toast_message (self, msg, toast_style : style = None):

        parent = self._diagram._viewPanel
        Toaster.showMessage (parent, msg, corner=Qt.Corner.BottomLeftCorner, margin=QMargins(0, 0, 0, 0),
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
        airfoil : Airfoil = self.airfoil_org if self.airfoil().usedAsDesign else self.airfoil()

        if airfoil.isExample:
            toDict (settings,'last_opened', None)
        else:
            toDict (settings,'last_opened', airfoil.pathFileName)

        # reference airfoils 
        ref_list = []
        for airfoil in self.airfoils_ref:
            ref_entry = {}
            ref_entry ["path"] = airfoil.pathFileName
            ref_entry ["show"] = airfoil.get_property ("show", True)
            ref_list.append (ref_entry)
        toDict (settings,'reference_airfoils', ref_list)

        # save polar definitions 
        def_list = []
        for polar_def in self.polar_definitions():
            def_list.append (polar_def._as_dict())
        toDict (settings,'polar_definitions', def_list)

        # save polar diagram settings 
        toDict (settings,'diagram_settings', self._diagram._as_dict_list())

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
                    airfoil = Airfoil(pathFileName=pathFileName)
                    airfoil.load ()
                    airfoil.set_property ("show", show)
                    self.set_airfoil_ref (None, airfoil)
                except: 
                    pass


    @override
    def closeEvent  (self, event : QCloseEvent):
        """ main window is closed """

        # remove lost worker input files 
        if Worker.ready:
            Worker().clean_workingDir (self.airfoil().pathName)

        # terminate polar watchdog thread 

        if self._watchdog:
            self._watchdog.requestInterruption ()
            self._watchdog.wait()

        # save e..g diagram options 
        self._save_settings ()

        # inform parent (PlanformCreator) 
        self.sig_closing.emit (self.airfoil().pathFileName)

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
    sig_xo2_new_design      = pyqtSignal (int)
    sig_xo2_still_running   = pyqtSignal ()


    def __init__ (self, parent = None):
        """ use .set_...(...) to put data into thread """

        super().__init__(parent)

        self._case_optimize_fn = None                           # Case_Optimize to watch      
        self._xo2_state        = None                           # last run state of xo2
        self._xo2_nDesigns     = 0                              # last actual steps    


    def __repr__(self) -> str:
        """ nice representation of self """
        return f"<{type(self).__name__}>"


    def _check_case_optimize (self):
        """ check Case_Optimize for updates """

        if self._case_optimize_fn:

            case : Case_Optimize = self._case_optimize_fn ()

            if case.xo2.state != self._xo2_state:

                case.results.set_results_could_be_dirty ()                      # ! will check for new Xoptfoil2 results
                self.sig_xo2_new_state.emit()
                self._xo2_state = case.xo2.state

            elif case.xo2.nDesigns != self._xo2_nDesigns:

                case.results.set_results_could_be_dirty ()                      # ! will check for new Xoptfoil2 results
                self.sig_xo2_new_design.emit(case.xo2.nDesigns)
                self._xo2_nDesigns = case.xo2.nDesigns

            elif case.isRunning:

                self.sig_xo2_still_running.emit()                               # update time elapsed etc.  


    def set_case_optimize (self, case_fn):
        """ set Case_Optimize to watch"""
        if (case_fn and isinstance (case_fn(), Case_Optimize)) or case_fn is None:
            self._case_optimize_fn = case_fn



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

            n_new_polars = 0 
            polar_tasks = Polar_Task.get_instances () 

            for task in polar_tasks: 

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
                logger.debug (f"{self} --> {n_new_polars} new polars")

            self.msleep (500)

        return 


#--------------------------------


if __name__ == "__main__":

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
        airfoil_file = args.airfoil[0]
    else: 
        airfoil_file = None

    # init Qt Application and style  

    app = QApplication(sys.argv)
    app.setStyle('fusion')

    # set dark / light mode for widgets depending on system mode 

    scheme = QGuiApplication.styleHints().colorScheme()
    Widget.light_mode = not (scheme == Qt.ColorScheme.Dark)

    Main = App_Main (airfoil_file)
    Main.show()
    app.exec()

    