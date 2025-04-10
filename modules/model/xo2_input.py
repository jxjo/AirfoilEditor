#!/usr/bin/env pythonnowfinished
# -*- coding: utf-8 -*-
"""  

    handle Xoptfoil2 input file 

    |-- Case_Xo2_Optimize       - a single case, define specs for an optimization 
        |-- Input               - proxy of the Xopfoil2 input file 

                                          
"""

import os
import sys
import textwrap
from pathlib import Path
from typing import TextIO


import f90nml         # fortran namelist parser

# let python find the other modules in the dir of self  
sys.path.append(Path(__file__).parent)
from base.common_utils      import * 
from base.spline            import HicksHenne

from model.polar_set        import * 
from model.airfoil          import Airfoil, GEO_BASIC



#-------------------------------------------------------------------------------
# Input file  
#-------------------------------------------------------------------------------


class Input_File:
    """ 
    Proxy to Xoptfoil2 input file, manage input data of an optimization      
    """

    def __init__(self, fileName: str, workingDir: str = '' ):
        """
        """
        self._workingDir = workingDir           # working dir of optimizer
        self._fileName   = fileName

        self._hasErrors  = False                # errors in input file? 
        self._error_text = None                 # text from error check by worker

        if os.path.exists (self.pathFileName):
            pass
        else: 
            raise ValueError (f"Input file '{self.pathFileName}' doesn't exist")

        # fortran namelist of the input file  

        self._nml_file = None                   # f90nml namelist as dict 

        # single namelists within the input file 

        self._nml_operating_conditions   = Nml_operating_conditions (self)
        self._nml_optimization_options   = Nml_optimization_options (self)
        self._nml_hicks_henne_options    = Nml_hicks_henne_options (self)
        self._nml_bezier_options         = Nml_bezier_options (self)
        self._nml_camb_thick_options     = Nml_camb_thick_options (self)
        self._nml_paneling_options       = Nml_paneling_options (self)
        self._nml_particle_swarm_options = Nml_particle_swarm_options (self)
        self._nml_xfoil_run_options      = Nml_xfoil_run_options (self)
        self._nml_curvature              = Nml_curvature (self)
        self._nml_constraints            = Nml_constraints (self)
        self._nml_geometry_targets       = Nml_geometry_targets (self)

        # definitions from input file 

        self._airfoil_seed   = None                 # seed Airfoil    
        self._opPoints_def   = None                 # op Points definition in input file
        self._polar_defs     = None                 # Polar definitions in input file
        self._geoTargets_def = None                 # geo targets definition in input file


    def reset (self): 
        """ reset namelist, etc so there will be a re-re-read"""
        self._nml_file = None
        self._hasErrors  = False                # errors in input file? 
        self._error_text = None                 # text from error check by worker

        self._airfoil_seed   = None
        self._geoTargets_def = None
        self._polar_defs     = None
        self._opPoints_def   = None


    # ---- Properties -------------------------------------------


    @property
    def workingDir (self): 
        """ working dir of optimizer - absolut"""
        return self._workingDir

    @property
    def name(self):  
        """ name of input file without .inp"""
        return Path(self.fileName).stem

    @property
    def fileName(self):  
        """ name of input file including .inp"""
        return self._fileName


    @property
    def pathFileName (self): 
        """returns the path of the input file rebuild from name """
        return os.path.join (self.workingDir, self.fileName)


    @property
    def pathFileName_relative (self): 
        """returns the relative path of the input 'save' file to working directory """
        return  PathHandler.relPath (self.pathFileName_save, self.workingDir)
    
    @property
    def pathFileName_save (self): 
        """returns the pathFileName of the output file"""

        dir  = os.path.split (self.pathFileName) [0]
        return os.path.join(dir, self.name + '_patched.nml')
        # return self.pathFileName

    @property
    def nml_file (self) -> f90nml.Namelist:
        """ self as f90nml namelist object (dict) """

        if self._nml_file is None: 
            parser = f90nml.Parser()
            parser.global_start_index = 1
            try: 
                self._nml_file = parser.read(self.pathFileName)   # fortran namelist as object  
            except: 
                self._nml_file = None    
                self._hasErrors  = True  
                self._error_text = 'Generell syntax error'            
        return self._nml_file

    @property 
    def nml_operating_conditions (self) -> 'Nml_operating_conditions':
        return self._nml_operating_conditions

    @property 
    def nml_optimization_options (self) -> 'Nml_optimization_options':
        return self._nml_optimization_options

    @property 
    def nml_hicks_henne_options (self) -> 'Nml_hicks_henne_options':
        return self._nml_hicks_henne_options

    @property 
    def nml_bezier_options (self) -> 'Nml_bezier_options':
        return self._nml_bezier_options

    @property 
    def nml_camb_thick_options (self) -> 'Nml_camb_thick_options':
        return self._nml_camb_thick_options

    @property 
    def nml_paneling_options (self) -> 'Nml_paneling_options':
        return self._nml_paneling_options

    @property 
    def particle_swarm_options (self) -> 'Nml_particle_swarm_options':
        return self._particle_swarm_options

    @property 
    def nml_xfoil_run_options (self) -> 'Nml_xfoil_run_options':
        return self._nml_xfoil_run_options

    @property 
    def nml_curvature (self) -> 'Nml_curvature':
        return self._nml_curvature

    @property 
    def nml_constraints (self) -> 'Nml_constraints':
        return self._nml_constraints

    @property 
    def nml_geometry_targets (self) -> 'Nml_geometry_targets':
        return self._nml_geometry_targets


    @property 
    def hasErrors (self) -> bool:
        """ are syntax errors in input file"""
        return self._hasErrors

    @property
    def summary (self) -> list:  
        """ a summary self as list of line items """

        if self.hasErrors:
            summary = textwrap.wrap(self._error_text, width=30, max_lines=5)
        else:
            summary = []
            shape = self.nml_optimization_options.shape_functions
            if shape == 'bezier': 
                top = self.nml_bezier_options.ncp_top
                bot = self.nml_bezier_options.ncp_bot
                line = f"{shape} (top {top}, bot {bot})"
            elif shape == 'hicks_henne':
                top = self.nml_hicks_henne_options.nfunctions_top
                bot = self.nml_hicks_henne_options.nfunctions_bot
                line = f"{shape} (top {top}, bot {bot})"
            else: 
                line = f"{shape}"
            summary.append(line)

            nop  = self.nml_operating_conditions.noppoint
            ngeo = self.nml_geometry_targets.ngeo_targets

            if nop: 
                re_def    = self.nml_operating_conditions.re_default
                ncrit_def = self.nml_xfoil_run_options.ncrit
                line = f"Re default {re_def}, Ncrit {ncrit_def}"
                summary.append(line)

            if nop or ngeo: 
                line = f"{nop} op points"
                if ngeo: 
                    line = f"{line}, {ngeo} geo targets"
                summary.append(line)

            for i, line in enumerate (summary):
                summary[i] = "- " + summary[i]

        return "\n".join (summary)


    @property
    def airfoil_seed (self) -> Airfoil:  
        """ seed airfoil as defined in input file"""

        # special handling - the airfoil file in input couldn't exist - avoid retry all the time 
        if self._airfoil_seed is None: 
            seed_airfoil_fileName  = self.nml_optimization_options.airfoil_file
            if seed_airfoil_fileName:

                try: 
                    airfoil = Airfoil.onFileType (seed_airfoil_fileName, workingDir=self.workingDir, 
                                                geometry=GEO_BASIC)
                    airfoil.load()
                    airfoil.set_usedAs (usedAs.SEED)
                    self._airfoil_seed = airfoil
                except:
                    logger.error (f"{seed_airfoil_fileName} could not be created")
                    pass
        
        return self._airfoil_seed

    
    def set_airfoil_seed (self, airfoil: Airfoil):  
        """ set new seed airfoil in input file and refresh"""
        if airfoil: 
            self.nml_optimization_options.set_airfoil_file(airfoil.pathFileName)
            self.save_nml ()
            self._airfoil_seed = None


    @property
    def opPoint_defs (self) -> 'OpPoint_Definitions':  
        """ op points definition as defined in input file """
        return self.nml_operating_conditions.opPoint_defs


    @property
    def polar_defs (self) -> list [Polar_Definition]: 
        """ polar definitions of input file """
        return self.nml_operating_conditions.polar_defs


    # ---- Methods -------------------------------------------


    def check_file (self): 
        """check self input file with Worker for errors

        Returns:
            returncode: = 0 no errors 
            error_text: the error text from Xoptfoil2
        """

        faulty, text =self.check_content(self.as_text())

        self._hasErrors, self._error_text = faulty, text

        return faulty, text


    def check_additional (self): 
        """check additional sanity of input file 

        Returns:
            faulty: True - there are errors 
            text: error text 
        """

        faulty = False
        text = ""

        # does airfoil exists? 
        airfoil_name = self.nml_optimization_options.airfoil_file
        if not airfoil_name: 
            text = "(seed) airfoil_file is missing"
            faulty = True 

        return faulty, text


    def as_text (self) -> str: 
        "returns the content of input file as text string"

        text = ""
        with open(self.pathFileName,'r') as f:
            text = f.read()
        return text


    def text_save (self, text, pathFileName=None, hasErrors=None): 
        "save text to input file - overwrite existing data"

        if pathFileName is None: pathFileName = self.pathFileName

        with open(pathFileName,'w') as f:
            f.write(text)

        # error state of input file 
        if hasErrors is not None:  self._hasErrors = hasErrors

        # reset f90nml 
        self._nml_file = None 


    def check_content (self, text): 
        """check text being input definition with Worker for errors

        Returns:
            returncode: = 0 no errors 
            error_text: the error text from Xoptfoil2
        """

        # create a temporary input file to check with Worker 
        tmpFile = self.fileName + '.tmp'
        tmpFilePath = os.path.join (self.workingDir, tmpFile)
        self.text_save (text, pathFileName=tmpFilePath)

        # run Worker in 'check-input' mode 
        returncode,error_text = Worker().check_inputFile (inputFile = tmpFilePath)

        if returncode == 0: 
            tmpInput = Input_File (self, workingDir=self.workingDir, fileName=tmpFile) 
            returncode,error_text = tmpInput.check_additional()

        os.remove (tmpFilePath)

        return returncode,error_text


    def save_nml (self):
        """ save current namelist to file """

        # write back list objects to namelist dictionary

        self.opPoint_defs.set_nml() 
        self.nml_geometry_targets.geoTarget_defs.set_nml ()

        # write namelist dictionaries to file 

        with open(self.pathFileName_save, 'w') as nml_stream:

            for namelist_name in self.nml_file:
                try: 
                    nml_class = globals()['Nml_'+ namelist_name]
                except: 
                    nml_class = None
                    logging.error (f"Class for namelist '{namelist_name}' not found")

                if nml_class:
                    nml : Nml_Abstract = nml_class(self)
                    nml.write_to_stream (nml_stream)

    # -----------------------------------------------


    def opPoints_def_as_splined_polar (self):
        """ returns a splines polar based on opPoins_def"""

        polar = Polar_Splined (None, polar_def=self.polar_defs[0])
        polar.set_knots_from_opPoints_def (var.CL, var.CD, self.opPoints_def)
        polar.generate()
        return polar 


    def get_value_in_seed_polar (self, re, ma, ncrit, specVar, specVal, optVar):
        """ 
        Interpolates optVvalue in polar (specVar,optvar) of seed airfoil
        Returns None if polar doesn't exist """
        if self.airfoil_seed is None or self.airfoil_seed.polarSet is None: 
            return None 
        
        polar: Polar
        for polar in self.airfoil_seed.polarSet.polars:
            if polar.re == re and polar.ma == ma and polar.ncrit == ncrit:
                return polar.get_optValue (specVar, specVal, optVar) 
        return None 



