#!/usr/bin/env pythonnowfinished
# -*- coding: utf-8 -*-

import os
import fnmatch      
import shutil   

from datetime               import datetime
from pathlib                import Path
from typing                 import override

from model.airfoil          import Airfoil, Airfoil_Bezier, Airfoil_Hicks_Henne, GEO_SPLINE, usedAs
from model.polar_set        import Polar_Definition

from model.xo2_input        import Input_File
from model.xo2_controller   import Xo2_Controller
from model.xo2_results      import Xo2_Results

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)

"""  

    Case Direct Design  

    Airfoil                         - Project for new airfoil - main class of data model 
        |-- Case                    - a single case, define specs for an optimization 
            |-- Designs             - the different designs of this design case 
                     
"""

class Case_Abstract:
    """
    Abstract super class of the different 'cases' like optimization, direct design
    """

    DESIGN_DIR_EXT = "_designs"
    DESIGN_NAME_BASE = "Design"

    @classmethod
    def design_fileName (cls, iDesign : int, extension : str) -> str:
        """ returns fileName of design iDesign"""

        return f"{cls.DESIGN_NAME_BASE}{iDesign:4}{extension}"

    @classmethod
    def get_iDesign (cls, airfoil : Airfoil) -> int:
        """ get iDesign from Airfoil fileName - or None if couldn't retrieved"""

        fileName = airfoil.fileName_stem
        if fileName.startswith (cls.DESIGN_NAME_BASE):
            return int (fileName [len(cls.DESIGN_NAME_BASE):])


    # ---------------------------------

    def __init__(self):

        self._airfoil_seed     = None                   
        self._airfoil_final    = None
        self._workingDir       = None 
        self._airfoil_designs  = [] 

    def __repr__(self) -> str:
        """ nice print string"""
        return f"<{type(self).__name__} {self.name}>"

    @property
    def name (self) -> str:
        # to be overridden 
        return "no name" 

    @property
    def workingDir (self) -> str:
        """working directory where airfoil or input file is located"""
        return self._workingDir

    @property
    def airfoil_seed (self) -> Airfoil: 
        """ seed or initial airfoil"""
        return self._airfoil_seed 
    
    @property
    def airfoil_final (self) -> Airfoil: 
        """ final airfoil"""
        return self._airfoil_final

    @property
    def airfoil_designs (self) -> list[Airfoil]: 
        """ list of airfoil designs - to be overridden"""
        return self._airfoil_designs     
      
    @property
    def airfoils_ref (self) -> list[Airfoil]:
        """ individual reference airfoils of this case"""
        return []


    def initial_airfoil_design (self) -> Airfoil:
        """ first initial design as the working airfoil """

        # to be overlaoded         
        return  self.airfoil_designs[-1] if self.airfoil_designs else None 

    

    def close (self, remove_designs : bool | None = None):
        """ shut down activities - to be overridden Design 
        """
        pass


# -------------------------------------------------------------------
    
