#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""

Application state management for the airfoil editor.

Holding stateful model data like current airfoil, case, polar definitions, etc.

"""

import os
from typing                 import override
from PyQt6.QtCore           import pyqtSignal, QObject, QThread

from base.common_utils      import Parameters
from base.app_utils         import Settings

from model.airfoil          import Airfoil, usedAs
from model.airfoil_examples import Example
from model.airfoil_geometry import Panelling_Spline, Panelling_Bezier, Line
from model.polar_set        import Polar_Definition, Polar_Set, Polar_Task
from model.xo2_driver       import Worker, Xoptfoil2
from model.xo2_input        import Input_File
from model.case             import Case_Direct_Design, Case_Optimize, Case_Abstract, Case_As_Bezier




import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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


class App_Model (QObject):

    """
    The App Mode is a shell around the Model enriched whith App speficic objects
    having a state of the current Airfoil
    and provides Signals when data is changed

    """

    WORKER_MIN_VERSION         = '1.0.10'
    XOPTFOIL2_MIN_VERSION      = '1.0.10'


    sig_new_airfoil             = pyqtSignal()          # new airfoil selected 
    sig_airfoil_changed         = pyqtSignal()          # current airfoil changed (geometry etc)
    sig_etc_changed             = pyqtSignal()          # reference airfoils etc changed
    sig_settings_loaded         = pyqtSignal()          # settings loaded for current airfoil

    sig_polar_set_changed       = pyqtSignal()          # polar set of one or more airfoils changed
    sig_new_polars              = pyqtSignal()          # new polars generated (Watchdog)

    sig_airfoil_geo_changed     = pyqtSignal()          # airfoil geometry is fast changing / moving 
    sig_airfoil_geo_te_gap      = pyqtSignal(object, object)  # te gap is fast changing / moving
    sig_airfoil_geo_le_radius   = pyqtSignal(object, object)  # le radius is fast changing / moving
    sig_airfoil_flap_set        = pyqtSignal(bool)      # flap setting (Flapper) changed / moving

    sig_xo2_new_state           = pyqtSignal()          # Xoptfoil2 new info/state (Watchdog)
    sig_xo2_new_design          = pyqtSignal(int)       # Xoptfoil2 new current design index (Watchdog)


    def __init__(self, workingDir_default: str = None):
        super().__init__()

        self._workingDir_default = workingDir_default if workingDir_default else os.getcwd()

        self._airfoil           = None                  # current airfoil 
        self._airfoils_ref      = []                    # reference airfoils 
        self._airfoils_ref_scale= None                  # indexed list of re scale factors of ref airfoils
        self._airfoil_2         = None                  # 2nd airfoil for blend    

        self._polar_definitions = []                    # current polar definitions  
        self._case : Case_Abstract = None               # design Case holding all designs 

        self._settings = {}                             # actual loaded settings dict
        self._airfoil_settings_loaded = False           # have settings been loaded for current airfoil

        self._is_lower_minimized= False                 # is lower panel minimized

        # set working dir for Example airfoils created
        Example.workingDir_default = workingDir_default   

        # Worker for polar generation and Xoptfoil2 for optimization ready? 
        modulesDir = os.path.dirname(os.path.abspath(__file__))                
        projectDir = os.path.dirname(modulesDir)

        Worker    (workingDir=self._workingDir_default).isReady (projectDir, min_version=self.WORKER_MIN_VERSION)
        Xoptfoil2 (workingDir=self._workingDir_default).isReady (projectDir, min_version=self.XOPTFOIL2_MIN_VERSION)

        # initialize watchdog thread for polars and xo2 state changes
        self._init_watchdog()


    def _init_watchdog (self):
        """ initialize watchdog thread to check for new polars and xo2 state changes """

        self._watchdog = Watchdog (self) 
        self._watchdog.sig_new_polars.connect       (self.sig_new_polars.emit)
        self._watchdog.sig_xo2_new_state.connect    (self.sig_xo2_new_state.emit)            
        self._watchdog.sig_xo2_new_design.connect   (self.sig_xo2_new_design.emit)  
        self._watchdog.start()


    def _finish_watchdog (self):
        """ finish watchdog thread """

        if self._watchdog:
            self._watchdog.requestInterruption()
            self._watchdog.wait (2000)                     # wait max 2s for finish
            self._watchdog = None


    def _refresh_polar_sets (self, silent=False):
        """ refresh polar sets of all airfoils with current polar definitions """

        changed = False 

        for airfoil in self.airfoils:

            # get re scale for reference airfoils
            if airfoil.usedAs == usedAs.REF:
                iRef, _ = airfoil.usedAs_i_Ref (self.airfoils)
                re_scale = self.airfoils_ref_scale [iRef] if self.airfoils_ref_scale [iRef] else 1.0
            else:
                re_scale = 1.0 

            # assign new polarset if it changed

            new_polarSet = Polar_Set (airfoil, polar_def=self.polar_definitions, re_scale=re_scale, only_active=True)

            # check changes to avoid unnecessary refresh
            if not new_polarSet.is_equal_to (airfoil.polarSet):
                changed = True 
                airfoil.set_polarSet (new_polarSet)

        if not silent and changed: 
            self.sig_polar_set_changed.emit()



    @property
    def case (self) -> Case_Abstract:
        """ design or optimize case holding all design airfoils"""
        return self._case 

    def set_case (self, case : Case_Abstract | None):
        """ set new case (design or optimize) - will also set new airfoil"""

        if isinstance (case, Case_Abstract) :
            self._case = case
            self.set_airfoil (case.initial_airfoil_design())
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
    
    def set_airfoil (self, aNew : Airfoil):

        self._airfoil = aNew

        if aNew is not None: 
            self._airfoil.set_polarSet (Polar_Set (aNew, polar_def=self.polar_definitions, only_active=True))

        self._airfoil_settings_loaded = False

        # cleanup Worker working dir of previous airfoil
        Worker().clean_workingDir (self.workingDir)

        logger.debug (f"Set new {aNew} {'having settings' if self.airfoil_settings_exist else ''}")

        self.sig_new_airfoil.emit ()


    def notify_airfoil_changed (self):
        """ notify self that current airfoil has changed """

        if isinstance (self.case, Case_Direct_Design) and self.airfoil.usedAsDesign:

            case : Case_Direct_Design = self.case
            case.add_design(self.airfoil)

            self.set_airfoil (self.airfoil)                # new DESIGN - inform diagram   


    def notify_polar_definitions_changed (self):
        """ notify self that polar definitions have changed """
        self._refresh_polar_sets (silent=False)


    def notify_airfoil_geo_changed (self):
        """ notify self that current airfoil geometry has changed rapidly """
        self.sig_airfoil_geo_changed.emit()


    def notify_airfoil_geo_te_gap (self, new_gap: float, xBlend: float ):
        """ notify self that current airfoil geometry TE gap has changed rapidly """  
        self.sig_airfoil_geo_te_gap.emit (new_gap, xBlend)


    def notify_airfoil_geo_le_radius (self, new_radius: float, xBlend: float ):
        """ notify self that current airfoil geometry LE radius has changed rapidly """  
        self.sig_airfoil_geo_le_radius.emit (new_radius, xBlend)


    def notify_airfoil_flap_set (self, is_set: bool):
        """ notify self that current airfoil flap setting has changed rapidly """  
        self.sig_airfoil_flap_set.emit (is_set)


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
        if self.case:
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
    def airfoil_final (self) -> Airfoil | None:
        """ final airfoil of optimization"""
        if isinstance (self.case, Case_Optimize):
            final =  self.case.airfoil_final
            if final and not final.polarSet:
               final.set_polarSet (Polar_Set (final, polar_def=self.polar_definitions, only_active=True))
            return final


    @property
    def airfoils_ref_scale (self) -> list:
        """ chord/re scale factor of ref airfoils"""

        if self._airfoils_ref_scale is None: 
            self._airfoils_ref_scale = [None] * len(self.airfoils_ref)
        return self._airfoils_ref_scale


    def set_airfoils_ref_scale (self, scales: list[float|None]):
        """ set chord/re scale factor of ref airfoils"""

        if len(scales) != len(self.airfoils_ref):
            raise ValueError (f"length of ref_scales {len(scales)} does not match n airfoils ref {len(self.airfoils_ref)}")
        
        self._airfoils_ref_scale = scales

        # update polar sets of reference airfoils
        self._refresh_polar_sets ()


    @property
    def airfoils_ref (self) -> list[Airfoil]:
        """ reference airfoils"""

        if self.is_case_optimize:
            # take individual reference airfoils of case optimize
            airfoils_ref = self.case.airfoils_ref if self.case else []                         
        else:
            airfoils_ref = self._airfoils_ref                               # normal handling
 
        # ensure scale property is set for airfoil artist 
        if self._airfoils_ref_scale is None:                                # first time not initialized
            self._airfoils_ref_scale = [None] * len(airfoils_ref)
        airfoil : Airfoil
        for iRef, airfoil in enumerate(airfoils_ref):
            airfoil.set_property ("scale", self._airfoils_ref_scale[iRef])  # used in airfoil_artist to scale airfoil

        return airfoils_ref


    def set_airfoil_ref (self, cur_airfoil_ref: Airfoil | None,
                               new_airfoil_ref: Airfoil | None,
                               scale : float|None = None,
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
                del self.airfoils_ref_scale [i]

        # add new ref airfoil
        elif new_airfoil_ref:
            self.airfoils_ref.append(new_airfoil_ref)
            self.airfoils_ref_scale.append(scale)

        # prepare new airfoil with polar_set 
        if new_airfoil_ref:
            if scale is None:                                   # get current scale at i 
                i = self.airfoils_ref.index (new_airfoil_ref)
                scale = self.airfoils_ref_scale [i]

            new_airfoil_ref.set_polarSet (Polar_Set (new_airfoil_ref, polar_def=self.polar_definitions, 
                                                     re_scale=scale, only_active=True))
            new_airfoil_ref.set_usedAs (usedAs.REF) 


        if not silent: 
            self.sig_etc_changed.emit()

        if self.is_case_optimize:                                   # reference airfoils are in input file
            self._on_xo2_input_changed (silent=True)                # silent - we already signaled


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
        if self.case:                                         # case working dir has priority 
            return self.case.workingDir
        elif self.airfoil:                                     
            return self.airfoil.pathName
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
            logger.info (f"Settings of {airfoil} loaded from {s.pathFileName}")

        else:
            s = Settings()
            self._airfoil_settings_loaded = False
            logger.info (f"Application settings loaded from {s.pathFileName}")

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
        self._airfoils_ref_scale : list [float|None] = []

        ref_entries = s.get('reference_airfoils', [])

        for ref_entry in ref_entries:
            if isinstance (ref_entry, str):                             # compatible with older version
                pathFileName = ref_entry
                show = True
            elif isinstance (ref_entry, dict):                          # mini dict with show boolean 
                pathFileName = ref_entry.get ("path", None)
                show         = ref_entry.get ("show", True)
                scale        = ref_entry.get ("scale", None)
                scale        = round(scale,2) if scale else None
            else:
                pathFileName = None 

            if pathFileName is not None: 
                try: 
                    airfoil = Airfoil.onFileType (pathFileName=pathFileName)
                    airfoil.load ()
                    airfoil.set_property ("show", show)
                    self.set_airfoil_ref (None, airfoil, scale=scale, silent=True)
                except Exception as e: 
                    logger.warning (f"Reference airfoil {pathFileName} could not be loaded: {e}")

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
        for iRef, airfoil in enumerate(self.airfoils_ref):
            ref_entry = {}
            ref_entry ["path"]  = airfoil.pathFileName_abs
            ref_entry ["show"]  = airfoil.get_property ("show", True)
            if self.airfoils_ref_scale [iRef]:
                ref_entry ["scale"] = self.airfoils_ref_scale [iRef]
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

            # get current xo2 state and nDesigns, nSteps 

            xo2_state    = case.xo2.state                                       # ... will re-calc state info 
            xo2_nDesigns = case.xo2.nDesigns
            xo2_nSteps   = case.xo2.nSteps  

            # detect state change of new design and siganl (if not first)

            if xo2_state != self._xo2_state:

                case.results.set_results_could_be_dirty ()                      # ! will check for new Xoptfoil2 results
                self._xo2_state = case.xo2.state
                self.sig_xo2_new_state.emit()

            elif xo2_nSteps != self._xo2_nSteps:

                case.results._reader_optimization_history.set_results_could_be_dirty(True)
                self._xo2_nSteps = xo2_nSteps
                self.sig_xo2_new_step.emit()

            elif xo2_nDesigns != self._xo2_nDesigns:

                case.results.set_results_could_be_dirty ()                      # ! will check for new Xoptfoil2 results
                self._xo2_nDesigns = xo2_nDesigns
                self.sig_xo2_new_design.emit(case.xo2.nDesigns)
 
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

        logger.info (f"Starting Watchdog Thread")
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
                    #   and not randomly by worker execution time -> more consistent diagram updates
                    # break
                    pass        # deactivated 

            # if new polars loaded signal 

            if n_new_polars:

                self.sig_new_polars.emit()
                logger.debug (f"{self} --> {n_new_polars} new in {n_polars} polars")

            self.msleep (500)

        return 