#-------------------------------------------------------------------------------
# OpPoint Definition 
#-------------------------------------------------------------------------------


#   if (opt_type /= 'min-drag' .and. &
#       opt_type /= 'max-glide' .and. &
#       opt_type /= 'min-sink' .and. &
#       opt_type /= 'max-lift' .and. &
#       opt_type /= 'target-moment' .and. &
#       opt_type /= 'target-drag' .and. &
#       opt_type /= 'target-lift' .and. &
#       opt_type /= 'target-glide' .and. &
#       opt_type /= 'max-xtr') & 

OPT_TARGET          = "target"
OPT_MIN             = "min"
OPT_MAX             = "max"

XTR                 = "xtr"

OPT_TYPES   = [OPT_TARGET, OPT_MIN, OPT_MAX]
OPT_VARS    = [var.CD, var.CL, var.GLIDE, var.CM, XTR]
OPT_ALLOWED = [(OPT_TARGET,var.CD), 
               (OPT_TARGET,var.GLIDE),
               (OPT_TARGET,var.CL),
               (OPT_TARGET,var.CM),
               (OPT_MIN,   var.CD),
               (OPT_MIN,   var.SINK),
               (OPT_MAX,   var.GLIDE),
               (OPT_MAX,   var.CL)]
SPEC_TYPES  = [var.CL, var.ALPHA]


