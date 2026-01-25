#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""

App model and state management for the airfoil editor.

- holding stateful data like current airfoil, case, polar definitions, etc.
- signals for changes in data to inform the UI
- loading and saving of airfoil specific settings
- watchdog thread for monitoring polar generation and optimization state
- can be notified of changes in airfoil geometry and other parameters

The App Model is needed as the 'real' model is QObject agnostic and stateless. 

"""

import os
import stat
from enum                    import Enum, auto
from typing                  import override
from shutil                  import copytree, rmtree
from PyQt6.QtCore            import pyqtSignal, QObject, QThread

from .resources              import get_assets_dir, get_xo2_examples_dir, XO2_EXAMPLE_DIR
from .base.common_utils      import Parameters, clip
from .base.app_utils         import Settings

# --- the real model imports
from .model.airfoil          import Airfoil, usedAs
from .model.airfoil_examples import Example
from .model.airfoil_geometry import Panelling_Spline, Panelling_Bezier, Line
from .model.polar_set        import Polar_Definition, Polar_Set, Polar_Task
from .model.xo2_driver       import Worker, Xoptfoil2
from .model.xo2_input        import OpPoint_Definition, Input_File
from .model.case             import Case_Direct_Design, Case_Optimize, Case_Abstract, Case_As_Bezier

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


# -----------------------------------------------------------------------------

class Mode_Id(Enum):
    """ Application Mode Identifiers """
    VIEW      = auto()
    MODIFY    = auto()
    OPTIMIZE  = auto()
    AS_BEZIER = auto()


# -----------------------------------------------------------------------------


class Airfoil_Settings (Parameters):
    """ 
    Settings for an airfoil which are stored with the airfoil
    in an individual settings file with airfoil fileName + '.ae'
    """

    FILE_EXTENSION = ".ae"

    @classmethod
    def settings_pathFileName (cls, airfoil : Airfoil) -> str:
        """ get settings file pathFileName for airfoil """
        return os.path.join (airfoil.pathName_abs, airfoil.fileName_stem + cls.FILE_EXTENSION)


    @classmethod
    def exists_for (cls, airfoil : Airfoil) -> bool:
        """ check if settings file exists for airfoil """

        if isinstance (airfoil, Airfoil):
            return os.path.isfile (cls.settings_pathFileName(airfoil))
        return False


    def __init__ (self, airfoil : Airfoil):

        if not isinstance (airfoil, Airfoil):
            raise ValueError (f"Airfoil_Settings: airfoil must be of type Airfoil")
        
        self._airfoil = airfoil
        
        super().__init__(self.settings_pathFileName (airfoil))


    def __repr__ (self) -> str:
        """ nice representation of self """
        return f"<{type(self).__name__} for Airfoil '{self._airfoil}'>"



# -----------------------------------------------------------------------------



class App_Model (QObject):

    """
    The App Mode is a shell around the Model enriched with App specific objects
    having a state of the current Airfoil
    and provides Signals when data is changed

    """

    WORKER_MIN_VERSION          = '1.0.11'
    XOPTFOIL2_MIN_VERSION       = '1.0.11'

    # --- signals

    sig_new_mode                = pyqtSignal()          # new mode selected
    sig_new_case                = pyqtSignal()          # new case selected
    sig_new_airfoil             = pyqtSignal()          # new airfoil selected

    sig_airfoil_changed         = pyqtSignal()          # current airfoil changed (geometry etc)
    sig_etc_changed             = pyqtSignal()          # reference airfoils etc changed
    sig_settings_loaded         = pyqtSignal()          # settings loaded for current airfoil

    sig_polar_set_changed       = pyqtSignal()          # polar set of one or more airfoils changed
    sig_new_polars              = pyqtSignal()          # new polars generated (Watchdog)

    sig_airfoil_geo_changed     = pyqtSignal()          # airfoil geometry is fast changing / moving 
    sig_airfoil_geo_te_gap      = pyqtSignal(object)    # te gap is fast changing / moving
    sig_airfoil_geo_le_radius   = pyqtSignal(object)    # le radius is fast changing / moving
    sig_airfoil_geo_paneling    = pyqtSignal(bool)      # airfoil panelling is fast changing / moving
    sig_airfoil_flap_set        = pyqtSignal(bool)      # flap setting (Flapper) changed / moving
    sig_airfoil_bezier          = pyqtSignal(Line.Type) # new bezier curve during match bezier 

    sig_xo2_run_started         = pyqtSignal()          # optimization run started
    sig_xo2_run_finished        = pyqtSignal()          # optimization run finished
    sig_xo2_new_state           = pyqtSignal()          # Xoptfoil2 new info/state (Watchdog)
    sig_xo2_new_design          = pyqtSignal()          # Xoptfoil2 new current design index (Watchdog)
    sig_xo2_new_step            = pyqtSignal()          # Xoptfoil2 new step (Watchdog)
    sig_xo2_still_running       = pyqtSignal()          # Xoptfoil2 still running (Watchdog)
    sig_xo2_input_changed       = pyqtSignal()          # xo2 input data changed (opPoints, ref airfoils, ...)
    sig_xo2_opPoint_def_selected= pyqtSignal()          # xo2 opPoint definition selected


    def __init__(self, workingDir_default: str = None, start_watchdog: bool = True):
        super().__init__()

        self._workingDir_default= workingDir_default if workingDir_default else os.getcwd()

        logger.info (f"Init App_Model - working dir: {self._workingDir_default}")

        self._version           = ""                    # application version
        self._change_text       = ""                    # change text for this version
        self._is_first_run      = False                 # is first run of this version

        self._mode_id : Mode_Id = None                  # current app mode

        self._airfoil           = None                  # current airfoil 
        self._airfoils_ref      = []                    # reference airfoils 
        self._airfoil_2         = None                  # 2nd airfoil for blend  
        self._show_airfoil_design = True                # show design airfoil by default

        self._xo2_iopPoint_def  = 0                     # current xo2 opPoint definition index
        self._xo2_run_started   = False                 # has xo2 run started

        self._polar_definitions = []                    # current polar definitions  
        self._case : Case_Abstract = None               # design Case holding all designs 

        self._settings = {}                             # actual loaded settings dict
        self._airfoil_settings_loaded = False           # have settings been loaded for current airfoil

        self._is_lower_minimized= False                 # is lower panel minimized
        
        self._watchdog = None                           # watchdog thread (may not be started)

        # set working dir for Example airfoils created
        Example.workingDir_default = workingDir_default   

        # setup path for worker and xoptfoil2 - and their working dir
        assets_dir = str(get_assets_dir()) 
        Worker    (workingDir=self._workingDir_default).isReady (assets_dir, min_version=self.WORKER_MIN_VERSION)
        Xoptfoil2 (workingDir=self._workingDir_default).isReady (assets_dir, min_version=self.XOPTFOIL2_MIN_VERSION)

        # initialize watchdog thread for polars and xo2 state changes (optional)
        if start_watchdog:
            self._init_watchdog()


    def __repr__(self):
        """ nice representation of self """
        if self.case:
            on_str = f" on {self.case}"
        else:
            on_str = f" on {self.airfoil}" if self.airfoil else ""
        return f"<App_Model{on_str}>"


    def _init_watchdog (self):
        """ initialize watchdog thread to check for new polars and xo2 state changes """

        self._watchdog = Watchdog (self) 

        # watch for new polars
        self._watchdog.sig_new_polars.connect       (self.sig_new_polars.emit)

        # watch xo2 state changes
        self._watchdog.sig_xo2_new_state.connect    (self._on_xo2_new_state)            
        self._watchdog.sig_xo2_new_design.connect   (self._on_xo2_new_design)  
        self._watchdog.sig_xo2_new_step.connect     (self.sig_xo2_new_step.emit)
        self._watchdog.sig_xo2_still_running.connect(self.sig_xo2_still_running.emit)

        self._watchdog.start()


    def _finish_watchdog (self):
        """ finish watchdog thread """

        if self._watchdog:

            # Disconnect all signals safely
            self._watchdog.sig_new_polars.disconnect()
            self._watchdog.sig_xo2_new_state.disconnect()
            self._watchdog.sig_xo2_new_design.disconnect()
            self._watchdog.sig_xo2_new_step.disconnect()
            self._watchdog.sig_xo2_still_running.disconnect()

            # Stop the thread
            self._watchdog.set_case_optimize(None)              # stop watching
            self._watchdog.requestInterruption()
            self._watchdog.wait(2000)                           # wait max 2s for finish
            
            self._watchdog = None


    def _refresh_polar_sets (self, silent=False):
        """ refresh polar sets of all airfoils with current polar definitions """

        changed = False 

        for airfoil in self.airfoils:

            # get re scale for reference airfoils
            re_scale = airfoil.scale_factor if airfoil.usedAs == usedAs.REF else 1.0

            # assign new polarset if it changed
            new_polarSet = Polar_Set (airfoil, polar_def=self.polar_definitions, re_scale=re_scale, only_active=True)

            # check changes to avoid unnecessary refresh
            if not new_polarSet.is_equal_to (airfoil.polarSet):
                changed = True 
                airfoil.set_polarSet (new_polarSet)

        if not silent and changed: 
            self.sig_polar_set_changed.emit()


    def _on_xo2_new_design (self):
        """ slot to handle new design during Xoptfoil2 run signaled by watchdog """

        case : Case_Optimize = self.case

        if not case.airfoil_designs: return 

        logger.debug (f"{str(self)} on Xoptfoil2 new design {case.xo2.nDesigns}")

        airfoil_design = case.airfoil_designs [-1]    

        # set new current airfoil - no polar_set to avoid polar generation during optimization  
        self.set_airfoil (airfoil_design, silent=True, assign_polar_set=False)         # new current airfoil

        self.sig_xo2_new_design.emit ()                                     # inform diagram


    def _on_xo2_new_state (self):
        """ slot to handle new state - will end watchdog if Xoptfoil2 doesn't run anymore """

        case : Case_Optimize = self.case

        logger.debug (f"{str(self)} on Xoptfoil2 new state {case.xo2.state}")

        # signal start and end of an optimization run
        if case.xo2.isRunning and not self._xo2_run_started:
            self._xo2_run_started = True

            self.sig_xo2_run_started.emit()

        elif not case.xo2.isRunning and self._xo2_run_started:
            self._xo2_run_started = False

            self._watchdog.set_case_optimize (None)                         # stop watching
            self.set_show_airfoil_design (False)                            # not show design airfoil finally
            # assign polar set to the last design airfoil (it was assigned without polar set during optimization)
            if self.airfoil:
                self.airfoil.set_polarSet (Polar_Set (self.airfoil, polar_def=self.polar_definitions, only_active=True))

            self.sig_xo2_run_finished.emit()                                # wake up UI

        self.sig_xo2_new_state.emit()


    # --- properties

    def set_app_info (self, version: str, change_text: str, is_first_run: bool):
        """ set application info """
        self._version        = version
        self._change_text    = change_text
        self._is_first_run   = is_first_run


    @property
    def mode_id (self) -> Mode_Id:
        """ current application mode id """
        return self._mode_id
    

    def set_mode_and_case (self, mode_id : Mode_Id, case : Case_Abstract):
        """ set new application mode id and case """

        # sanity - ensure mode and case are compatible

        ok = False
        if mode_id == Mode_Id.OPTIMIZE      and isinstance (case, Case_Optimize):
            ok = True
        elif mode_id == Mode_Id.MODIFY      and isinstance (case, Case_Direct_Design):
            ok = True
        elif mode_id == Mode_Id.AS_BEZIER   and isinstance (case, Case_As_Bezier):
            ok = True
        elif mode_id == Mode_Id.VIEW and case is None:
            ok = True

        if not ok:
            raise ValueError (f"{self} cannot set mode {mode_id} with case {case}")
        
        self.set_case (case)
        self._mode_id = mode_id
        self.sig_new_mode.emit()



    @property
    def is_ready (self) -> bool:
        """ is app model ready to work"""
        return self.airfoil or self.case 

    @property
    def is_mode_view (self) -> bool:
        """ is current mode view """
        return self._mode_id == Mode_Id.VIEW

    @property
    def is_mode_modify (self) -> bool:
        """ is current mode modify """
        return self._mode_id == Mode_Id.MODIFY

    @property
    def is_mode_optimize (self) -> bool:
        """ is current mode optimize """
        return self._mode_id == Mode_Id.OPTIMIZE

    @property
    def is_mode_as_bezier (self) -> bool:
        """ is current mode as bezier """
        return self._mode_id == Mode_Id.AS_BEZIER


    @property
    def case (self) -> Case_Abstract:
        """ design or optimize case holding all design airfoils"""
        return self._case 

    def set_case (self, case : Case_Abstract | None, silent: bool = True):
        """ set new case (design or optimize) - will also set new airfoil"""

        if isinstance (case, Case_Abstract) :

            logger.debug (f"{self} Set new {case} ")

            self._case = case

            self.set_airfoil (case.initial_airfoil_design(), silent=True)   # set initial design airfoil silently
            self._xo2_iopPoint_def  = 0                                     # reset state variables

            if not silent:  
                self.sig_new_case.emit()
        else: 
            self._case = None 

    @property
    def is_case_optimize (self) -> bool:
        """ is current case an optimize case """
        return isinstance (self.case, Case_Optimize)
    

    @property
    def airfoil (self) -> Airfoil:
        """ current airfoil with current polar definitions"""
        return self._airfoil 
    
    def set_airfoil (self, aNew : Airfoil, 
                     silent: bool = False,
                     load_settings: bool = False,
                     assign_polar_set: bool = True):

        if aNew == self.airfoil:
            return  

        logger.debug (f"{self} Set new airfoil {aNew}")

        # sanity cleanup Worker working dir of previous airfoil
        if self.airfoil:
            Worker().clean_workingDir (self.airfoil.pathName_abs)

        # set new airfoil 
        self._airfoil = aNew

        # assign polar set with current polar definitions
        if aNew is not None:
            if assign_polar_set: 
                self._airfoil.set_polarSet (Polar_Set (aNew, polar_def=self.polar_definitions, only_active=True))
            else: 
                self._airfoil.set_polarSet (Polar_Set (aNew, polar_def=[]))   # empty polar set

        # load settings if requested and available
        if load_settings and self.airfoil_settings_exist:
            self.load_settings()
            self._airfoil_settings_loaded = True
        else:
            self._airfoil_settings_loaded = False

        if not silent: 
            self.sig_new_airfoil.emit()


    def notify_airfoil_changed (self):
        """ notify self that current airfoil has changed """

        if isinstance (self.case, Case_Direct_Design) and self.airfoil.usedAsDesign:

            # create copy of airfoil and it add this to the list of designs, current gets new name
            case : Case_Direct_Design = self.case
            case.add_design(self.airfoil)

            # reset the polar set of the current airfoil ensure re-generation of polars (new filename)
            self.airfoil.set_polarSet (Polar_Set (self.airfoil, polar_def=self.polar_definitions, only_active=True))

            logger.debug (f"{self} airfoil_changed - added new design")
            self.sig_new_airfoil.emit()                             # inform diagram and data panel - new design generated


    def notify_airfoils_scale_changed (self):
        """ notify self that airfoil scale(s) have changed """
        self._refresh_polar_sets (silent=True)

        if self.is_case_optimize:                                   # reference airfoils are in input file
            self.notify_xo2_input_changed (silent=True)             # silent - we will signal soon

        self.sig_etc_changed.emit()


    def notify_polar_definitions_changed (self):
        """ notify self that polar definitions have changed """
        self._refresh_polar_sets (silent=False)


    def notify_airfoil_geo_changed (self):
        """ notify self that current airfoil geometry has changed rapidly """
        self.sig_airfoil_geo_changed.emit()


    def notify_airfoil_geo_te_gap (self, xBlend: float ):
        """ notify self that current airfoil geometry TE gap has changed rapidly """  
        self.sig_airfoil_geo_te_gap.emit (xBlend)


    def notify_airfoil_geo_le_radius (self, xBlend: float ):
        """ notify self that current airfoil geometry LE radius has changed rapidly """  
        self.sig_airfoil_geo_le_radius.emit (xBlend)


    def notify_airfoil_flap_set (self, is_set: bool):
        """ notify self that current airfoil flap setting has changed rapidly """  
        self.sig_airfoil_flap_set.emit (is_set)


    def notify_airfoil_geo_paneling (self, is_paneling: bool = True):
        """ notify self that current airfoil panelling has changed rapidly """  
        self.sig_airfoil_geo_paneling.emit (is_paneling)


    def notify_airfoil_bezier (self, line_type: Line.Type):
        """ notify self that current airfoil bezier has changed rapidly """  
        self.sig_airfoil_bezier.emit (line_type)



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
        self.sig_etc_changed.emit()             


    @property
    def airfoil_seed (self) -> Airfoil | None:
        """ seed airfoil of optimization or original airfoil during modify mode"""
        if self.case and self.case.airfoil_seed:
            seed =  self.case.airfoil_seed
            if not seed.polarSet:
               seed.set_polarSet (Polar_Set (seed, polar_def=self.polar_definitions, only_active=True))
            return seed
        else:
            return None

    @property
    def airfoil_design (self) -> Airfoil:
        """ the current design airfoil if available"""
        for airfoil in self.airfoils:
            if airfoil.usedAs == usedAs.DESIGN:
                return airfoil
    @property                    
    def show_airfoil_design (self) -> bool:
        """ should the design airfoil be shown"""
        # here in app_model that this setting applies to all designs
        return self._show_airfoil_design

    def set_show_airfoil_design (self, show: bool):
        self._show_airfoil_design = show


    @property
    def airfoil_final (self) -> Airfoil | None:
        """ final airfoil of optimization"""
        if isinstance (self.case, Case_Optimize):
            final =  self.case.airfoil_final
            if final and not final.polarSet:
               final.set_polarSet (Polar_Set (final, polar_def=self.polar_definitions, only_active=True))
            return final


    @property
    def airfoils_ref (self) -> list[Airfoil]:
        """ reference airfoils"""

        if self.is_case_optimize:

            # take individual reference airfoils of case optimize
            airfoils_ref = self.case.airfoils_ref if self.case else [] 
            # ensure polar sets are assigned 
            for airfoil in airfoils_ref:
                if not airfoil.polarSet:
                    airfoil.set_polarSet (Polar_Set (airfoil, polar_def=self.polar_definitions, 
                                                    re_scale=airfoil.scale_factor, only_active=True))                       
        else:
            airfoils_ref = self._airfoils_ref                               # normal handling

        return airfoils_ref


    def set_airfoil_ref (self, cur_airfoil_ref: Airfoil | None,
                               new_airfoil_ref: Airfoil | None,
                               silent = False):
        """ adds, replace, delete airfoil to the list of reference airfoils"""

        # sanity - check if already in list 
        if new_airfoil_ref in self.airfoils_ref: return 

        # replace or delete existing ref airfoil
        if cur_airfoil_ref:
            i = self.airfoils_ref.index (cur_airfoil_ref)
            if new_airfoil_ref:
                self.airfoils_ref[i] = new_airfoil_ref
            else: 
                del self.airfoils_ref [i]

        # add new ref airfoil
        elif new_airfoil_ref:
            self.airfoils_ref.append(new_airfoil_ref)

        # prepare new airfoil with polar_set 
        if new_airfoil_ref:

            new_airfoil_ref.set_polarSet (Polar_Set (new_airfoil_ref, polar_def=self.polar_definitions, 
                                                     re_scale=new_airfoil_ref.scale_factor, only_active=True))
            new_airfoil_ref.set_usedAs (usedAs.REF) 

        if not silent: 
            self.sig_etc_changed.emit()

        if self.is_case_optimize:                                   # reference airfoils are in input file
            self.notify_xo2_input_changed (silent=True)             # silent - we already signaled


    @property
    def airfoils (self) -> list [Airfoil]:
        """ list of airfoils (current, ref1 and ref2) """
        airfoils = []

        if self.airfoil_final:      airfoils.append (self.airfoil_final)
        if self.airfoil:            airfoils.append (self.airfoil)
        if self.airfoil_seed:       airfoils.append (self.airfoil_seed)
        if self.airfoil_2:          airfoils.append (self.airfoil_2)
        if self.airfoils_ref:       airfoils.extend (self.airfoils_ref)

        # remove duplicates 

        path_dict = {}
        airfoil : Airfoil 
        for airfoil in airfoils [:]:
            if path_dict.get (airfoil.pathFileName_abs, False):
                airfoils.remove (airfoil)
                if airfoil.usedAs == usedAs.REF:                    # sanity: also remove from ref airfoils 
                    self.set_airfoil_ref (airfoil, None, silent=True)
            else: 
                path_dict [airfoil.pathFileName_abs] = True

        return airfoils


    @property
    def airfoils_to_show (self) -> list[Airfoil]: 
        """ the airfoil(s) currently to show as list (filtered)"""

        # filter airfoils with 'show' property
        airfoils = []
        for airfoil in self.airfoils:

            if airfoil.usedAs == usedAs.DESIGN:
                if self.show_airfoil_design:                        # show design airfoil according to global setting  
                    airfoils.append (airfoil)
            elif airfoil.get_property("show",True):                 # individual show property
                airfoils.append (airfoil)

        # at least one airfoil should be there - take first 
        if not airfoils and self.airfoils: 
            first_airfoil = self.airfoils[0]
            first_airfoil.set_property("show", True)
            airfoils = [first_airfoil]

        return  airfoils 

    # --- Xoptfoil2
    

    @property
    def cur_opPoint_def (self) -> OpPoint_Definition:
        """ current xo2 opPoint_definition """
        case : Case_Optimize = self.case
        opPoint_defs = case.input_file.opPoint_defs if case else []
         
        # ensure current index is still valid with changed opPoint definitions
        self._xo2_iopPoint_def = clip (self._xo2_iopPoint_def, 0, len(opPoint_defs)-1)
        return opPoint_defs [self._xo2_iopPoint_def] if opPoint_defs else None


    def set_cur_opPoint_def (self, opPoint_def: OpPoint_Definition):
        """ set current xo2 opPoint_definition """
        case : Case_Optimize = self.case
        opPoint_defs = case.input_file.opPoint_defs if case else []

        self._xo2_iopPoint_def = opPoint_defs.index (opPoint_def) if opPoint_def in opPoint_defs else 0
        self.sig_xo2_opPoint_def_selected.emit()


    def notify_xo2_input_changed (self, silent: bool = False):
        """ notify self - change of xo2 input data"""

        logger.debug (f"{self} xo2_input_changed")
        
        case : Case_Optimize = self.case
        case.input_file.update_nml ()                                              # ensure namelist dict is up to date

        # polar definitions could have changed - update polarSets of airfoils 
        self._refresh_polar_sets (silent=True)

        if not silent:
            self.sig_xo2_input_changed.emit()                                       # inform diagram 


    @property
    def xo2_example_files (self) -> dict:
        """
        Returns dict of example xo2 input files by name
            collect in example dir and below 
        """ 

        # example_dir already copied to user data dir? Are they actual? 

        example_dir_org  = str(get_xo2_examples_dir())
        example_dir_user = os.path.join (self._workingDir_default, XO2_EXAMPLE_DIR)

        if not os.path.isdir (example_dir_org):
            return {}          # no examples available

        if not os.path.isdir (example_dir_user) :              
            copytree (example_dir_org, example_dir_user)
            logger.info (f"{self} {XO2_EXAMPLE_DIR} installed in {self._workingDir_default}") 

        # copy if org examples are newer than user ones
        elif os.path.getctime(example_dir_org) > os.path.getctime(example_dir_user):
            try:
                rmtree (example_dir_user)
                copytree (example_dir_org, example_dir_user)
                logger.info (f"{self} {XO2_EXAMPLE_DIR} updated in {self._workingDir_default}") 
            except (PermissionError, OSError) as e:
                logger.warning (f"{self} Failed to update {example_dir_user}: {e}. Using existing ones.")


        # collect all xo2 input files 

        examples_dict = {}

        for sub_dir, _, _ in os.walk(example_dir_user):
            for input_file in Input_File.files_in_dir (sub_dir, exclude_versions=True):
                examples_dict [input_file] = os.path.join (sub_dir, input_file)
        return examples_dict


    # --- polar definitions etc


    @property
    def polar_definitions (self) -> list [Polar_Definition]:
        """ list of current polar definitions """

        # take polar_defs defined by case optimize 

        if self.is_case_optimize:
            case : Case_Optimize = self.case
            polar_defs = case.input_file.opPoint_defs.polar_defs [:]
        else: 
            polar_defs = []

        # append existing, without duplicates and old mandatory (from old case optimize)

        polar_def : Polar_Definition
        for polar_def in self._polar_definitions:
            if not polar_def.is_in (polar_defs) and not (self.is_case_optimize and polar_def.is_mandatory):
                polar_def.set_is_mandatory (False)
                polar_defs.append (polar_def) 

        # ensure at least one polar 

        if not polar_defs: 
            polar_defs = [Polar_Definition()]

        self._polar_definitions = polar_defs    

        return self._polar_definitions


    @property
    def workingDir (self) -> str: 
        """ directory we are currently in (equals dir of airfoil)"""
        if self.case and self.case.workingDir:                                         # case working dir has priority 
            return self.case.workingDir
        elif self.airfoil:                                     
            return self.airfoil.pathName_abs
        else:
            return self._workingDir_default
        
    @property
    def settings (self) -> Parameters:
        """ current loaded settings """
        return self._settings

    @property
    def airfoil_settings_exist (self) -> bool:
        """ does current airfoil have individual settings file """
        return Airfoil_Settings.exists_for (self.airfoil)
    
    @property
    def airfoil_settings_loaded (self) -> bool:
        """ have settings been loaded for current airfoil """
        return self._airfoil_settings_loaded

    # ---- functions on state

    
    def load_settings (self):
        """ 
        Load and apply either default or individual settings for airfoil like view, polars, ...
        """

        airfoil = self.airfoil

        if self.airfoil_settings_exist:
            s = Airfoil_Settings (airfoil)

            self._airfoil_settings_loaded = True
            logger.info (f"{self} Individual settings loaded: {s.pathFileName}")

        else:
            s = Settings()
            self._airfoil_settings_loaded = False
            logger.info (f"{self} Settings loaded: {s.pathFileName}")

        # panelling 
        nPanels  = s.get ('spline_nPanels', None)
        le_bunch = s.get ('spline_le_bunch', None)
        te_bunch = s.get ('spline_te_bunch', None)

        if nPanels:                 Panelling_Spline._nPanels  = nPanels
        if le_bunch is not None:    Panelling_Spline._le_bunch = le_bunch
        if te_bunch is not None:    Panelling_Spline._te_bunch = te_bunch

        nPanels  = s.get ('bezier_nPanels', None)
        le_bunch = s.get ('bezier_le_bunch', None)
        te_bunch = s.get ('bezier_te_bunch', None)

        if nPanels:                 Panelling_Bezier._nPanels  = nPanels
        if le_bunch is not None:    Panelling_Bezier._le_bunch = le_bunch
        if te_bunch is not None:    Panelling_Bezier._te_bunch = te_bunch

        # polar definitions 
        self._polar_definitions : list [Polar_Definition] = []
        for def_dict in s.get('polar_definitions', []):
            self._polar_definitions.append(Polar_Definition(dataDict=def_dict))
        self._polar_definitions.sort (key=lambda aDef : aDef.re)

        # reference airfoils including initial re scale 

        self._airfoils_ref : list [Airfoil] = []

        ref_entries = s.get('reference_airfoils', [])

        for ref_entry in ref_entries:
            if isinstance (ref_entry, str):                             # compatible with older version
                pathFileName = ref_entry
                show = True
                scale = None
            elif isinstance (ref_entry, dict):                          # mini dict with show boolean 
                pathFileName = ref_entry.get ("path", None)
                show         = ref_entry.get ("show", True)
                scale        = ref_entry.get ("scale", None)
            else:
                pathFileName = None 

            if pathFileName is not None: 
                try: 
                    airfoil = Airfoil.onFileType (pathFileName=pathFileName)
                    airfoil.load ()
                    airfoil.set_property ("show", show)
                    airfoil.set_scale_factor (scale)
                    self.set_airfoil_ref (None, airfoil, silent=True)
                except Exception as e: 
                    logger.warning (f"{self} Reference airfoil {pathFileName} could not be loaded: {e}")

        # update polar sets of airfoils
        self._refresh_polar_sets (silent=True)

        self._settings = s

        self.sig_settings_loaded.emit()

        return 


    def delete_airfoil_settings (self):
        """ delete individual settings file of airfoil """

        if Airfoil_Settings.exists_for (self.airfoil):

            Airfoil_Settings (self.airfoil).delete_file()

            # load the default settings again
            self.load_settings ()


    def save_settings (self, to_app_settings: bool = False,
                               add_key: str = "",
                               add_value = None):
        """ 
        Save settings either to app settings or to settings of current airfoil
            An additional key, value pair (like diagram settings)can be added"""

        # save either in global settings or airfoil individual settings
        if to_app_settings:
            s = Settings()
        else:
            s = Airfoil_Settings (self.airfoil)
            s.clear()                                       # new rebuild of settings

        # save panelling values 
        s.set ('spline_nPanels',  Panelling_Spline().nPanels)
        s.set ('spline_le_bunch', Panelling_Spline().le_bunch)
        s.set ('spline_te_bunch', Panelling_Spline().te_bunch)

        s.set ('bezier_nPanels',  Panelling_Bezier().nPanels)
        s.set ('bezier_le_bunch', Panelling_Bezier().le_bunch)
        s.set ('bezier_te_bunch', Panelling_Bezier().te_bunch)

        # add reference airfoils 
        ref_list = []
        for airfoil in self.airfoils_ref:
            ref_entry = {}
            ref_entry ["path"]  = airfoil.pathFileName_abs
            if not airfoil.get_property ("show", True):             # avoid default True
                ref_entry ["show"]  = airfoil.get_property ("show", True)
            if airfoil.isScaled:                                    # avoid default 1.0
                ref_entry ["scale"] = airfoil.scale_factor
            ref_list.append (ref_entry)
        s.set ('reference_airfoils', ref_list)

        # add polar definitions 
        def_list = []
        for polar_def in self.polar_definitions:
            def_list.append (polar_def._as_dict())
        s.set ('polar_definitions', def_list)

        # add additional settings
        if add_key:
            s.set (add_key, add_value)

        # finally save either in global settings or airfoil individual settings
        s.save()
        logger.info (f"{s} saved to {s.pathFileName}")

        self._settings = s

        if not to_app_settings:
            self._airfoil_settings_loaded = True


    def close (self):
        """ finish app model """

        self._finish_watchdog()

        if Worker.ready and self.airfoil:
            Worker().clean_workingDir (self.airfoil.pathName)


    def remove_current_design (self):
        """ remove current design and set new current design airfoil"""

        if isinstance (self.case, Case_Direct_Design) and self.airfoil.usedAsDesign:

            case : Case_Direct_Design = self.case
            next_airfoil =case.remove_design(self.airfoil)

            self.set_airfoil (next_airfoil)


    def run_xo2 (self): 
        """ run xo2 optimizer"""

        case : Case_Optimize = self.case

        # reset current xo2 controller if there was an error 
        if case.xo2.isRun_failed:
            case.xo2_reset()

        if case.xo2.isReady:

            # be sure input file data is written to file 

            if case.input_file.isChanged:                
                case.input_file.save_nml()

            # clear previous results - prepare UI 

            case.clear_results ()
            self.set_airfoil (None, silent=True)                # clear current airfoil during optimization run
            self.set_show_airfoil_design (True)                 # do show design airfoil initially

            self._watchdog.set_case_optimize (case)             # will start watching this case

            # let's go

            case.run()