class Case_Direct_Design (Case_Abstract):
    """
    A Direct Design Case: Manual modifications of an airfoil 
    """

    @staticmethod
    def remove_design_dir (airfoil_pathFileName : str):
        """ remove the design dir of airfoil_pathFileName"""

        design_dir = f"{os.path.splitext(airfoil_pathFileName)[0]}{Case_Abstract.DESIGN_DIR_EXT}"
        shutil.rmtree (design_dir, ignore_errors=True)


    def __init__(self, airfoil: Airfoil):

        super().__init__()

        self._airfoil_seed = airfoil
        self._workingDir   = airfoil.pathName_abs 

        # create design directory or read existing designs 
        if not os.path.isdir (self.design_dir_abs):
            os.makedirs(self.design_dir_abs)
        else:
            self._airfoil_designs = self._read_all_designs(self.design_dir, self.workingDir,
                                                            prefix=self.DESIGN_NAME_BASE,
                                                            extension=self.airfoil_seed.fileName_ext)


    @property
    def name (self) -> str:
        return self._airfoil_seed.fileName

    @property
    def design_dir (self) -> str:
        """ relative directory with airfoil designs"""

        return f"{os.path.splitext(self._airfoil_seed.fileName)[0]}{self.DESIGN_DIR_EXT}"


    @property
    def design_dir_abs (self) -> str:
        """ absolute directory with airfoil designs"""

        return os.path.join(self.workingDir, self.design_dir)


    @override
    @property
    def airfoil_designs (self) -> list[Airfoil]: 
        """ list of airfoil designs"""
        return self._airfoil_designs 
      

    def initial_airfoil_design (self) -> Airfoil:
        """ 
        returns first design as the working airfoil - either 
            - normalized version of seed airfoil 
            - last design of already existing design in design folder 
        """

        if self.airfoil_designs:
            airfoil =  self.airfoil_designs[-1]
        else: 
            try:                                                        # normal airfoil - allows new geometry
                airfoil  = self.airfoil_seed.asCopy (geometry=GEO_SPLINE)
            except:                                                     # bezier or hh does not allow new geometry
                airfoil  = self.airfoil_seed.asCopy ()
            airfoil.normalize(just_basic=True)              
            airfoil.useAsDesign()
            airfoil.set_pathName   (self.design_dir, noCheck=True)      # no check, because workingDir is needed
            airfoil.set_workingDir (self.workingDir)

            self.add_design (airfoil)

        airfoil_copy = airfoil.asCopy_design () 

        return airfoil_copy
    

    def add_design (self, airfoil : Airfoil):
        """ add a airfoil as a copy design to list - save it """

        # get highest design number 

        if len(self.airfoil_designs) > 0:
            iDesign = self.get_i_from_design (self.airfoil_designs[-1])
            iDesign += 1
        else: 
            iDesign = 0 

        # save and append copy to list of designs

        fileName = self.design_fileName (iDesign, airfoil.Extension)
        pathFileName = os.path.join (self.design_dir, fileName)

        airfoil_copy = airfoil.asCopy_design (pathFileName=pathFileName)
        airfoil_copy.save   (onlyShapeFile=True)            # save to file - in case of Bezier only .bez

        self.airfoil_designs.append (airfoil_copy)

        # prepare the current  airfoil 

        airfoil.set_fileName (fileName)                     # give a new filename to current
        airfoil.set_isModified (False)                      # avoid being saved for polar generation, there is already a Design


    def remove_design (self, airfoil_design : Airfoil) -> Airfoil:
        """ 
        Remove airfoil_design having design number of airfoil from list
        Returns next airfoil or None if it fails """

        # sanity - don't remove the first design 0 

        if len(self.airfoil_designs) <= 1: return

        # get the instance which could be a copy of airfoil_design and remove  

        airfoil = self.get_design_by_name (airfoil_design.fileName, as_copy=False)

        # remove it and return airfoil next to airfoil_design
        try: 
            i = self.airfoil_designs.index (airfoil)
            self.airfoil_designs.pop (i)

            # remove file 
            os.remove (airfoil.pathFileName_abs)

            if i < (len (self.airfoil_designs) - 1):
                next_airfoil = self.airfoil_designs [i]
            else: 
                next_airfoil = self.airfoil_designs [-1]
        except:
            logger.error (f"design airfoil {airfoil.fileName} couldn't be removed")

            self._airfoil_designs = None                        # reset list to reread
            return None

        return next_airfoil.asCopy_design ()    



    def get_design_by_name (self, fileName : str, as_copy = True):
        """ returns a working copy of Design having fileName (with or without extension)"""

        airfoil = None 
        for a in self.airfoil_designs:
            if a.fileName == fileName or os.path.splitext(a.fileName)[0] == fileName:
                airfoil = a
                break

        if airfoil is None:
            raise RuntimeError (f"Airfoil with fileName {fileName} doesn't exist anymore")
        else: 
            if as_copy:
                return airfoil.asCopy_design () 
            else: 
                return airfoil 


    def get_i_from_design (self, airfoil_design : Airfoil) -> int:
        """ returns the number of the design airfoil (retrieved from filename)"""

        i = None 
        base = os.path.splitext(airfoil_design.fileName)[0]         # remove extension
        base_parts = base.split()                                   # seperate number

        if len(base_parts) > 1:                                     # convert to int 
            try: 
                i = int (base_parts[-1])
            except:
                pass
        return i 


    def get_final_from_design (self, airfoil_org : Airfoil, airfoil_design : Airfoil) -> Airfoil:
        """ returns a final airfoil from airfoil_design based on original airfoil  """

        airfoil = airfoil_design.asCopy ()

        # create name extension - does name have already ..._mod?
     
        if airfoil_org.name.find ('mod') >= 0:
            i = self.get_i_from_design (airfoil_design)
            if i is not None:
                name_ext = f"_Design_{i}"
            else: 
                name_ext = f"_Design"
        else: 
            name_ext = f"_mod"

        # set new name and fileName 

        airfoil.set_name     (airfoil_org.name + name_ext)
        airfoil.set_pathName (airfoil_org.pathName)
        airfoil.set_fileName (airfoil_org.fileName_stem + name_ext + airfoil_design.fileName_ext)

        return airfoil


    @override
    def close (self, remove_designs : bool | None = None):
        """ 
        closes Case - remove design directory 
        
        Args: 
            remove_designs: True - remove 
                            False - do not remove 
                            None - remove if only 1 Design 
        """

        if remove_designs is None: 
            remove = len (self.airfoil_designs) < 2 
        else: 
            remove = remove_designs 

        if remove: 
            airfoil_pathFileName = os.path.join(self.workingDir, self._airfoil_seed.pathFileName)
            Case_Direct_Design.remove_design_dir (airfoil_pathFileName)


    # ---------------------------------


    def _read_all_designs (self, design_dir, working_dir, prefix : str = None, extension=".dat"):
        """ read all airfoils satisfying 'filter'

        Args:
            prefix (str, optional): file filter prefix for airfoils 
        """

        airfoils = []
        design_dir_abs = os.path.join (working_dir, design_dir)

        if not os.path.isdir (design_dir_abs): 
            return airfoils

        # read all file names in dir and filter 
 
        all_files     = os.listdir(design_dir_abs)                             
        airfoil_files = fnmatch.filter(all_files, f'{prefix}*{extension}')     

        # built pathFileName and sort 

        airfoil_files = [os.path.normpath(os.path.join(design_dir, f)) \
                            for f in airfoil_files if os.path.isfile(os.path.join(design_dir_abs, f))]
        airfoil_files = sorted (airfoil_files, key=str.casefold)

        # create Airfoils from file 

        for fileName in airfoil_files:
            try: 
                airfoil = Airfoil.onFileType(fileName, workingDir=working_dir, geometry=GEO_SPLINE)
                airfoil.load()
                airfoil.useAsDesign()
                airfoil_loaded = airfoil.isLoaded
            except:
                airfoil_loaded = False

            if airfoil_loaded:
                airfoils.append (airfoil)
            else:
                 logger.error (f"Could not load '{fileName}'")

        return airfoils 