class OpPoint_Definition:
    """ 
    A single op point for optimization   
    """
    def __init__(self, 
                    myList : 'OpPoint_Definitions', 
                    specVar = var.ALPHA, 
                    specValue = 0.0, 
                    optVar  = var.CD, 
                    optType = OPT_TARGET, 
                    optValue = 0.0, 
                    re = None, 
                    weighting = None):
        """
        New operating point definition

        """

        self._myList     = myList 

        # init values as arguments 
        self._specVar    = specVar              # polar var self is based 
        self._specValue  = specValue            # the value of this variable
        self._optVar     = optVar               # polar var which should be optimized
        self._optType    = optType              # type of optimization 
        self._optValue   = optValue             # an optional value 
        self._weighting  = weighting            # weighting during optimization 
        self._re         = re                   # an individual re number of self
        self._re_type    = polarType.T1         # re type of self 
        self._ma         = None                 # an individual re number of self
        self._ncrit      = None                 # an individiual xfoil ncrit 
        self._flap_angle = None                 # an individiual flap angle        
        self._flap_optimize = False             # optimize this flap angle 

        # set to format values 
        self.set_specValue (specValue)
        self.set_optValue  (optValue)


    def __repr__(self) -> str:
        """ nice print string polarType and Re """
        return f"<{type(self).__name__} {self.labelLongFix}>"

    @property
    def specVar (self): return self._specVar
    def set_specVar (self, aVal): 
        if aVal in SPEC_TYPES: 
            self._specVar = aVal
            if not (self.opt in self.opt_allowed()):
                self.set_opt(self.opt_allowed()[0])


    @property
    def specValue (self): return self._specValue
    def set_specValue (self, aVal):  
        if self.specVar == var.ALPHA:
            self._specValue = round (aVal,2)
        else: 
            self._specValue = round (aVal,3)

    def set_specValue_limited (self, aVal):  
        """ set specValue - assures aVal is between specValues of self neighbours"""
        lower_limit, upper_limit = self.specValue_limits () 
        if lower_limit and aVal and aVal < lower_limit:
            aVal = lower_limit
        if upper_limit and aVal and aVal > upper_limit:
            aVal = upper_limit
        self.set_specValue (aVal) 


    @property
    def opt (self) -> tuple:
        """ returns optType and optvar as tuple like (OPT_TARGET, CD)""" 
        return (self.optType, self.optVar)
    def set_opt (self, aOpt: tuple):  
        if aOpt in OPT_ALLOWED: 
            self._optType = aOpt[0] 
            self._optVar  = aOpt[1] 
    def opt_allowed (self) -> list: 
        """ return list of allowed (optType,optVar) combinations depending on specVar"""
        return [opt for opt in OPT_ALLOWED if opt[1] != self.specVar]  

    @property 
    def opt_asString(self) -> str: 
        return f"{self.opt[0]}-{self.opt[1]}"
    def set_opt_asString (self, opt_string: str): 
        opt = tuple(opt_string.split('-'))
        optType = opt[0]
        optVar  = opt[1] 
        # set optVar and type with an initial value 
        if opt in OPT_ALLOWED and (optType != self._optType or optVar != self._optVar): 
            self._optType = opt[0] 
            self._optVar  = opt[1] 
            self._optValue = self.get_optValue_seed_polar()

    def opt_allowed_asString (self) -> list: 
        """ return allowed optType,optVar combinations depending on specVar"""
        return [f"{opt[0]}-{opt[1]}" for opt in OPT_ALLOWED if opt[1] != self.specVar]  

    @property
    def optType (self): 
        """ type of optimization eg TARGET"""
        return self._optType

    def set_optType (self, aVal):  
        if aVal in OPT_TYPES: 
            self._optType = aVal 

    @property
    def optVar (self): 
        """ variable to be optimized eg CD"""
        return self._optVar

    def set_optVar (self, aVal):  
        if aVal in OPT_VARS: 
            self._optVar = aVal 

    @property
    def optValue (self): 
        """ 
        the target value to optimize - only for optType 'target'
        or - the current value on the seed polar for optType 'min/max'
        """
        if self.optType == OPT_TARGET:
            if self.optValue_isFactor:
                return - self._optValue
            else: 
                return self._optValue
        else: 
            return self.get_optValue_seed_polar()
        
    def set_optValue (self, aVal):  
        if self.optType == OPT_TARGET:
            if self.optValue_isFactor:
                self._optValue = -abs(round(aVal,2))
            else: 
                if self.optVar == var.CD:
                    self._optValue = round (aVal,5)
                else: 
                    self._optValue = round (aVal,3)

    @property
    def optValue_isFactor (self) -> bool: 
        """ optValue (target value) is taken as factor to seed airfoil value"""
        isFactor = False
        # only possible for target-cd and target-glide 
        if self.isTarget_type and not self.optVar == var.CM:
            # a negative target value is taken as factor by Xoptfoil2 
            if self._optValue < 0.0: 
                isFactor = True
        return isFactor 
    
    def set_optValue_isFactor (self, aBool: bool):
        """ is True, optValue (target value) is taken as factor to seed airfoil value """
        # only possible for target-cd and target-glide 
        if self.isTarget_type and not self.optVar == var.CM:
            if aBool: 
                self.set_optValue (-1.0) 
            else: 
                # reset - take inital value from seed airfoil polar
                seedValue = self.get_optValue_seed_polar()
                if seedValue: 
                    self._optValue = seedValue 

    @property
    def re (self): 
        """ the individual reynolds number - normaly the default value is returned"""
        if self._re is None:
            return self._myList.re_default
        else: 
            return self._re
    def set_re (self, aVal):
        if aVal == self._myList.re_default: 
            self._re = None
        elif aVal:  
            aVal = max (1000, aVal)
            aVal = min (2000000, aVal)
            self._re = aVal 
        else: 
            self._re = None

    @property
    def re_asK (self) -> int: 
        """ the individual reynolds number in k - normaly the default value is returned"""
        return int (self.re/1000) if self.re is not None else 0 
    def set_re_asK (self, aVal): self.set_re (aVal * 1000)

    @property
    def re_type (self):
        """ either T1 or T2"""
        return self._re_type
    def set_re_type (self, aType):
        if aType in polarType.values():
            self._re_type = aType

    @property
    def ma (self): 
        """ the individual mach number - normaly a common default value is used"""
        if self._ma is None:
            return self._myList.ma_default
        else: 
            return self._ma
        
    def set_ma (self, aVal):
        if aVal == self._myList.ma_default: 
            self._ma = None
        else: 
            self._ma = aVal

    @property
    def ncrit (self): 
        """ the individual xfoil ncrit - normaly a common default value is used"""
        if self._ncrit is None:
            return self._myList.ncrit
        else: 
            return self._ncrit
        
    def set_ncrit (self, aVal):
        if aVal == self._myList.ncrit: 
            self._ncrit = None
        else: 
            self._ncrit = aVal

    @property
    def weighting (self): 
        """ an individual weighting - default is 1"""
        if self._weighting is None: 
            return 1.0
        else: 
            return self._weighting
        
    def set_weighting (self, aVal): 
        if aVal == 1.0: 
            self._weighting = None
        else: 
            self._weighting = aVal 

    @property
    def has_default_weighting (self) -> bool:
        """ True if op point has default weighting """
        return self._weighting == None

    @property
    def flap_angle (self): 
        """ the individual flap angle """
        return self._flap_angle
    def set_flap_angle (self, aVal : float): 
        self._flap_angle = aVal 
    
    @property
    def flap_optimize (self) -> bool: 
        """ optimize this flap angle flap angle """
        return self._flap_optimize is True
    def set_flap_optimize (self, aVal : bool): 
        self._flap_angle = aVal is True 
    
    #------------

    @property
    def iPoint (self): return self._myList.index (self) + 1


    @property
    def label (self): 
        """ short label like 'target-cd: .00123' or 'Min-cd' """
        return self._get_label()

    def _get_label (self, fix=False): 
        """ short label like 'target-cd: .00123' or 'Min-cd' 
            if fix=True 0-decimals are not cutted """
        if self.optType == OPT_TARGET:
            return f"{self.opt_asString}: {self.optValue_formatted(fix=fix)}"
        else: 
            return f"{self.opt_asString}"

    @property
    def labelLong (self): 
        """ long label including spec like 'cl: 0.2  target-cd: .00123'"""
        return self._get_labelLong()
    @property
    def labelLongFix (self): 
        """ long label including spec like 'cl: 0.2  target-cd: .00123' with fixed decimals"""
        return self._get_labelLong (fix=True)
    
    def _get_labelLong (self, fix=False): 
        """ 
        long label including spec like 'cl: 0.2  target-cd: .00123'
            if fix=True 0-decimals are not cutted
        """
        specText = f"{self.specVar}: {self.specValue_formatted(fix=fix)}  " 
        if self._re: 
            reText = f"  {int(self._re/1000):3d}k" 
        else:
            reText = ''
        if self._ncrit: 
            ncritText = f"  N{int(self._ncrit)}" 
        else:
            ncritText = ''
        return specText + self._get_label (fix=fix) + reText + ncritText


    def specValue_formatted (self, fix=False ):
        """ 
        format specValue according its type like CL or alpha.
            if fix=True the value will have a fixed length, otherwise the 0-decimals are cut"""

        try:
            if self.specVar == var.ALPHA:
                valstr = "%4.2f" % self.specValue
            else :
                valstr = "%4.2f" % self.specValue
        except: 
            valstr = ''

        if not fix: 
            valstr = (f"{valstr}").rstrip('0').rstrip('.')          # remove trailing 0 and .
        return valstr


    def specValue_limits (self) -> tuple:
        """ 
        returns tuple of lower and upper limits of specValue defined by neighbour opPoints
            If there is no neighbour with same specVar return None 
        """

        lower_limit = None 
        upper_limit = None 

        n = len (self._myList) 
        index = self._myList.index(self)

        opPoint_before  = self._myList[index-1] if index > 0 else None
        opPoint_after   = self._myList[index+1] if index < (n-1) else None

        if opPoint_before and opPoint_before.specVar == self.specVar:          
            lower_limit = opPoint_before.specValue * 1.02

        if opPoint_after and opPoint_after.specVar == self.specVar:
            upper_limit = opPoint_after.specValue * 0.98

        return (lower_limit, upper_limit)


    def optValue_formatted (self, altValue : float =None, fix : bool =False ) -> float:
        """ 
        format optVar according its type like CD or GLIDE.
            Value can be alternate for self.optValue  
            if fix=True the value will have a fixed length, otherwise the 0-decimals are cut
        """

        value = altValue if altValue is not None else self.optValue 

        if self.optVar == var.CL:
            valstr = f"{value:4.2f}"

        elif self.optVar == var.CD:
            if self.optValue_isFactor and not altValue:
                valstr = (f"seed*{value:.2f}")              # cd val is factor  
                fix = False                                 # always cut 0   
            else:
                if value >= 0.0:       
                    valstr = (f"{value:7.5f}")[1:]          # remove leading 0 
                else:                                       # altValue can be negative
                    valstr = "-" +(f"{value:7.5f}")[2:]  
                # if valstr == "": valstr = ".0"  

        elif self.optVar == var.GLIDE or self.optVar == var.SINK:
            if self.optValue_isFactor and not altValue:
                valstr = (f"seed*{value:.2f}")              # glide val is factor     
                fix = False                                 # always cut 0   
            else:       
                valstr = (f"{value:4.2f}")[1:]              # remove leading 0 
            valstr = "%4.2f" % value
        elif self.optVar == var.CM:
            valstr = "%5.3f" % value
        else:
            valstr = "%5.3f" % value

        if not fix: 
            valstr = (f"{valstr}").rstrip('0').rstrip('.')          # remove trailing 0 and .
        return valstr



    @property
    def isTarget_type (self) -> bool:
        """ is self based on targets"""
        return self.optType == OPT_TARGET


    def xyValues_for_xyVars (self, xyVar : tuple):
        """ 
        Returns x,y values for either optVar or specVar in x or y
            if xVar and yVar does not fit return None 
            if indirect cd/cl optVars will be calculated to cd and vice versa"""

        y = None
        x = None
        optVar   = self.optVar
        optValue = self.optValue

        # target (opt)value could be a factor to seed airfoil value 
        if self.isTarget_type and self.optValue_isFactor:
            seedValue = self.get_optValue_seed_polar()
            if seedValue : 
                optValue = self.optValue * seedValue
            else:                                       
                return None, None      

        if self.xyVars_are_indirect (xyVar): 
            # recalc cl/cd to cd  - or vice versa 
            if self.optVar == var.GLIDE and self.specVar == var.CL:
                optVar = var.CD 
                optValue = self.specValue / optValue       # cd = cl / glide
            elif self.optVar == var.CD and self.specVar == var.CL:
                optVar = var.GLIDE 
                optValue = self.specValue / optValue       # glide = cl / cd
            else:
                optVar = None

        if optVar is not None: 
            if xyVar[0] == optVar and xyVar[1] == self.specVar:
                x = optValue 
                y = self.specValue
            elif xyVar[1] == optVar and xyVar[0] == self.specVar:
                y = optValue 
                x = self.specValue

        return x, y



    def xyVars_are_indirect (self, xyVar : tuple):
        """ 
        true if xyVar is 'indirect' to self - e.g. (GLIDE,CL) is indirect to (CL,CD) 
        """

        indirect = False 
        specVar = self.specVar
        optVar  = self.optVar

        if (specVar, optVar) == (var.CL, var.CD) or (specVar, optVar) == (var.CD, var.CL): 
            if xyVar == (var.GLIDE, var.CL) or xyVar == (var.CL, var.GLIDE): 
                indirect = True
        elif (specVar, optVar) == (var.CL, var.GLIDE) or (specVar, optVar) == ( var.GLIDE, var.CL): 
            if xyVar == (var.CD, var.CL) or xyVar == (var.CL, var.CD): 
                indirect = True
        return indirect 


    def xyVars_as_spec (self, xyVar : tuple, xyValues : tuple = None):
        """ 
        returns specVar and optVar of the tuple xyVar which could be flipped. 
            if xyVar does not find return None  
        if xyValues are provided, these are returned as specValue and optValue """

        specVar   = None
        optVar    = None
        optValue  = None
        specValue = None

        xVar, yVar     = xyVar[0], xyVar[1]
        xValue, yValue = xyValues [0], xyValues [1]

        if (xVar == self.specVar and yVar == self.optVar):
            specVar = xVar
            optVar  = yVar 
            if xyValues is not None:
                specValue = xValue
                optValue  = yValue
        elif (yVar == self.specVar and xVar == self.optVar):        # flip x and y
            specVar = yVar
            optVar  = xVar
            if xyValues is not None:
                specValue = yValue
                optValue  = xValue

        return specVar, optVar, specValue, optValue
        

    def set_xyValues_for_xyVars (self,xyVar : tuple, xyValues : tuple):
        """ 
        sets x,y values for either optVar or specVar in x or y
            if xVar and yVar does not fit return None 
            if indirect cd/cl optVars will be calculated to cd and vice versa"""

        if self.xyVars_are_indirect (xyVar): 
            # recalc cl/cd to cd  - or vice versa 
            xVar, yVar     = xyVar [0], xyVar[1]
            xValue, yValue = xyValues [0], xyValues [1]

            if xVar == var.GLIDE and yVar == var.CL:
                xValue = yValue / xValue                    # cd = cl / glide
                xVar   = var.CD
            elif xVar == var.CL and yVar == var.GLIDE:
                yValue = xValue / yValue                    # cd = cl / glide
                yVar   = var.CD
            elif xVar == var.CD and yVar == var.CL:
                xValue = yValue / xValue                    # glide = cl / cd
                xVar   = var.GLIDE 
            elif xVar == var.CL and yVar == var.CD:
                yValue = xValue / yValue                    # glide = cl / cd
                yVar   = var.GLIDE 
            else:
                raise ValueError (f"{self} xyVar: {xyVar} do not fit into myself")

            xyVar = xVar, yVar 
            xyValues = xValue, yValue 

        # handle flipped x any y

        specVar, optVar, specValue, optValue = self.xyVars_as_spec (xyVar, xyValues)

        if specVar is None or specValue is None: return         # xy doesn't fit 

        # target (opt)value could be a factor to seed airfoil value 
        if self.isTarget_type and self.optValue_isFactor:
            seedValue = self.get_optValue_seed_polar()
            if seedValue : 
                optValue = optValue / seedValue
            else: 
                optValue = None 




        # do not set if seed couldn't be calculated
        if optValue is not None: 
            self.set_optValue  (optValue) 
            self.set_specValue_limited (specValue)      # check neighbour values 

        return 


    def get_optValue_seed_polar(self):
        """ 
        returns the value for optValue interpolated from seed polar
        If seed polar is not available etc. returns None"""
    
        raise RuntimeError ("to be implemented")
        # optVal =  self._input_file.get_value_in_seed_polar (self.re, self.ma, self.ncrit,
        #                                              self.specVar, self.specValue, self.optVar)
        # # not allow Glide < 0 - would confuse factor which detects negative value ...
        # if self.optVar == var.GLIDE and  optVal is not None and optVal < 0.0:
        #     optVal = 0.0 


    def delete_me (self):
        """ remove self from list"""

        self._myList.remove (self) 
        self._myList = None 