# -----------------------------------------------------------------------------


class Watchdog (QThread):
    """ 
    Long running QThread to check if there is some new and signal parent
    
        - new polars generated - check Polar.Tasks 
        - Xoptfoil2 state 

    """

    sig_new_polars          = pyqtSignal ()
    sig_xo2_new_state       = pyqtSignal ()
    sig_xo2_new_step        = pyqtSignal ()
    sig_xo2_new_design      = pyqtSignal ()
    sig_xo2_still_running   = pyqtSignal ()


    def __init__ (self, parent = None):
        """ use .set_...(...) to put data into thread """

        super().__init__(parent)

        self._case_optimize : Case_Optimize = None              # Case_Optimize to watch      
        self._xo2_state        = None                           # last run state of xo2
        self._xo2_id           = None                           # instance id of xo2 for change detection
        self._xo2_nDesigns     = 0                              # last actual design    
        self._xo2_nSteps       = 0                              # last actual steps    


    def __repr__(self) -> str:
        """ nice representation of self """
        return f"<{type(self).__name__}>"


    def _check_case_optimize (self):
        """ check Case_Optimize for updates """

        if self._case_optimize:

            case : Case_Optimize = self._case_optimize

            # reset cached progress and result up to date info
            there_is_progress = case.xo2.refresh_progress ()                    # ensure progress info is up to date
            case.results.set_results_could_be_outdated ()                       # will check for new Xoptfoil2 results


            # reset saved xo2 state for state change detection if there is new xo2 instance 

            if id(case.xo2) != self._xo2_id:
                self._xo2_id        = id(case.xo2)
                self._xo2_state     = case.xo2.state
                self._xo2_nDesigns  = case.xo2.nDesigns
                self._xo2_nSteps    = case.xo2.nSteps                           # new design will also update nsteps
                self.sig_xo2_new_state.emit()                                   # ensure, UI starts with current state 
                return 

            # get current xo2 state and nDesigns, nSteps 

            xo2_state    = case.xo2.state                                       # ... will re-calc state info 
            xo2_nDesigns = case.xo2.nDesigns
            xo2_nSteps   = case.xo2.nSteps  

            if there_is_progress:
                logger.debug (f"{self} xo2 state: {xo2_state}, designs: {xo2_nDesigns}, steps: {xo2_nSteps}")
            else:
                logger.debug (f"{self} xo2 state: {xo2_state}, no progress ...")

            # detect state change of new design and signal (if not first)

            if xo2_state != self._xo2_state:

                self._xo2_state = case.xo2.state
                self.sig_xo2_new_state.emit()

            if there_is_progress:

                if xo2_nSteps != self._xo2_nSteps:

                    self._xo2_nSteps = xo2_nSteps
                    self.sig_xo2_new_step.emit()
    
                if xo2_nDesigns != self._xo2_nDesigns:

                    self._xo2_nDesigns = xo2_nDesigns
                    self.sig_xo2_new_design.emit()

            elif case.isRunning:

                self.sig_xo2_still_running.emit()                             # update time elapsed etc.  



    def set_case_optimize (self, case : Case_Optimize | None):
        """ set Case_Optimize to watch"""

        if (case and isinstance (case, Case_Optimize)) or case is None:
            self._case_optimize = case
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

        logger.info (f"Starting Watchdog")
        self.msleep (1000)                                  # initial wait before polling begins 

        while not self.isInterruptionRequested():

            # check optimizer state 

            if self._case_optimize:
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
                    #   and not randomly by worker execution time -> more consistent diagram updates
                    # break
                    pass        # deactivated 

            # if new polars loaded signal 

            if n_new_polars:

                self.sig_new_polars.emit()
                logger.debug (f"{self} --> {n_new_polars} new in {n_polars} polars")

            self.msleep (500)

        return 