class Case_Optimize (Case_Abstract):
    """
    A Xoptfoil2 optimizer Case 

    """

    def __init__(self, airfoil_or_input_file : Airfoil | str | None, workingDir=None):

        self._airfoil_seed     = None   
        self._airfoil_final    = None
        self._airfoil_designs  = None 

        self._input_file       = None
        self._results          = None

        # init input file instance 

        if airfoil_or_input_file is None:

            self._input_file    = Input_File ("new.xo2", workingDir=workingDir, is_new=True)

        elif isinstance (airfoil_or_input_file, Airfoil):

            airfoil : Airfoil = airfoil_or_input_file
            input_fileName      = Input_File.fileName_of (airfoil) 
            self._input_file    = Input_File (input_fileName, workingDir=airfoil.pathName)

        elif isinstance (airfoil_or_input_file, str):

            fileName : str      = airfoil_or_input_file
            self._input_file    = Input_File (fileName, workingDir=workingDir)

        else: 
            raise ValueError (f"{airfoil_or_input_file} not a valid argument")
        
        # init xo2 controller

        self._xo2 = Xo2_Controller (self.workingDir)

        # init xo2 results 

        self._results = Xo2_Results (self.workingDir, self.outName)


    @property
    def name (self) -> str:
       return self.input_file.fileName

    @override
    @property
    def workingDir (self) -> str:
        """working directory where input file is located"""
        return self.input_file.workingDir

    def set_workingDir (self, aDir : str):
        self.input_file.set_workingDir (aDir)


    @override
    @property
    def airfoil_seed (self) -> Airfoil: 
        """ seed or initial airfoil"""
        return self.input_file.airfoil_seed 
    
    @override
    @property
    def airfoil_final (self) -> Airfoil: 
        """ final airfoil - get it from xo2 results"""
        if self.isRunning:
            return None                                                 # no final during run 
        else:
            return self.results.airfoil_final

    @override
    @property
    def airfoil_designs (self) -> list [Airfoil]:
        """ list of airfoil designs"""
        return self.results.designs_airfoil

    @override
    @property
    def airfoils_ref (self) -> list[Airfoil]:
        """ individual reference airfoils of this case"""
        return self.input_file.airfoils_ref

    @property
    def input_file (self) -> Input_File:
        """ xo2 input file proxy"""
        return self._input_file
    
    @property
    def results (self) -> Xo2_Results:
        """ xo2 results handler"""
        return self._results


    @property
    def isInput_faultless (self) -> bool:
        """ is input file ready for optimization """
        return self.input_file.fileName and not self.input_file.hasErrors


    @property 
    def xo2 (self) -> Xo2_Controller:
        """ the Xoptfoil2 (controller) instance """

        return self._xo2
    
    def xo2_reset (self):
        """ reset Xoptfoil2 (controller) instance """

        # remove current, stateful xo2 controller 
        self._xo2 = Xo2_Controller (self.workingDir)


    @property
    def outName (self) -> str:
        """ outName of Xoptfoil2 equals stem of result airfoil (and base of temp directory)"""

        return Path(self.input_file.fileName).stem 


    @property
    def isRunning (self) -> bool:
        """ True if Xoptfoil2 is running"""
        return self.xo2.isRunning


    @property
    def isFinished (self) -> bool:
        """ 
        True if an optimization is finished ...
            - input file exists 
            - result airfoil is younger than results directory
            - xo2 is ready 
        """

        isFinished = False

        if os.path.isfile (self.input_file.pathFileName) and \
            self.results.date_time_last_write and \
            self.xo2.isReady and \
            self.airfoil_final is not None: 
                            
            airfoil_dt     = datetime.fromtimestamp(os.path.getmtime(self.airfoil_final.pathFileName_abs))

            if airfoil_dt >= self.results.date_time_last_write:
                isFinished = True

        return isFinished


    # ---- Methods -------------------------------------------

    def clear_results (self):
        """ removes all existing results - deletes result directory  """

        self._results = Xo2_Results (self.workingDir, self.outName, remove_result_dir=True, remove_airfoil=True)
        self._results.set_results_could_be_dirty ()


    def run (self):
        """ start a new optimization run """

        if not self.input_file.hasErrors and self.xo2.isReady:

            # be sure all changes written to file 
            self.input_file.save_nml()

            self.xo2.run (self.outName, self.input_file.fileName)



    def state_info (self):
        """returns state info tuple of current state (progress)

        Returns:
            state: xo2 state
            nSteps: number of optimization steps 
            nDesigns: number of optimization designs 
        """

        return self.xo2.state, self.xo2.nSteps, self.xo2.nDesigns
    