class OpPoint_Definitions (list [OpPoint_Definition]):
    """ 
    container (list) for operating point definitions of Input 
    
        |-- Case
            |-- Input_File
                |-- OpPoint_Definitions
                    |-- OpPoint_Definition

    """

    def __init__ (self, nml : 'Nml_operating_conditions', input_file: 'Input_File'):
        super().__init__ ([])

        self._nml = nml 
        self._input_file = input_file

        # read self from namelist 

        op_points = nml._get ('op_point', []) 
        npoints = len(op_points)
 
        if npoints == 0: return 

        # f90nml delivers op point values as list 

        optimization_types  = nml._get('optimization_type')
        target_values       = nml._get('target_value',   default=[None] * npoints)
        weightings          = nml._get('weighting',      default=[1.0] * npoints)
        reynolds            = nml._get('reynolds',       default=[None] * npoints)        
        machs               = nml._get('mach',           default=[None] * npoints)    
        ncrits              = nml._get('ncrit_pt',       default=[None] * npoints)
        op_modes            = nml._get('op_mode',        default=['spec_cl'] * npoints)
        flap_angles         = nml._get('flap_angle',     default=[None] * npoints)
        flap_optimizes      = nml._get('flap_optimizes', default=[False] * npoints)

        # get default polar type 

        if self._nml.re_default_as_resqrtcl: 
            type_default = polarType.T2
        else: 
            type_default = polarType.T1

        # collect opPoint definitions

        for iop in range (npoints):

            op_def = OpPoint_Definition(self)

            if op_modes[iop] == "spec-al":
                op_def.set_specVar (var.ALPHA)
            else: 
                op_def.set_specVar (var.CL)

            op_def.set_specValue    (op_points[iop])
            op_def.set_re           (reynolds[iop])
            op_def.set_ma           (machs[iop])
            op_def.set_ncrit        (ncrits[iop])
            op_def.set_weighting    (weightings[iop])
            op_def.set_re_type      (type_default)
            op_def.set_flap_angle   (flap_angles[iop])
            op_def.set_flap_optimize(flap_optimizes[iop])

            opt = optimization_types[iop]
            if opt == 'min-drag':
                op_def.set_optType (OPT_MIN)
                op_def.set_optVar  (var.CD)
            elif opt == 'max-glide':
                op_def.set_optType (OPT_MAX)
                op_def.set_optVar  (var.GLIDE)
            elif opt == 'max-lift':
                op_def.set_optType (OPT_MAX)
                op_def.set_optVar  (var.CL)
            elif opt == 'target-moment':
                op_def.set_optType (OPT_TARGET)
                op_def.set_optVar  (var.CM)
            elif opt == 'target-drag':
                op_def.set_optType (OPT_TARGET)
                op_def.set_optVar  (var.CD)
            elif opt == 'target-lift':
                op_def.set_optType (OPT_TARGET)
                op_def.set_optVar  (var.CL)
            elif opt == 'target-glide':
                op_def.set_optType (OPT_TARGET)
                op_def.set_optVar  (var.GLIDE)
            elif opt == 'max-xtr':
                op_def.set_optType (OPT_MAX)
                op_def.set_optVar  (var.XTRT)
            else:
                raise ValueError ("Type '%s' of Operating point %d not known. Using default" %(opt, iop))

            op_def.set_optValue (target_values[iop])

            self.append (op_def) 



    def set_nml (self)  :
        """ set op points definition back to namelist """

        op_points     = []
        optimization_types = []
        target_values = []
        weightings    = []
        reynolds      = []        
        machs         = []   
        ncrits        = []
        op_modes      = []
        flap_angles   = []
        flap_optimizes= []


        for opPoint_def in self:

            if opPoint_def.specVar == var.ALPHA:
                op_modes.append ("spec-al")
            else:
                op_modes.append (None)                  # spec-cl is default value 

            op_points.append (opPoint_def.specValue)

            # use raw value - so default values won't be in input file 
             
            target_values.append (opPoint_def._optValue)             
            reynolds.append (opPoint_def._re)
            machs.append (opPoint_def._ma)
            ncrits.append (opPoint_def._ncrit)
            weightings.append (opPoint_def._weighting)
            
            flap_angles.append (opPoint_def._flap_angle)
            flap_optimizes.append (opPoint_def._flap_optimize)

            if opPoint_def.optType == OPT_MIN and opPoint_def.optVar == var.CD:
                opt = 'min-drag'
            elif opPoint_def.optType == OPT_MAX and opPoint_def.optVar == var.GLIDE:
                opt = 'max-glide'
            elif opPoint_def.optType == OPT_MAX and opPoint_def.optVar == var.CL:
                opt = 'max-lift'
            elif opPoint_def.optType == OPT_TARGET and opPoint_def.optVar == var.CM:
                opt = 'target-moment'
            elif opPoint_def.optType == OPT_TARGET and opPoint_def.optVar == var.CD:
                opt = 'target-drag'
            elif opPoint_def.optType == OPT_TARGET and opPoint_def.optVar == var.CL:
                opt = 'target-lift'
            elif opPoint_def.optType == OPT_TARGET and opPoint_def.optVar == var.GLIDE:
                opt = 'target-glide'
            elif opPoint_def.optType == OPT_MAX and opPoint_def.optVar == var.XTRT:
                opt = 'max-xtr'
            else:
                logging.debug ("Unknown optType, optVar combination - using default optimization type")
                opt = 'min-drag'
                
            optimization_types.append(opt)

        self._nml._set ('noppoint', clip (len(self), 0, 50)) 

        # f90nml wants op point values as list 

        self._nml._set ('op_mode', op_modes)
        self._nml._set ('op_point', op_points)
        self._nml._set ('optimization_type', optimization_types)
        self._nml._set ('target_value', target_values)
        self._nml._set ('weighting', weightings)
        self._nml._set ('reynolds', reynolds)
        self._nml._set ('mach', machs)
        self._nml._set ('ncrit_pt', ncrits)
        self._nml._set ('flap_angle', flap_angles)
        self._nml._set ('flap_optimize', flap_optimizes)


    def _sort (self):
        """ sorts self with ascending specValue """

        from operator import attrgetter
        self.sort(key=attrgetter('specValue'))  
        self.sort(key=attrgetter('specVar'), reverse=True)  


    @property
    def ncrit (self):  
        return self._input_file.nml_xfoil_run_options.ncrit

    @property
    def re_default (self):  
        return self._nml.re_default

    @property
    def ma_default (self):  
        return self._nml.mach_default
    

    def create_after (self, index = 0):
        """
        Create and add a new opPoint_def after index with
            a best fit of specVar, specVal
        """

        opPoint_before : OpPoint_Definition = None 
        opPoint_after  : OpPoint_Definition = None 
        
        ilast = len (self) - 1

        # get neighbours 
        if index <= ilast:
            opPoint_after = self [index]

        if index <= ilast and index > 0:    
            opPoint_before = self [index-1]
        elif index > ilast and ilast >= 0 : 
            opPoint_before = self [-1]

        if opPoint_before:
            specVar = opPoint_before.specVar
            optVar  = opPoint_before.optVar
            optType = opPoint_before.optType
        elif opPoint_after: 
            specVar = opPoint_after.specVar
            optVar  = opPoint_after.optVar
            optType = opPoint_after.optType
        else: 
            specVar = var.CL 
            optVar  = var.CD
            optType = OPT_MIN

        # try to find best specValue from neighbours 
        if opPoint_before and opPoint_after and (opPoint_before.specVar == opPoint_after.specVar): 
            specVal = round ((opPoint_before.specValue + opPoint_after.specValue) / 2, 2) 
        elif opPoint_before: 
            if opPoint_before.specVar == var.CL: 
               specVal = opPoint_before.specValue + 0.1
            else: 
               specVal = opPoint_before.specValue + 1
        elif opPoint_after: 
            if opPoint_after.specVar == var.CL: 
               specVal = opPoint_after.specValue - 0.1
            else: 
               specVal = opPoint_after.specValue - 1
        else: 
            specVal = 0.1    

        # optValue equals seed 
        if optType == OPT_TARGET:
            if optVar == var.CM: 
                optValue = 0.0                  # cm doesn't support '-1' (equals seed) 
            else: 
                optValue = -1.0 
        else: 
            optValue = None 
    
        # return new instance 

        new_opPoint_def = OpPoint_Definition (self, specVar=specVar, specValue=specVal, optType=optType,
                                                    optVar = optVar, optValue = optValue)
        self.insert (index, new_opPoint_def)


    def create_in_xyVars (self, xyVars, x, y, re=None):
        """
        Alternate constructor for new opPoint definition coming from diagram with 
            xyVars like CD or CL with corresponding x,y values 
        New opPoint_def is added to self

        Args:
            xyVars: tuple of polar variables like (CD,CL)
            x,y: the values of xyVars 
            re:  a guess for the reynolds nummber 
        Returns:
            new OpPoint_Definition instance: 
        """

        xVar, yVar = xyVars
        specVar, optVar = None, None

        if not (xVar in var.values() and yVar in var.values()):
            raise ValueError (f"'{xyVars}' are not supported for opPoint definition")
        
        # try to find what is 'spec' and what is 'opt'
        if xVar in SPEC_TYPES: 
            specVar = xVar
            specValue = x
            if yVar in OPT_VARS:
                optVar = yVar 
                optValue = y
        elif yVar in SPEC_TYPES: 
            specVar = yVar
            specValue = y
            if xVar in OPT_VARS:
                optVar = xVar 
                optValue = x

        if specVar and optVar:
            new_opPoint_def = OpPoint_Definition (self, specVar=specVar, specValue=specValue, 
                                                        optVar = optVar, optValue = optValue)
            self.add (new_opPoint_def)
            self._sort ()
            return new_opPoint_def
        else: 
            return None 


    def add (self, aOpPoint_def : 'OpPoint_Definition'):
        """ add (a new) opPoint definition and resort self"""

        self.append (aOpPoint_def) 
        self._sort ()



