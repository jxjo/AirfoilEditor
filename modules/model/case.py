#!/usr/bin/env pythonnowfinished
# -*- coding: utf-8 -*-

import os
import fnmatch      
import shutil           

from model.airfoil          import Airfoil, Airfoil_Bezier, Airfoil_Hicks_Henne, usedAs, GEO_BASIC, GEO_SPLINE
from model.polar_set        import Polar_Set

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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

    def __init__(self):

        self._airfoil_seed     = None                   
        self._airfoil_final    = None
        self._airfoil_designs  = None 


    @property
    def airfoil_seed (self) -> Airfoil: 
        """ seed or initial airfoil"""
        return self._airfoil_seed 
    
    @property
    def airfoil_final (self) -> Airfoil: 
        """ final airfoil"""
        return self._airfoil_final
    

    
class Case_Direct_Design (Case_Abstract):
    """
    A Direct Design Case: Manual modifications of an airfoil 
    """

    DESIGN_DIR_EXT = "_designs"
    DESIGN_NAME_BASE = "Design"

    def __init__(self, airfoil: Airfoil):

        super().__init__()

        self._airfoil_seed = airfoil 

        # create design directory 
        if not os.path.isdir (self.design_dir):
            os.makedirs(self.design_dir)


    @property
    def design_dir (self) -> str:
        """ directory with airfoil designs"""
        base=os.path.basename (self._airfoil_seed.pathFileName)
        dir =os.path.dirname  (self._airfoil_seed.pathFileName)
        design_dir_name = f"{os.path.splitext(base)[0]}{self.DESIGN_DIR_EXT}"
        return os.path.join(dir, design_dir_name)

    @property
    def airfoil_designs (self) -> list[Airfoil]: 
        """ list of airfoil designs"""
        if self._airfoil_designs is None: 
            self._airfoil_designs = Reader_Airfoil_Designs(self.design_dir).read_all(prefix=self.DESIGN_NAME_BASE)
        return self._airfoil_designs 

    @property
    def nDesigns (self) -> int:
        """ number of actual designs """
        return len(self.airfoil_designs) 
      

    def first_working_design (self) -> Airfoil:
        """ 
        returns first design as the working airfoil - either 
            - normalized version of seed airfoil 
            - last design of already existing design in design folder 
        """

        if self.airfoil_designs:
            airfoil =  self.airfoil_designs[-1]
        else: 
            try:                                            # normal airfoil - allows new geometry
                airfoil  = self.airfoil_seed.asCopy (geometry=GEO_SPLINE)
            except:                                         # bezier or hh does not allow new geometry
                airfoil  = self.airfoil_seed.asCopy ()
            airfoil.normalize(just_basic=True)              # 
            airfoil.useAsDesign()
            airfoil.set_pathName (self.design_dir)

            self.add_design (airfoil)

        airfoil_copy = airfoil.asCopy_design () 

        return airfoil_copy
    

    def add_design (self, airfoil : Airfoil):
        """ add a airfoil as a copy design to list - save it """

        # save and append copy to list of designs

        iDesign = self.nDesigns
        fileName = f"{self.DESIGN_NAME_BASE}{iDesign:4}{airfoil.Extension}"
        pathFileName = os.path.join (self.design_dir, fileName)

        airfoil_copy = airfoil.asCopy_design (pathFileName=pathFileName)
        airfoil_copy.save   (onlyShapeFile=True)            # save to file - in case of Bezier only .bez

        self.airfoil_designs.append (airfoil_copy)

        # prepare the current  airfoil 

        airfoil.set_fileName (fileName)                     # give a new filename to current
        airfoil.set_isModified (False)                      # avoid being saved for polar generation, there is already a Design


    def get_design_by_name (self, fileName : str):
        """ returns a working copy of Design having fileName (with or without extension)"""

        airfoil = None 
        for a in self.airfoil_designs:
            if a.fileName == fileName or os.path.splitext(a.fileName)[0] == fileName:
                airfoil = a
                break

        if airfoil is None:
            raise RuntimeError (f"Airfoil with fileName {fileName} doesn't exist anymore")
        else: 
            return airfoil.asCopy_design () 


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

        if airfoil_org.name.find ('mod') >= 0:
            i = self.get_i_from_design (airfoil_design)
            if i is not None:
                name = f"{airfoil_org.name}_Design_{i}"
            else: 
                name = f"{airfoil_org.name}_Design"
        else: 
            name = f"{airfoil_org.name}_mod"

        airfoil.set_name (name)
        airfoil.set_pathName (airfoil_org.pathName)
        airfoil.set_fileName_from_name ()

        return airfoil


    def close (self, remove_designs : bool | None = None):
        """ 
        closes Case - remove design directory 
        
        Args: 
            remove_designs: True - remove 
                            False - do not remove 
                            None - remove if only 1 Design 
        
        """

        if remove_designs is None: 
            remove = self.nDesigns < 2 
        else: 
            remove = remove_designs 

        if remove: 
            shutil.rmtree (self.design_dir, ignore_errors=True)



#-------------------------------------------------------------------------------
# Result Reader 
#-------------------------------------------------------------------------------


class Reader_Airfoil_Designs:
    """ 
    Reads all Airfoil .dat or .bez files in a directory   
    """

    def __init__(self, directory : str):

        self._directory = directory if directory else '.'


    def read_all(self, prefix : str = None):
        """ read all airfoils satisfying 'filter'

        Args:
            prefix (str, optional): file filter prefix for airfoils 
        """

        airfoils = []

        if not os.path.isdir (self._directory): airfoils

        # read all file names in dir and filter 

        all_files = os.listdir(self._directory)                             # all files in dir

        dat_files = fnmatch.filter(all_files, f'{prefix}*.dat')             # filter 
        bez_files = fnmatch.filter(all_files, f'{prefix}*.bez')
        hh_files  = fnmatch.filter(all_files, f'{prefix}*.hicks')

        # built pathFileName and sort 

        airfoil_files = dat_files + bez_files + hh_files                
        airfoil_files = [os.path.normpath(os.path.join(self._directory, f)) \
                            for f in airfoil_files if os.path.isfile(os.path.join(self._directory, f))]
        airfoil_files = sorted (airfoil_files, key=str.casefold)

        # create Airfoils from file 

        for file in airfoil_files:
            try: 
                airfoils.append (self._create_airfoil_from_path (file))
            except RuntimeError:
                pass

        return airfoils 




    def _create_airfoil_from_path (self, pathFilename) -> Airfoil:
        """
        Create and return a new airfoil based on pathFilename.
            Return None if the Airfoil couldn't be loaded  
        """

        extension = os.path.splitext(pathFilename)[1]
        if extension == ".bez":
            airfoil = Airfoil_Bezier (pathFileName=pathFilename)
        elif extension == ".hicks":
            airfoil = Airfoil_Hicks_Henne (pathFileName=pathFilename)
        else: 
            airfoil = Airfoil(pathFileName=pathFilename, geometry=GEO_SPLINE)

        airfoil.load()
        airfoil.useAsDesign()

        if airfoil.isLoaded:                      # could have been error in loading
            return airfoil
        else:
            raise RuntimeError (f"Could not load '{pathFilename}'")