#-------------------------------------------------------------------------------
# Geometry target Definition 
#-------------------------------------------------------------------------------


THICKNESS           = "Thickness"
CAMBER              = "Camber"
CURVATURE_LE        = "tbd"             #todo

GEO_OPT_VARS    = [THICKNESS, CAMBER]

class GeoTarget_Definition:
    """ 
    A geometry target definition for optimization   
    """

    def __init__(self, optVar  = None, optValue = 0.0, weighting = None):
        """
        Geometry target definition 
        """
        self._optVar     = optVar                   # either Thickness or Camber
        self._optValue   = optValue                 # target value 
        self._weighting  = weighting                # weighting during optimization 
        self._preset_to_target = False


    @property
    def optType (self): 
        """ geometry is always 'target'"""
        return OPT_TARGET
    
    @property
    def optVar (self): 
        return self._optVar
    def set_optVar (self, aVal):  
        # allow all ..   if aVal in GEO_OPT_VARS: 
        self._optVar = aVal 

    @property
    def optValue (self): 
        """ the target value to optimize """
        return self._optValue
    def set_optValue (self, aVal):  
        self._optValue = aVal

    @property
    def optValue_in_perc (self) -> float:
        """ target value in percent"""
        if self.optValue_is_numeric:
            return round((self.optValue * 100),2)
        else:
            return self.optValue
        
    def set_optValue_in_perc (self, aVal):  
        if self.optValue_is_numeric:
            self.set_optValue (aVal/100)
        else:
            self.set_optValue (aVal/100)

    @property
    def optValue_is_numeric (self) -> bool:
        """ true if optValue is numeric like optVar THICKNESS""" 
        return self.optVar in [THICKNESS, CAMBER]


    @property
    def weighting (self): 
        """ an individual weighting - default is 1"""
        if self._weighting is None: 
            return 1.0
        else: 
            return self._weighting   
    def set_weighting (self, aVal): 
        if aVal == 1.0: 
            self._weighting = None
        else: 
            self._weighting = aVal 

    @property
    def preset_to_target (self) -> bool: 
        """ preset airfoil to target value """
        return self._preset_to_target is True
    def set_preset_to_target (self, aBool : bool): 
        self._preset_to_target = aBool is True

    @property
    def label (self): 
        """ short label """
        return f"{self.optVar}:  {self.optValue_in_perc:.2f}%"



class GeoTarget_Definitions (list [GeoTarget_Definition]):
    """ 
    container (list) for geometry target definitions of Input 
    
        |-- Case
            |-- Input_File
                |-- GeoTarget_Definitions
                    |-- GeoTarget_Definition

    """

    def __init__ (self, nml : 'Nml_geometry_targets'):
        super().__init__ ([])

        self._nml = nml 

        # read self from namelist 

        target_types = self._nml._get('target_type', []) 
        ngeo = len(target_types)
 
        if ngeo == 0: return self

        target_values   = self._nml._get('target_value',        default=[None] * ngeo)
        weightings      = self._nml._get('weighting',           default=[1.0] * ngeo)
        presets         = self._nml._get('preset_to_target',    default=[False] * ngeo)

        for igeo in range (ngeo):

            geo_def = GeoTarget_Definition ()

            geo_def.set_optVar    (target_types [igeo])
            geo_def.set_optValue  (target_values [igeo])
            geo_def.set_weighting (weightings [igeo])
            geo_def.set_preset_to_target (presets [igeo])
            
            self.append (geo_def) 

        return 


    def set_nml (self)  :
        """ set op geo targets definition back to namelist """

        target_types  = []
        target_values = []
        weightings    = []
        presets       = []

        for geo_def in self:

            target_types.append (geo_def.optVar)
            target_values.append (geo_def.optValue)
            weightings.append (geo_def._weighting)                                          # raw value (None for default)
            presets.append (geo_def.preset_to_target if geo_def.preset_to_target else None) # False is default

        self._nml._set ('ngeo_targets', len(self)) 

        # f90nml wants op point values as list 
        self._nml._set ('target_type',       target_types)
        self._nml._set ('target_value',      target_values)
        self._nml._set ('weighting',         weightings)
        self._nml._set ('preset_to_target',  presets)


    def create_new (self):
        """
        Alternate constructor for new geoTarget definition in self.
        A new GeoTarget_Definition with a not used optVar is returned 

        If all possible optVars are already in used return None
        """
 
        # collect optVars already used 
        optVars_defined = []
        for geoTarget_def in self:
            optVars_defined.append(geoTarget_def.optVar)

        # find an optVar which isn't already used
        for optVar in GEO_OPT_VARS:
            if not optVar in optVars_defined: 
                if optVar == THICKNESS:
                    optVal = 0.1
                elif optVar == CAMBER:
                    optVal = 0.02
                else: 
                    optVal = None 

                self.append(GeoTarget_Definition (optVar = optVar, optValue = optVal))
                return self[-1]
            
        return None 


#-------------------------------------------------------------------------------
# Namelists within Xoptfoil2 Input file  
#-------------------------------------------------------------------------------


class Nml_Abstract:
    """
    Abstract superclass

    Represents a single Fortran namelist in the Xoptfoil2 input file" 
    """

    name = "nml_abstract"

    INDENT = '  '                               #  spaces to indent when writing vars to file

    def __init__(self, input_file: Input_File):

        self._input_file = input_file 
        self._workingDir = input_file.workingDir


    @property
    def nml (self) -> dict:
        """ the namelist as dict self represents""" 

        try:
            return self._input_file.nml_file[self.name]
        except:                                     # create new, empty namelist
            self._input_file.nml_file [self.name] = {}
            return self._input_file.nml_file[self.name]


    def _get (self, key: str, default=None):
        """ returns a namelist entry in self having 'key'"""

        try: 
            entry = self.nml[key]
        except: 
            entry = default

        # f90nml gets arrays only up to highest index defined in namelist
        # --> fill up with default values
        if isinstance (entry, list) and isinstance(default, list):
            entry : list
            if len(entry) < len(default): 
                entry.extend (default [(len(entry)-len(default)):])

        return entry    


    def _set (self, key: str, aVal): 
        """ sets a namelist entry in self having key"""

        toDict (self.nml, key, aVal)

    
    def write_to_stream (self, aStream: TextIO):
        """ write the variables of self to sStream"""

        if self.nml:                                    # only nml with data 

            aStream.write (f"&{self.name}\n")           # &namelist

            for varName in self.nml:                    # write all simple variables var = 123.3
                value = self._get (varName, default=None)
                if not isinstance(value, list) : 
                    self._write_entry (aStream, varName, value)

            self._write_arrays  (aStream)               #   op_point(1) = 0.2

            aStream.write (f"/\n")                      # /
            aStream.write (f"\n")                       # blank line at end 


    def _write_entry (self, aStream : TextIO, varName, value):
        """ write a single variables to stream"""

        if value is not None  : 
            if   type(value) == type(True) and value: 
                valString = ".true."
            elif type(value) == type(True) and not value: 
                valString = ".false."
            elif isinstance(value, str):
                valString = f"'{value}'"
            else: 
                valString = str(value)

            aStream .write (f"{self.INDENT}{varName} = {valString}\n")


    def _write_arrays (self, aStream : TextIO):
        """ write arrays to stream"""
        # must be implemented by subClass
        pass

    
    def write_to_stream (self, aStream: TextIO):
        """ write the variables of self to sStream"""

        if self.nml:                                    # only nml with data 

            aStream.write (f"&{self.name}\n")           # &namelist

            for varName in self.nml:                    # write all simple variables var = 123.3
                value = self._get (varName, default=None)
                if not isinstance(value, list) : 
                    self._write_entry (aStream, varName, value)

            self._write_arrays  (aStream)               #   op_point(1) = 0.2

            aStream.write (f"/\n")                      # /
            aStream.write (f"\n")                       # blank line at end 


# --------- Concrete subclasses ------------------------------------


class Nml_optimization_options (Nml_Abstract):
    """ 
    &optimization_options                          ! main control of optimization
    airfoil_file     = '<mySeedAirfoil>'           ! either '.dat', '.bez' or '.hicks' file 
    shape_functions  = 'hicks-henne'               ! either 'hicks-henne', 'bezier' or 'camb-thick' 
    cpu_threads      = -1                          ! no of cpu threads or -n less than available 
    show_details     = .true.                      ! show details of actions and results 
    """

    name = "optimization_options"

    HICKS_HENNE = 'hicks-henne'
    BEZIER      = 'bezier'
    CAMB_THICK  = 'camb-thick'

    SHAPE_FUNCTIONS = [HICKS_HENNE, BEZIER, CAMB_THICK]
  
    @property
    def airfoil_file (self) -> str:             return self._get ('airfoil_file', default=None) 
    def set_airfoil_file (self, aStr : str):    self._set ('airfoil_file', PathHandler.relPath (aStr, self._workingDir)) 

    @property 
    def show_details (self) -> bool:            return self._get ('show_details', default=True)
    def set_show_details (self, aVal : bool):   self._set('show_details', aVal is True)

    @property 
    def cpu_threads (self) -> int:              return self._get ('cpu_threads', default=-1)
    def set_cpu_threads (self, aVal : int):     self._set('cpu_threads', aVal is True)

    @property 
    def shape_functions (self) -> str: 
        shape = self._get ('shape_functions', default=self.HICKS_HENNE)
        return shape  if shape in self.SHAPE_FUNCTIONS else self.HICKS_HENNE
    def set_shape_functions (self, aShape):     
        if aShape in self.SHAPE_FUNCTIONS:  
            self._set('shape_functions', aShape)
        


class Nml_hicks_henne_options (Nml_Abstract):
    """ 
    &hicks_henne_options                               ! options for shape_function 'hicks-henne'
        nfunctions_top   = 3                           ! hicks-henne functions on top side              
        nfunctions_bot   = 3                           ! hicks-henne functions on bot side
        initial_perturb  = 0.1                         ! max. perturb when creating initial designs 
        smooth_seed      = .false.                     ! smooth (match bezier) of seed airfoil prior to optimization
    """
    name = "hicks_henne_options"

    @property
    def nfunctions_top (self) -> int:           return self._get ('nfunctions_top', default=3) 
    def set_nfunctions_top (self, aVal : int):  self._set ('nfunctions_top',  clip (int(aVal), 0, 10)) 

    @property
    def nfunctions_bot (self) -> int:           return self._get ('nfunctions_bot', default=3) 
    def set_nfunctions_bot (self, aVal : int):  self._set ('nfunctions_bot',  clip (int(aVal), 0, 10)) 

    @property
    def initial_perturb (self) -> float:        return self._get ('initial_perturb', default=0.1) 
    def set_initial_perturb (self, aVal:float): self._set ('initial_perturb', clip (aVal, 0.01, 0.5)) 

    @property
    def smooth_seed (self) -> bool:             return self._get ('smooth_seed', default=False) 
    def set_smooth_seed (self, aVal : bool):    self._set('initial_perturb', aVal is True) 



class Nml_bezier_options (Nml_Abstract):
    """ 
    &bezier_options                                    ! options for shape_function 'bezier'
        ncp_top          = 5                           ! no of bezier control points on top side              
        ncp_bot          = 5                           ! no of bezier control points on bot side
        initial_perturb  = 0.1                         ! max. perturb when creating initial designs    
    """
    name = "bezier_options"

    @property
    def ncp_top (self) -> int:                  return self._get ('ncp_top', default=5) 
    def set_ncp_top (self, aVal : int):         self._set ('ncp_top', clip (int(aVal), 3, 10) )

    @property
    def ncp_bot (self) -> int:                  return self._get ('ncp_bot', default=5) 
    def set_ncp_bot (self, aVal : int):         self._set ('ncp_bot', clip (int(aVal), 3, 10) )

    @property
    def initial_perturb (self) -> float:        return self._get ('initial_perturb', default=0.1) 
    def set_initial_perturb (self, aVal:float): self._set ('initial_perturb', clip (aVal, 0.01, 0.5)) 



class Nml_camb_thick_options (Nml_Abstract):
    """ 
    &camb_thick_options                                ! options for shape_function 'camb_thick'
        thickness        = .true.                      ! optimize thickness 
        thickness_pos    = .true.                      ! optimize max. thickness position
        camber           = .true.                      ! optimize camber
        camber_pos       = .true.                      ! optimize max. camber position
        le_radius        = .true.                      ! optimize leading edge radius
        le_radius_blend  = .true.                      ! optimize blending distance for le radius change 
        initial_perturb  = 0.1d0                       ! max. perturb when creating initial designs     
    """
    name = "camb_thick_options"

    @property
    def thickness (self) -> bool:               return self._get('thickness', default=True) 
    def set_thickness (self, aVal : bool):      self._set('thickness', aVal is True) 

    @property
    def thickness_pos (self) -> bool:           return self._get('thickness_pos', default=True) 
    def set_thickness_pos (self, aVal : bool):  self._set('thickness_pos', aVal is True) 

    @property
    def camber (self) -> bool:                  return self._get('camber', default=True) 
    def set_camber (self, aVal : bool):         self._set('camber', aVal is True) 

    @property
    def camber_pos (self) -> bool:              return self._get('camber_pos', default=True) 
    def set_camber_pos (self, aVal : bool):     self._set('camber_pos', aVal is True) 

    @property
    def le_radius (self) -> bool:               return self._get('le_radius', default=True) 
    def set_le_radius (self, aVal : bool):      self._set('le_radius', aVal is True) 

    @property
    def le_radius_blend (self) -> bool:         return self._get('le_radius_blend', default=True) 
    def set_le_radius_blend (self, aVal : bool):self._set ('le_radius_blend', aVal is True) 

    @property
    def initial_perturb(self) -> float:         return self._get('initial_perturb', default=0.1) 
    def set_initial_perturb (self, aVal:float): self._set ('initial_perturb', clip(aVal, 0.01, 0.5)) 



class Nml_operating_conditions (Nml_Abstract):
    """ 
    &operating_conditions

        dynamic_weighting      = .true.                ! activate dynamic weighting during optimization
        allow_improved_target  = .true.                ! allow result to be better than target value
        
        re_default             = 400000                ! use this Reynolds number for operating points
        re_default_as_resqrtcl = .false.               ! interpret re number as type 2 (Re*sqrt(cl)) 
        mach_default           = 0.0                   ! use this Mach number for operating points 
        
        use_flap               = .false.               ! activate flap setting or optimization
        x_flap                 = 0.75                  ! chord position of flap 
        y_flap                 = 0.0                   ! vertical hinge position 
        y_flap_spec            = 'y/c'                 ! ... in chord unit or 'y/t' relative to height
        flap_angle_default     = 0.0                   ! default flap angle for all op points

        noppoint         = 0                           ! no of operating points  

        op_mode(1)       = 'spec_cl'                   ! op either 'spec_cl' or 'spec_al' based             
        op_point(1)      = 0.0                         ! value of either cl or alpha         
        optimization_type(1) = 'target-drag'           ! 'min-drag', 'max-glide', 'min-sink', 
                                                       ! 'max-lift', 'max-xtr', 
                                                       ! 'target-drag', 'target-glide', 'target-moment', 
        target_value(1)  = 0.0                         ! target value if type = 'target-...'              
        weighting(1)     = 1.0                         ! weighting during optimization 
        reynolds(1)      =                             ! individual re number of op (default: re_default) 
        mach(1)          =                             ! individual mach number of op (default: mach_default) 
        ncrit_pt(1)      =                             ! individual ncrit of op  

        flap_angle(1)    =                             ! individual flap angle (default: flap_angle_default)
        flap_optimize(1) = .false.                     ! optimize this flap angle         
    """

    name = "operating_conditions"

    def __init__ (self, *args):

        self._opPoint_defs = None 
        super().__init__(*args)


    @override
    def _write_arrays (self, aStream : TextIO):
        """ write arrays to stream"""

        # write op_points as single value like 
        # op_mode(1)       = 'spec_cl'                    
        # op_point(1)      = 0.0                           
        # optimization_type(1) = 'target-drag'        

        op_points = self._get('op_point', [])        

        noneArr = [None] * len(op_points)                       # len op_points is master

        optimization_types = self._get('optimization_type', noneArr)
        target_values = self._get('target_value', noneArr)
        weightings    = self._get('weighting', noneArr)
        reynolds      = self._get('reynolds', noneArr)        
        machs         = self._get('mach', noneArr)    
        ncrits        = self._get('ncrit_pt', noneArr)
        op_modes      = self._get('op_mode', noneArr)

        for i, op_point in enumerate (op_points):

            aStream .write (f"\n")                      # blank line 

            self._write_entry (aStream, f"op_mode({i+1})", op_modes[i])
            self._write_entry (aStream, f"op_point({i+1})", op_point)
            self._write_entry (aStream, f"optimization_type({i+1})", optimization_types[i])
            self._write_entry (aStream, f"target_value({i+1})", target_values[i])
            self._write_entry (aStream, f"weighting({i+1})", weightings[i])
            self._write_entry (aStream, f"reynolds({i+1})", reynolds[i])
            self._write_entry (aStream, f"mach({i+1})", machs[i])
            self._write_entry (aStream, f"ncrit({i+1})", ncrits[i])


    @property
    def re_default (self) -> float:             return self._get('re_default', default=100000)
    def set_re_default (self, aVal):            self._set ('re_default', clip (aVal, 1000, 10000000)) 

    @property
    def re_default_asK (self) -> int:           return int (self.re_default/1000) 
    def set_re_default_asK (self, aVal):        self.set_re_default (aVal * 1000)

    @property
    def mach_default (self) -> float:           return self._get('mach_default', default=0) 
    def set_mach_default (self, aVal):          self._set ('mach_default', clip (aVal, 0, 10)) 

    @property 
    def re_default_as_resqrtcl (self) -> bool:  return self._get ('re_default_as_resqrtcl', default=False)
    def set_re_default_as_resqrtcl (self, aVal : bool): self._set ('re_default_as_resqrtcl', aVal is True)

    @property 
    def dynamic_weighting (self) -> bool:       return self._get('dynamic_weighting', default=True)
    def set_dynamic_weighting (self, aVal:bool):self._set('dynamic_weighting', aVal is True)

    @property 
    def allow_improved_target (self) -> bool:   return self._get('allow_improved_target', default=True)
    def set_allow_improved_target (self, aVal : bool): self._set('allow_improved_target', aVal is True)

    @property 
    def use_flap (self) -> bool:                return self._get('use_flap', default=False)
    def set_use_flap (self, aVal : bool):       self._set('use_flap', aVal is True)

    @property
    def x_flap (self) -> float:                 return self._get('x_flap', default=0.75)
    def set_x_flap (self, aVal):                self._set ('x_flap', clip (aVal, 0.0, 1.0)) 

    @property
    def y_flap (self) -> float:                 return self._get('y_flap', default=0.0)
    def set_y_flap (self, aVal):                self._set ('y_flap', clip (aVal, 0.0, 1.0)) 

    @property
    def flap_angle_default (self) -> float:     return self._get('flap_angle_default', default=0.0)
    def set_flap_angle_default (self, aVal):    self._set ('flap_angle_default', clip (aVal, -45.0, 45.0)) 

    @property 
    def y_flap_of_thickness (self) -> bool:     
        """ is y position value as fraction from thickness"""
        entry = self._get('y_flap_spec', default='y/t')
        return True if entry == 'y/t' else False    
    def set_y_flap_of_thickness (self, aVal : bool): self._set('y_flap_spec', 'y/t' if aVal else 'y/c')

    @property
    def noppoint (self) -> int:                 return self._get('noppoint', default=0)
    def set_noppoint (self, aVal):              self._set ('noppoint', clip (int(aVal), 0, 50)) 


    @property
    def opPoint_defs (self) -> OpPoint_Definitions :
        """ 
        op point definitions as list of OpPoint_Definition 
        ! set is done via OpPoint_Definitions " 
        """

        if self._opPoint_defs is None: 
            self._opPoint_defs = OpPoint_Definitions(self, self._input_file)
        return self._opPoint_defs

    @property
    def polar_defs (self) -> list[Polar_Definition]: 
        """ the polar definitions defined within self"""

        polar_defs_dict = {}

        # implicit polars by operating points 
         
        for opPoint_def in  self.opPoint_defs: 
            # build unique key to detect dublicates
            key = str([opPoint_def.re, opPoint_def.ma, opPoint_def.ncrit, opPoint_def.re_type])

            polar_def : Polar_Definition = polar_defs_dict.get (key, Polar_Definition())
            polar_def.set_ncrit (opPoint_def.ncrit)
            polar_def.set_autoRange (True)           # auto range is default 
            polar_def.set_re (opPoint_def.re)
            polar_def.set_type (opPoint_def.re_type)
            polar_def.set_ma (opPoint_def.ma)
            polar_defs_dict[key] = polar_def

        return list(polar_defs_dict.values())



class Nml_paneling_options (Nml_Abstract):
    """ 
    &paneling_options                                  ! options for re-paneling before optimization 
        npan             = 160                         ! no of panels of airfoil
        npoint           = 161                         ! alternative: number of coordinate points
        le_bunch         = 0.86                        ! panel bunch at leading edge  - 0..1 (max) 
        te_bunch         = 0.6                         ! panel bunch at trailing edge - 0..1 (max) 
    """
    name = "paneling_options"

    @property
    def npoint (self) -> int:                   return self._get('npoint', default=161) 
    def set_npoint (self, aVal : int):          self._set ('npoint', clip (int(aVal), 80, 300)) 
    
    @property
    def npan (self) -> int:                     return self.npoint - 1 
    
    @property
    def le_bunch (self) -> float:               return self._get('le_bunch', default=0.86) 
    def set_le_bunch (self, aVal : float):      self._set('le_bunch', clip (aVal, 0.0, 1.0)) 

    @property
    def te_bunch (self) -> float:               return self._get('te_bunch', default=0.6) 
    def set_te_bunch (self, aVal : float):      self._set('te_bunch', clip (aVal, 0.0, 1.0)) 



class Nml_particle_swarm_options (Nml_Abstract):
    """ 
    &particle_swarm_options                            ! options for particle swarm optimization - PSO
        pop              = 30                          ! swarm population - no of particles 
        min_radius       = 0.001                       ! design radius when optimization shall be finished
        max_iterations   = 500                         ! max no of iterations 
        max_retries      = 2                           ! no of particle retries for geometry violations
        max_speed        = 0.1                         ! max speed of a particle in solution space 0..1 
        init_attempts    = 1000                        ! no of tries to get initial, valid design 
        convergence_profile = 'exhaustive'             ! either 'exhaustive' or 'quick' or 'quick_camb_thick'
    """
    name = "particle_swarm_options"

    EXHAUSTIVE  = 'exhaustive'
    QUICK       = 'quick'
    QUICK_CAMB  = 'quick_camb_thick'

    POSSIBLE_PROFILES = [EXHAUSTIVE, QUICK, QUICK_CAMB]

    @property
    def pop (self) -> int:                      return self._get('pop', default=30) 
    def set_pop (self, aVal : int):             self._set('pop', clip (int(aVal), 5, 100)) 

    @property
    def max_iterations (self) -> int:           return self._get('max_iterations', default=500) 
    def set_max_iterations (self, aVal : int):  self._set('max_iterations', clip (int(aVal), 0, 9999))

    @property
    def min_radius (self) -> float:             return self._get('min_radius', default=0.001) 
    def set_min_radius (self, aVal : float):    self._set('min_radius', clip (aVal, 0.0, 1.0))

    @property
    def max_retries (self) -> int:              return self._get('max_retries', default=2) 
    def set_max_retries (self, aVal : int):     self._set('max_retries', clip (int(aVal), 0, 5))

    @property
    def max_speed (self) -> float:              return self._get('max_speed', default=0.1) 
    def set_max_speed (self, aVal : float):     self._set('max_speed', clip (aVal, 0.01, 0.7))

    @property
    def init_attempts (self) -> int:            return self._get('init_attempts', default=1000) 
    def set_init_attempts (self, aVal : int):   self._set('init_attempts', clip (int(aVal), 0, 9999))

    @property
    def convergence_profile (self) -> str:      return self._get('convergence_profile', default=self.EXHAUSTIVE) 
    def set_convergence_profile (self,aVal:str):
        if aVal in self.POSSIBLE_PROFILES:      self._set('convergence_profile', aVal) 



class Nml_xfoil_run_options (Nml_Abstract):
    """ 
    &xfoil_run_options
        ncrit            = 9                           ! ncrit default value for op points 
        xtript           = 1.0                         ! forced transition point 0..1 - top  
        xtripb           = 1.0                         ! forced transition point 0..1 - bot  
        bl_maxit         = 50                          ! max no of xfoil iterations to converge
        vaccel           = 0.005                       ! xfoil vaccel parameter
        fix_unconverged  = .true.                      ! auto retry when op point doesn't converge
        reinitialize     = .false.                     ! reinit xfoil boundary layer after each op point 
    """
    name = "xfoil_run_options"

    @property
    def ncrit (self) -> float:                  return self._get('ncrit', default=9) 
    def set_ncrit (self, aVal : float):         self._set('ncrit', clip (aVal, 1.0, 20.0))

    @property
    def xtript (self) -> float:                 return self._get('xtript', default=1.0) 
    def set_xtript (self, aVal : float):        self._set('xtript', clip (aVal, 0.01, 1.0))

    @property
    def xtripb (self) -> float:                 return self._get('xtripb', default=1.0) 
    def set_xtripb (self, aVal : float):        self._set('xtripb', clip (aVal, 0.01, 1.0))

    @property
    def bl_maxit (self) -> int:                 return self._get('bl_maxit', default=50) 
    def set_bl_maxit (self, aVal : int):        self._set('bl_maxit', clip (int(aVal), 1, 500))

    @property
    def vaccel (self) -> float:                 return self._get('vaccel', default=0.005) 
    def set_vaccel (self, aVal : float):        self._set('vaccel', clip (aVal, 0.01, 0.1))

    @property
    def fix_unconverged (self) -> bool:         return self._get('fix_unconverged', default=True) 
    def set_fix_unconverged (self, aVal:bool):  self._set('fix_unconverged', aVal is True) 
                                            
    @property
    def reinitialize (self) -> bool:            return self._get('reinitialize', default=False) 
    def set_reinitialize (self, aVal:bool):     self._set('reinitialize', aVal is True) 



class Nml_curvature (Nml_Abstract):
    """ 
    &curvature                                         ! geometry curvature constraints for optimization 
        check_curvature  = .true.                      ! check curvature during optimization
        auto_curvature   = .true.                      ! auto determine thresholds for curvature and bumps
        max_curv_reverse_top = 0                       ! max no of curvature reversals - top ("reflexed"?)
        max_curv_reverse_bot = 0                       ! max no of curvature reversals - bot ("rearloading"?)
        curv_threshold   = 0.1                         ! threshold to detect reversals 
        max_te_curvature = 5.0                         ! max curvature at trailing edge
        max_le_curvature_diff = 5.0                    ! Bezier: max curvature difference at leading edge
        spike_threshold  = 0.5                         ! threshold to detect spikes aga bumps 
        max_spikes_top   = 0                           ! max no of curvature bumbs - top 
        max_spikes_bot   = 0                           ! max no of curvature bumbs - bot 
/    """
    name = "curvature"

    @property
    def check_curvature (self) -> bool:         return self._get('check_curvature', default=True) 
    def set_check_curvature (self, aVal:bool):  self._set('check_curvature', aVal is True) 

    @property
    def auto_curvature (self) -> bool:          return self._get('auto_curvature', default=True) 
    def set_auto_curvature (self, aVal : bool): self._set('auto_curvature', aVal is True) 

    @property
    def max_curv_reverse_top (self) -> int:     return self._get('max_curv_reverse_top', default=0) 
    def set_max_curv_reverse_top (self, aVal:int): self._set('max_curv_reverse_top', clip (int(aVal), 0, 5))

    @property
    def max_curv_reverse_bot (self) -> int:     return self._get('max_curv_reverse_bot', default=0) 
    def set_max_curv_reverse_bot (self, aVal:int): self._set('max_curv_reverse_bot', clip (int(aVal), 0, 5))

    @property
    def curv_threshold (self) -> float:         return self._get('curv_threshold', default=0.1) 
    def set_curv_threshold (self, aVal:float):  self._set('curv_threshold', clip (aVal, 0.01, 1.0))

    @property
    def max_te_curvature (self) -> float:       return self._get('max_te_curvature', default=5.0) 
    def set_max_te_curvature (self,aVal:float): self._set('max_te_curvature', clip (aVal, 0.01, 50) if aVal != 5.0 else None)

    @property
    def max_le_curvature_diff (self) -> float:  return self._get('max_le_curvature_diff', default=5.0) 
    def set_max_le_curvature_diff (self, aVal): self._set('max_le_curvature_diff', clip (aVal, 0.1, 50))

    @property
    def spike_threshold (self) -> float:        return self._get('spike_threshold', default=0.5) 
    def set_spike_threshold (self, aVal:float): self._set('spike_threshold', clip (aVal, 0.1, 5.0))

    @property
    def max_spikes_top (self) -> int:           return self._get('max_spikes_top', default=0) 
    def set_max_spikes_top (self, aVal : int):  self._set('max_spikes_top', clip (int(aVal), 0, 20))

    @property
    def max_spikes_bot (self) -> int:           return self._get('max_spikes_bot', default=0) 
    def set_max_spikes_bot (self, aVal : int):  self._set('max_spikes_bot', clip (int(aVal), 0, 20))



class Nml_constraints (Nml_Abstract):
    """ 
    &constraints                                       ! geometry constraints for optimization
        check_geometry   = .true.                      ! check geometry against geometry constraints 
        min_te_angle     = 2.d0                        ! min trailing edge angle in degrees
        symmetrical      = .false.                     ! force airfoil to be symmetrical 
        min_thickness    =                             ! min thickness        (better use geometry targets) 
        max_thickness    =                             ! max thickness        (better use geometry targets) 
        min_camber       =                             ! min camber           (better use geometry targets) 
        max_camber       =                             ! max camver           (better use geometry targets) 
    """
    name = "constraints"

    @property
    def check_geometry (self) -> bool:          return self._get('check_geometry', default=True) 
    def set_check_geometry (self, aVal:bool):   self._set('check_geometry', aVal is True) 

    @property
    def symmetrical (self) -> bool:             return self._get('symmetrical', default=False) 
    def set_symmetrical (self, aVal : bool):    self._set('symmetrical', aVal is True) 

    @property
    def min_te_angle (self) -> float:           return self._get('min_te_angle', default=2.0) 
    def set_min_te_angle (self, aVal : float):  self._set('min_te_angle', clip (aVal, 0.1, 20.0)) 




class Nml_geometry_targets (Nml_Abstract):
    """ 
    &geometry_targets                                  ! geometry targets which should be achieved
        ngeo_targets     = 0                           ! no of geometry targets 
        target_type(1)   = ''                          ! either 'camber', 'thickness', 'match-foil' 
        target_value(1)  = 0.0                         ! target value to achieve 
        target_string(1) = 0.0                         ! in case of 'match-foil' filename of airfoil 
        weighting(1)     = 1.0                         ! weighting of this target
        preset_to_target(1) = .false.                  ! preset seed airfoil to this target 
    """
    name = "geometry_targets"

    def __init__ (self, *args):

        self._geoTarget_defs = None 
        super().__init__(*args)


    @override
    def _write_arrays (self, aStream : TextIO):
        """ write arrays to stream"""

        # write geo targets as single value like 
        # target_type(1)   = 'thickness'                          
        # target_value(1)  = 0.078                         
        # target_string(1) = 0.0                       
        # weighting(1)     = 1.0                        

        target_types = self._get('target_type', [])        

        noneArr = [None] * len(target_types)                       # len op_points is master

        target_values = self._get('target_value',       noneArr)
        weightings    = self._get('weighting',          noneArr)
        presets       = self._get('preset_to_target',   noneArr)

        for i, _ in enumerate (target_types):

            if i > 0: aStream .write (f"\n")                       # blank line 

            self._write_entry (aStream, f"target_type({i+1})",      target_types[i])
            self._write_entry (aStream, f"target_value({i+1})",     target_values[i])
            self._write_entry (aStream, f"weighting({i+1})",        weightings[i])
            self._write_entry (aStream, f"preset_to_target({i+1})", presets[i])

    @property
    def ngeo_targets (self) -> int:             return self._get('ngeo_targets', default=0) 
    def set_ngeo_targets (self, aVal):          self._set ('ngeo_targets', clip (int(aVal), 0, 3)) 

    @property
    def geoTarget_defs (self) -> GeoTarget_Definitions:

        if self._geoTarget_defs is None: 
            self._geoTarget_defs = GeoTarget_Definitions (self)
        return self._geoTarget_defs

