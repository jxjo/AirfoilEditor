#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Polars of an airfoil 

    A Polar_Definition defines a polars 

        type      like T1 or T2
        re        like 400000
        ma        like 0.0 
        ncrit     like 7.0 
        autoRange
        specVar   like cl or alpha
        valRange  like -2, 12, 0.2

    At runtime an airfoil may have a Polar Set having some Polars

    A Polar consists out of n OpPoints holding the aerodynamic values like cd or cm 


    Object Model  

        Polar_Definition                            - defines a single Polar

        Airfoil
            |-- Polar_Set                           - manage polars of an airfoil
                -- Polar                            - a single polar  
                    |-- OpPoint                     - operating point holding aero values 

"""

import os
import sys
from typing                 import Tuple, override
from enum                   import StrEnum
from pathlib                import Path

import numpy as np

# let python find the other modules in the dir of self  
sys.path.append(Path(__file__).parent)
from base.common_utils      import * 
from base.math_util         import * 
from base.spline            import Spline1D, Spline2D

from model.airfoil          import Airfoil, GEO_BASIC, GEO_SPLINE, usedAs
from model.xo2_driver       import Worker, file_in_use   


import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


#  Constants for polar types 

CL      = "cl"               
CD      = "cd"               
ALPHA   = "alpha"               
GLIDE   = "cl/cd" 
SINK    = "sink"        # "cl^1.5/cd"              
CM      = "cm"               
XTRT    = "xtrt"               
XTRB    = "xtrb"    


#-------------------------------------------------------------------------------
# enums   
#-------------------------------------------------------------------------------

class StrEnum_Extended (StrEnum):
    """ enum extension to get a list of all enum values"""
    @classmethod
    def list(cls):
        return list(map(lambda c: c.value, cls))


class var (StrEnum_Extended):
    """ polar variables """
    CL      = "cl"               
    CD      = "cd"               
    ALPHA   = "alpha"               
    GLIDE   = "cl/cd" 
    SINK    = "sink"        # "cl^1.5/cd"              
    CM      = "cm"               
    XTRT    = "xtrt"               
    XTRB    = "xtrb"    


class polarType (StrEnum_Extended):
    """ xfoil polar types """
    T1      = "T1"
    T2      = "T2"


SPEC_ALLOWED = [ALPHA,CL]


#------------------------------------------------------------------------------


class Polar_Definition:
    """ 
    Defines the properties of a Polar  

    Polar_Definition

    Airfoil 
        |--- Polar_Set 
                |--- Polar    <-- Polar_Definition

    """

    VAL_RANGE_ALPHA = [-4.0, 13.0, 0.50]
    VAL_RANGE_CL    = [-0.2,  1.2, 0.05]

    def __init__(self, dataDict=None):
        
        self._ncrit     = fromDict (dataDict, "ncrit",    7.0)
        self._autoRange = fromDict (dataDict, "autoRange",True)
        self._specVar   = fromDict (dataDict, "specVar",  ALPHA)
        self._valRange  = fromDict (dataDict, "valRange", self.VAL_RANGE_ALPHA)
        self._type      = fromDict (dataDict, "type",     polarType.T1)
       
        self._re        = fromDict (dataDict, "re",       400000)             
        self._ma        = fromDict (dataDict, "mach",     0.0)

        self._active    = fromDict (dataDict, "active",   True)             # a polar definition can be in-active


    def __repr__(self) -> str:
        """ nice print string wie polarType and Re """
        return f"<{type(self).__name__} {self.name}>"

    # --- save --------------------- 

    def _as_dict (self):
        """ returns a data dict with the parameters of self """

        d = {}
        toDict (d, "type",           self.type) 
        toDict (d, "re",             self.re) 
        toDict (d, "ma",             self.ma) 
        toDict (d, "ncrit",          self.ncrit) 
        toDict (d, "specVar",        self.specVar) 
        toDict (d, "autoRange",      self.autoRange) 
        toDict (d, "valRange",       self.valRange) 
        toDict (d, "active",         self.active) 
        return d


    @property
    def active (self) -> bool:
        """ True - self is in use"""
        return self._active 
    
    def set_active (self, aBool : bool):
        self._active = aBool == True 


    @property
    def ncrit (self) -> float:
        """ ncrit of polar""" 
        return self._ncrit
    def set_ncrit (self, aVal : float): 
        if aVal is not None and (aVal > 0.0 and aVal < 20.0):
            self._ncrit = aVal 


    @property
    def specVar (self): 
        """ ALPHA or CL defining value range"""
        return self._specVar
    
    def set_specVar (self, aVal): 
        if aVal == ALPHA or aVal == CL: 
            self._specVar = aVal 
            if self._specVar == ALPHA:                                       # reset value range 
                self._valRange = self.VAL_RANGE_ALPHA
            else: 
                self._valRange = self.VAL_RANGE_CL

    @property
    def type (self) -> polarType: 
        """ polarType.T1 or T2"""
        return self._type
    def set_type (self, aVal): 
        if aVal in polarType.list(): 
            self._type = aVal 


    @property
    def valRange (self) -> list[float]:
        """ value range of polar  [from, to, step]""" 
        return self._valRange  

    def set_valRange (self, aRange : list): 
        if len(aRange) ==3 : 
            self._valRange = aRange 


    @property
    def autoRange (self) -> bool:
        """ auto range mode of Worker""" 
        return self._autoRange 

    def set_autoRange (self, aBool : bool): 
        self._autoRange = aBool is True  


    @property
    def valRange_string (self) -> str: 
        """ value range something like '-4, 12, 0.1' """
        if not self.autoRange:
            return ", ".join(str(x).rstrip('0').rstrip('.')  for x in self._valRange) 
        else: 
            return f"auto range ({self.valRange_step:.2f})"
    
    def set_valRange_string (self, aString):
        """ set new value range from something like '-4, 12, 0.1'"""
        
        valRange = []
        valsString = aString.split(',')
        if len(valsString) == 3:
            try:
                rangeFrom = float (valsString[0]) 
                rangeTo   = float (valsString[1]) 
                rangeStep = float (valsString[2]) 
                if rangeFrom < rangeTo and rangeStep > 0.0: 
                    valRange.append(rangeFrom)
                    valRange.append(rangeTo)
                    valRange.append(rangeStep)
            except: 
                pass
        self.set_valRange (valRange)

    @property
    def valRange_string_long (self): 
        """ value range something like 'alpha: -4, 12, 0.1' """
        return f"{self.specVar}: {self.valRange_string}"

    @property
    def valRange_from (self) -> float: 
        return self._valRange[0]
    def set_valRange_from (self, aVal : float): 
        if aVal < self.valRange_to:
            self._valRange[0] = aVal

    @property
    def valRange_to (self) -> float: 
        return self._valRange[1]
    def set_valRange_to (self, aVal): 
        if aVal > self.valRange_from:
            self._valRange[1] = aVal

    @property
    def valRange_step (self) -> float: 
        """ step size of value range"""
        return self._valRange[2]
    
    def set_valRange_step (self, aVal : float):
        if self.specVar == ALPHA:
            aVal = np.clip (aVal, 0.1, 1.0)
        else: 
            aVal = np.clip (aVal, 0.01, 0.1)
        self._valRange[2] = aVal


    @property
    def re (self) -> float: 
        """ Reynolds number"""
        return self._re
    def set_re (self, re): 
        if re and (re >= 1000 and re < 10000000):
            self._re = re

    @property
    def re_asK (self) -> int: 
        """ Reynolds number base 1000"""
        return int (self.re/1000) if self.re is not None else 0 
    def set_re_asK (self, aVal): 
        self.set_re (aVal * 1000)

    @property
    def ma (self) -> float: 
        """ Mach number like 0.3"""
        return self._ma
    def set_ma (self, aMach):
        if aMach is not None and (aMach >= 0.0 and aMach < 1.0):
            self._ma = aMach 

    @property
    def name (self): 
        """ returns polar name as a label  """
        return Polar.get_label(self.type, self.re, self.ma, self.ncrit)

    @property
    def polarName_long (self):
        """ returns polar extended name self represents """
        return self.name + f"  {self.valRange_string_long}"
    



#------------------------------------------------------------------------------

class Polar_Set:
    """ 
    Manage the polars of an airfoil   

    Polar_Definition

    Airfoil 
        |--- Polar_Set 
                |--- Polar    <-- Polar_Definition

    """

    instances : list ['Polar_Set']= []               # keep track of all instances ceated to reset 


    def __init__(self, myAirfoil: Airfoil, polar_def : Polar_Definition | list | None = None):
        """
        Main constructor for new polar set which belongs to an airfoil 

        Args:
            myAirfoil: the airfoil object it belongs to 
            polar_def: (list of) Polar_Definition to be added initially
        """

        self.__class__.instances.append(self)       # keep track of all instances

        self._airfoil = myAirfoil 
        self._polars = []                           # list of Polars of self is holding

        self._polar_worker_tasks = []               # polar generation tasks for worker 
        self._worker_polar_sets = {}                # polar generation job list for worker  

        self.add_polar_defs (polar_def)             # add initial polar def 


    def __repr__(self) -> str:
        """ nice representation of self """
        return f"<{type(self).__name__} of {self.airfoil}>"

    #---------------------------------------------------------------

    @classmethod
    def terminate_polar_generation_except_for (cls, airfoils):
        """ terminate all worker polar generation beside for 'airfoil'"""

        for polar_set in cls.instances:
            if not polar_set.airfoil in airfoils: 
                for worker_task in polar_set.polar_worker_tasks:
                    worker_task.terminate()


    #---------------------------------------------------------------

    @property
    def airfoil (self) -> Airfoil: return self._airfoil

    @property
    def airfoil_abs_pathFileName (self):
        """ returns absolute path of airfoil"""
        abs_path = None
        if self.airfoil:
            pathFileName = self.airfoil.pathFileName  
            if os.path.isabs (pathFileName):
                abs_path = pathFileName
            else:
                abs_path = os.path.join (self._airfoil.workingDir, pathFileName)

        # in case of Bezier we'll write only the .bez file 
        if self.airfoil.isBezierBased:
            abs_path = os.path.splitext(abs_path)[0] + ".bez"

        return abs_path

    def airfoil_ensure_being_saved (self):
        """ check and ensure that airfoil is saved to file (Worker needs it)"""

        if self.airfoil.isModified:
            if os.path.isfile (self.airfoil_abs_pathFileName):
                self.airfoil.set_isModified (False) 
            else: 
                if self.airfoil.isBezierBased:                      # for Bezier write only .bez - no dat
                    self.airfoil.save(onlyShapeFile=True)
                else: 
                    self.airfoil.save()
                logging.debug (f'Airfoil {self.airfoil} saved for polar generation') 


    @property
    def polars (self) -> list ['Polar']: 
        return self._polars

    @property
    def polars_not_loaded (self) -> list ['Polar']: 
        """ not loaded polars of self """
        return list(filter(lambda polar: not polar.isLoaded, self._polars)) 


    @property
    def has_polars (self): return len (self.polars) > 0 
    

    @property
    def has_polars_not_loaded (self) -> bool: 
        """ are there polars which are still not lazyloadeds when async polar generation """
        return len(self.polars_not_loaded) > 0
        

    @property
    def polar_worker_tasks (self) -> list ['Polar_Worker_Task']:
        """ current worker tasks of self"""
        return self._polar_worker_tasks

    #---------------------------------------------------------------

    def add_polar_defs (self, polar_defs):
        """ 
        Adds polars based on a active polar_def to self.
        The polars won't be loaded (or generated) 

        polar_defs can be a list or a single Polar_Definition
        """

        if isinstance(polar_defs, list):
            polar_def_list = polar_defs
        else: 
            polar_def_list = [polar_defs]

        polar_def : Polar_Definition
        for polar_def in polar_def_list:

            # is there already a similar polar - remove it 
            polar: Polar
            for polar in self.polars: 
                if polar.name == polar_def.name: 
                    polar.polar_set_detach ()
                    self.polars.remove(polar)

            # append new polar if it is active 
            if polar_def.active:
                self.polars.append (Polar(self, polar_def))



    def remove_polars (self):
        """ Removes all polars of self  """

        polar: Polar
        for polar in self.polars: 
            polar.polar_set_detach ()
            self.polars.remove(polar)


    def load_or_generate_polars (self):
        """ 
        Either loads or (if not already exist) generate polars of myAirfoil 
            for all polars of self.
        """

        # try to load already existing polar files 

        self.load_polars ()

        if not self.has_polars_not_loaded:                              # all done  
            for task in self.polar_worker_tasks:
                task.finalize ()
            self._polar_worker_tasks = []                               # remove tasks
            return                                                   
        elif self.polar_worker_tasks:                                   # there are already task running
            return

        # some polare have to be generated by Worker 

        self.airfoil_ensure_being_saved ()
 
        # build worker jobs 

        for polar in self.polars_not_loaded: 
            taken_over = False
            for task in self.polar_worker_tasks:
                taken_over =  task.take_over_polar (polar)
                if taken_over: break
            if not taken_over:
                 self._polar_worker_tasks.append(Polar_Worker_Task(polar))   

        # run all worker tasks 

        for task in self.polar_worker_tasks:
            task.start_polar_generation ()

        return 


    def load_polars (self) -> int:
        """ 
        loads all lazy polars which were generated async and now ready.
        Returns number of new loaded polars
        """
        nLoaded    = 0

        # from timeit import default_timer as timer
        # start = timer()

        polar : Polar
        for polar in self.polars: 

            if not polar.isLoaded:
                try:                
                    polar.load ()

                    if polar.isLoaded: nLoaded += 1
                except (RuntimeError) as exc:
                    logger.warning (f"{self} - loading polar failed for: {polar} error: {exc}")

        # print("Time ", timer() - start)  
        return nLoaded


#------------------------------------------------------------------------------

class Polar (Polar_Definition):
    """ 
    A single polar of an airfoil created by Worker

    Polar_Definition

    Airfoil 
        |--- Polar_Set 
                |--- Polar    <-- Polar_Definition
    """

    polarVarList = [CL, CD, ALPHA, GLIDE, SINK, CM, XTRT, XTRB]

    @classmethod
    def get_label (cls, polarType, re, ma, ncrit): 
        """ return a label of these polar variables"""
        if ma:
            maString = f" M {ma:.2f}".rstrip('0').rstrip('.') 
        else: 
            maString = ""
        ncritString = f" Ncrit {ncrit:.2f}".rstrip('0').rstrip('.') 
        return f"{polarType} Re {int(re/1000)}k{maString}{ncritString}"



    def __init__(self, mypolarSet: Polar_Set, polar_def : Polar_Definition = None):
        """
        Main constructor for new polar which belongs to a polar set 

        Args:
            :mypolarSet: the polar set object it belongs to 
            :polar_def: optional the polar_definition to initilaize self deinitions
        """
        self._polar_set = mypolarSet
        self._error_reason = None               # if error occurred during polar generation 

        self._opPoints = []                     # the single opPoins of self
        self._alpha = []
        self._cl = []
        self._cd = []
        self._cm = [] 
        self._cd = [] 
        self._xtrt = []
        self._xtrb = []
        self._glide = []
        self._sink = []

        if polar_def: 
            self.set_type       (polar_def.type)
            self.set_re         (polar_def.re)
            self.set_ma         (polar_def.ma)
            self.set_ncrit      (polar_def.ncrit)
            self.set_autoRange  (polar_def.autoRange)
            self.set_specVar    (polar_def.specVar)
            self.set_valRange   (polar_def.valRange)


    def __repr__(self) -> str:
        """ nice print string wie polarType and Re """
        return f"<{type(self).__name__} {self.name}>"

    #--------------------------------------------------------

    @property
    def polar_set (self) -> Polar_Set: return self._polar_set
    def polar_set_detach (self):
        """ detaches self from its polar set"""
        self._polar_set = None


    @property
    def opPoints (self) -> list:
        """ returns the sorted list of opPoints of self """
        return self._opPoints
    
    def set_opPoints (self, opPoints_new: list):
        """ set list of opPoints of self """
        self._opPoints = opPoints_new 

        if self.is_DESIGN_polar:                            # cut extrem beginings & endings
            self.adjust_DESIGN_polar ()
    
    @property
    def isLoaded (self) -> bool: 
        """ is polar data loaded from file (for async polar generation)"""
        return len(self._opPoints) > 0 or self.error_occurred
    
    @property 
    def error_occurred (self) -> bool:
        """ True if error occurred during polar generation"""
        return self._error_reason is not None
    
    @property
    def error_reason (self) -> str:
        """ reason of error during polar geneation """
        return self._error_reason
    
    @property
    def alpha (self) -> list:
        if self._alpha == []: self._alpha = self._get_values_forVar (ALPHA)
        return self._alpha
    
    @property
    def cl (self) -> list:
        if self._cl == []: self._cl = self._get_values_forVar (CL)
        return self._cl
    
    @property
    def cd (self) -> list:
        if self._cd == []: self._cd = self._get_values_forVar (CD)
        return self._cd
    
    @property
    def glide (self) -> list:
        if self._glide == []: self._glide = self._get_values_forVar (GLIDE)
        return self._glide
    
    @property
    def sink (self) -> list:
        if self._sink == []: self._sink = self._get_values_forVar (SINK)
        return self._sink
    
    @property
    def cm (self) -> list:
        if self._cm == []: self._cm = self._get_values_forVar (CM)
        return self._cm
    
    @property
    def xtrt (self) -> list:
        if self._xtrt == []: self._xtrt = self._get_values_forVar (XTRT)
        return self._xtrt
    
    @property
    def xtrb (self) -> list:
        if self._xtrb == []: self._xtrb = self._get_values_forVar (XTRB)
        return self._xtrb
    
    def ofVars (self, xyVars: Tuple[str, str]):
        """ returns x,y polar of the tuple xyVars"""

        x, y = [], []
        
        if isinstance(xyVars, tuple):
            x = self._ofVar (xyVars[0])
            y = self._ofVar (xyVars[1])

            # sink polar - cut values <= 0 
            if SINK in xyVars: 
                i = 0 
                if SINK == xyVars[0]:
                    for i, val in enumerate(x):
                        if val > 0.0: break
                else: 
                    for i, val in enumerate(y):
                        if val > 0.0: break
                x = x[i:]
                y = y[i:]
        return x,y 


    def _ofVar (self, var: str):

        vals = []
        if   var == CL:
            vals = self.cl
        elif var == CD:
            vals = self.cd
        elif var == ALPHA:
            vals = self.alpha
        elif var == GLIDE:
            vals = self.glide
        elif var == SINK:
            vals = self.sink
        elif var == CM:
            vals = self.cm
        elif var == XTRT:
            vals = self.xtrt
        elif var == XTRB:
            vals = self.xtrb
        else:
            raise ValueError ("Unkown polar variable: %s" % var)
        return vals

    def _get_values_forVar (self, var) -> list:
        """ copy values of var from op points to list"""

        nPoints = len(self.opPoints)
        if nPoints == 0: return [] 

        values  = [0] * nPoints
        op : OpPoint
        for i, op in enumerate(self.opPoints):
            values[i] = op.get_value (var)
        return values 


    def get_optValue (self, specVar, specVal, optVar):
        """ interpolates optvar in polar (specVar, optVar)"""

        if not self.isLoaded: return None

        specVals = self._ofVar (specVar)
        optVals  = self._ofVar (optVar)

        # find the index in self.x which is right before x
        jl = bisection (specVals, specVal)
        
        # now interpolate the y-value on lower side 
        if jl < (len(specVals) - 1):
            x1 = specVals[jl]
            x2 = specVals[jl+1]
            y1 = optVals[jl]
            y2 = optVals[jl+1]
            y = interpolate (x1, x2, y1, y2, specVal)
        else: 
            y = optVals[-1]

        if optVar == CD:
            y = round (y,5)
        else:
            y = round(y,2) 

        return y

    @property 
    def is_DESIGN_polar (self) -> bool:
        """ true if self is polar for a DESIGN airfoil"""

        if self.polar_set.airfoil: 
            return self.polar_set.airfoil.usedAs == usedAs.DESIGN
        else: 
            return False

    
    #--------------------------------------------------------

    def adjust_DESIGN_polar (self):
        """ adjust opPoints of DESIGN polar - cuts alpha max, min """

        if not self.opPoints: return 

        # alpha min - cut to lowest cl/cd 
        glide_min = self.opPoints[0].glide 
        op : OpPoint
        for i, op in enumerate (self.opPoints): 
            if op.glide <= glide_min:
                glide_min = op.glide 
            else: 
                self._opPoints = self._opPoints [i:]
                break

        # cut to cl-max 
        cl_max = self.opPoints[-1].cl 
        for i, op in reversed(list(enumerate(self.opPoints))):
            if op.cl >= cl_max:
                cl_max = op.cl 
            else: 
                self._opPoints = self._opPoints [:i+2]
                break
   

    def load (self):
        """ 
        Loads self from Xfoil polar file.

        If loading was successful, isLoaded will be True 
        """

        if self.isLoaded: return 


        airfoil_abs_pathFileName = self.polar_set.airfoil_abs_pathFileName

        # polar existing - will also check for Worker error

        try: 
            polar_pathFileName = Worker().get_existingPolarFile (airfoil_abs_pathFileName, 
                                            self.type, self.re, self.ma , self.ncrit)
        except (RuntimeError) as exc: 
            self._error_reason = str(exc)
            raise                                           # re-raise exception 

        if polar_pathFileName and not file_in_use (polar_pathFileName): 

            # read polar from file 

            try: 
                self._import_from_file(polar_pathFileName)
                logging.debug (f'{self} loaded for {self.polar_set.airfoil}') 
            except (RuntimeError) as exc:  
                self._error_reason = str(exc)
                raise                                           # re-raise exception 


    def _import_from_file (self, polarPathFileName):
        """
        Read data for self from an Xfoil polar file  
        """

        opPoints = []

        BeginOfDataSectionTag = "-------"
        airfoilNameTag = "Calculated polar for:"
        reTag = "Re ="
        ncritTag = "Ncrit ="
        parseInDataPoints = 0

        fpolar = open(polarPathFileName)

        # parse all lines
        for line in fpolar:

            # scan for airfoil-name
            if  line.find(airfoilNameTag) >= 0:
                splitline = line.split(airfoilNameTag)
                self.airfoilname = splitline[1].strip()
            # scan for Re-Number and ncrit
            if  line.find(reTag) >= 0:
                splitline = line.split(reTag)
                splitline = splitline[1].split(ncritTag)

                re_string    = splitline[0].strip()
                splitstring = re_string.split("e")
                faktor = float(splitstring[0].strip())
                Exponent = float(splitstring[1].strip())
                re = faktor * (10**Exponent)

                # sanity checks 
                if self.re != re: 
                    raise RuntimeError (f"Re Number of polar ({self.re}) and of polar file ({re}) not equal")

                ncrit = float(splitline[1].strip())
                if self.ncrit != ncrit: 
                    raise RuntimeError (f"Ncrit of polar ({self.ncrit}) and of polar file ({ncrit}) not equal")
                # ncrit within file ignored ...

            # scan for start of data-section
            if line.find(BeginOfDataSectionTag) >= 0:
                parseInDataPoints = 1
            else:
                # get all Data-points from this line
                if parseInDataPoints == 1:
                    # split up line detecting white-spaces
                    splittedLine = line.split(" ")
                    # remove white-space-elements, build up list of data-points
                    dataPoints = []
                    for element in splittedLine:
                        if element != '':
                            dataPoints.append(element)
                    op = OpPoint ()
                    op.alpha = float(dataPoints[0])
                    op.cl = float(dataPoints[1])
                    op.cd = float(dataPoints[2])
                    # cdp = float(dataPoints[3])
                    op.cm = float(dataPoints[4])
                    op.xtrt = float(dataPoints[5])
                    op.xtrb = float(dataPoints[6])

                    opPoints.append(op)
        fpolar.close()

        if len(opPoints) > 0: 

            self.set_opPoints (opPoints)

        else: 
            logger.error (f"{self} - import from {polarPathFileName} failed")
            raise RuntimeError(f"Could not read polar file" )
 


#------------------------------------------------------------------------------


class Polar_Worker_Task (Polar_Definition):
    """ 
    Single Task for Worker to generate polars based on paramters
    May generate many poars having same ncrit and type    

    Polar_Definition

    Airfoil 
        |--- Polar_Set 
                |--- Polar    <-- Polar_Definition
                |--- Polar_Worker_Task
    """

    def __init__(self, polar: Polar =None):
        
        self._ncrit     = None
        self._autoRange = None
        self._specVar   = None
        self._valRange  = None
        self._type      = None
       
        self._re        = []             
        self._ma        = []

        self._polars    = []                # polars to generate 
        self._myWorker  = None              # Worker instance which does the job
        self._polar_set = None


        if polar:
            self.take_over_polar (polar) 

    def __repr__(self) -> str:
        """ nice representation of self """
        return f"<{type(self).__name__} of {self._type} Re {self._re} Ma {self._ma} Ncrit {self._ncrit}>"


    def take_over_polar (self, polar : Polar) -> bool:
        """
        Checks and accepts a poalr for polar generation
        Returns True if polar is taken over by self
        """    

        # sanity - - polar already generated and loaded 
        if polar.isLoaded: return  

        taken_over = True 
        
        if not self._re: 
            self._ncrit     = polar.ncrit
            self._autoRange = polar.autoRange
            self._specVar   = polar.specVar
            self._valRange  = polar.valRange
            self._type      = polar.type
        
            self._re        = [polar.re]             
            self._ma        = [polar.ma]

            self._polar_set  = polar.polar_set

        elif  self._type==polar.type and self._ncrit == polar.ncrit and \
              self._autoRange == polar.autoRange and \
              self._specVar == polar.specVar and self._valRange == polar.valRange:
            
            self._re.append (polar.re)
            self._ma.append (polar.ma)

        else: 
            taken_over = False

        return taken_over 


    def start_polar_generation (self):
        """ run worker to generate self polars"""

        self._myWorker = Worker ()

        try:
            self._myWorker.generate_polar (self._polar_set.airfoil_abs_pathFileName, 
                        self._type, self._re, self._ma, self._ncrit, self._autoRange, 
                        self._specVar, self._valRange, None, run_async=True)
            logger.debug (f"{self} started")


        except (RuntimeError) as exc:

            logger.warning (f"{self} - polar generation failed - error: {exc}")
            self._myWorker = None


    def terminate (self):
        """ kill an active workerpolar generation """
        if self._myWorker and self._myWorker.isRunning():
            logger.warning (f"terminating {self}")
            self._myWorker.terminate()
            self.finalize()


    def finalize (self):
        """ all polars generated - worker clean up """

        if self._myWorker:
            self._myWorker.remove_tmp_inp_file ()
            self._myWorker = None 


    def isRunning (self) -> bool:
        """ is worker still running"""
        return self._myWorker.isRunning() if self._myWorker else False

# ------------------------------------------


class OpPoint:
    """ 
    A single (operating) point of a polar of an airfoil   

    airfoil 
        --> Polar_Set 
            --> Polar   (1..n) 
                --> OpPoint  (1..n) 
    """
    def __init__(self):
        """
        Main constructor for new opPoint 

        """
        self.spec   = ALPHA                     # self based on ALPHA or CL
        self.valid  = True                      # has it converged during xfoil calculation
        self.alpha  = None
        self.cl     = None
        self.cd     = None
        self.cm     = None 
        self.xtrt   = None                      # transition top side
        self.xtrb   = None                      # transition bot side

    @property
    def glide (self): 
        if self.cd and self.cl:                 # cd != 0.0  
            return self.cl/self.cd  
        else: 
            return 0.0 

    @property
    def sink (self): 
        if self.cd > 0.0 and self.cl >= 0.0:                 # cd != 0.0  
            return self.cl**1.5 / self.cd
        else: 
            return 0.0 

    def get_value (self, id ) -> float:
        """ get the value of the opPoint variable with id"""

        if id == CD:
            val = self.cd
        elif id == CL:
            val = self.cl
        elif id == ALPHA:
            val = self.alpha
        elif id == CM:
            val = self.cm
        elif id == XTRT:
            val = self.xtrt
        elif id == XTRB:
            val = self.xtrb
        elif id == GLIDE:
            val = self.glide
        elif id == SINK:
            val = self.sink
        else:
            raise ValueError ("Op point variable id '%s' not known" %id)
        return val 




class Polar_Splined (Polar_Definition):
    """ 
    A single polar of an airfoil splined on basis of control points 

    Airfoil 
        --> Polar_Set 
            --> Polar   
    """

    polarVarList = [CL, CD, GLIDE]

    @classmethod
    def get_label (cls, polarType, re, ma, ncrit): 
        """ return a label of these polar variables"""
        if ma:
            maString = f" Ma {ma:.2f}".rstrip('0').rstrip('.') 
        else: 
            maString = ""
        ncritString = f" Ncrit {ncrit:.2f}".rstrip('0').rstrip('.') 
        return f"{polarType} Re {int(re/1000)}k{maString}{ncritString}"



    def __init__(self, mypolarSet: Polar_Set, polar_def : Polar_Definition = None):
        """
        Main constructor for new polar which belongs to a polar set 

        Args:
            mypolarSet: the polar set object it belongs to 
            polar_def: optional the polar_definition to initilaize self deinitions
        """
        super().__init__()

        self._polar_set = mypolarSet

        self._opPoints = []                     # the single opPoins of self
        self._alpha = []
        self._cl = []
        self._cd = []
        self._cm = [] 
        self._cd = [] 
        self._xtrt = []
        self._xtrb = []
        self._glide = []
        self._sink = []

        if polar_def: 
            self.set_type       (polar_def.type)
            self.set_re         (polar_def.re)
            self.set_ma         (polar_def.ma)
            self.set_ncrit      (polar_def.ncrit)
            self.set_autoRange  (polar_def.autoRange)
            self.set_specVar    (polar_def.specVar)
            self.set_valRange   (polar_def.valRange)

        self._spline : Spline2D     = None   # 2 D cubic spline representation of self

        self._x                     = None   # spline knots - x coordinates  
        self._xVar                  = None   # xVar like CL 
        self._y                     = None   # spline knots - y coordinates  
        self._yVar                  = None   # yVar like CD 


    def __repr__(self) -> str:
        # overwrite to get a nice print string wie polarType and Re
        return f"'{Polar_Splined.get_label ('Splined', self.re, self.ma, self.ncrit)}'"

    #--------------------------------------------------------

    @property
    def polar_set (self) -> Polar_Set: 
        return self._polar_set
    def polar_set_detach (self):
        """ detaches self from its polar set"""
        self._polar_set = None

    def set_knots (self, xVar, xValues, yVar, yValues):
        """ set spline knots """
        self._x     = xValues  
        self._xVar  = xVar  
        self._y     = yValues   
        self._yVar  = yVar  

    def set_knots_from_opPoints_def (self, xyVar:tuple, opPoints_def: list):
        """ set spline knots """

        if len(opPoints_def) < 3: return            # minimum for spline 

        specVar = opPoints_def[0].specVar

        if specVar == xyVar [0]:
            self._xVar  = xyVar [0] 
            self._yVar  = xyVar [1] 
        else: 
            self._xVar  = xyVar [1] 
            self._yVar  = xyVar [0] 
        self._x  = []  
        self._y  = []

        logging.debug (f"spline x: {self._xVar}   y: {self._yVar}")

        for op in opPoints_def:  
            x,y = op.xyValues_for_xyVars ((self._xVar, self._yVar)) 
            if (x is not None) and (y is not None): 
                self._x.append (x)
                self._y.append (y)

        self.set_re (op.re)
        self.set_type (op.re_type)
        self.set_ncrit (op.ncrit)
        self.set_ma (op.ma)


    @property 
    def spline (self) -> Spline1D:
        """ spline representation of self """

        if self._spline is None: 
            if len (self._x) > 3: 
                boundary = 'notaknot'
            else: 
                boundary = "natural"
            self._spline = Spline1D (self._x, self._y, boundary=boundary)
            logging.debug (f"{self} New {boundary} spline with {len (self._x)} knots")
        return self._spline


    @property
    def opPoints (self) -> list:
        """ returns the sorted list of opPoints of self """
        return self._opPoints
    
    def set_opPoints (self, opPoints_new: list):
        """ set list of opPoints of self """
        self._opPoints = opPoints_new
    
    @property
    def isLoaded (self) -> bool: 
        """ is polar data available"""
        return self._x and self._y
    

    @property
    def alpha (self) -> list:
        return self._alpha
    
    @property
    def cl (self) -> list:
        return self._cl
    
    @property
    def cd (self) -> list:
        return self._cd
    
    @property
    def glide (self) -> list:
        return self._glide
    
    @property
    def sink (self) -> list:
        return self._sink
    
    @property
    def cm (self) -> list:
        return self._cm
    
    @property
    def xtrt (self) -> list:
        return self._xtrt
    
    @property
    def xtrb (self) -> list:
        return self._xtrb
    
    def ofVars (self, xyVars: Tuple[str, str]):
        """ returns x,y polar of the tuple xyVars"""

        x, y = [], []
        
        if isinstance(xyVars, tuple):
            x = self._ofVar (xyVars[0])
            y = self._ofVar (xyVars[1])

            # sink polar - cut vlaues <= 0 
            if SINK in xyVars: 
                i = 0 
                if SINK == xyVars[0]:
                    for i, val in enumerate(x):
                        if val > 0.0: break
                else: 
                    for i, val in enumerate(y):
                        if val > 0.0: break
                x = x[i:]
                y = y[i:]
        return x,y 


    def _ofVar (self, var: str):

        vals = []
        if   var == CL:
            vals = self.cl
        elif var == CD:
            vals = self.cd
        elif var == ALPHA:
            vals = self.alpha
        elif var == GLIDE:
            vals = self.glide
        elif var == SINK:
            vals = self.sink
        elif var == CM:
            vals = self.cm
        elif var == XTRT:
            vals = self.xtrt
        elif var == XTRB:
            vals = self.xtrb
        else:
            raise ValueError ("Unkown polar variable: %s" % var)
        return vals

    def _set_var (self, var: str, vals: list):
        """ set vals in var (eg CL)"""
        if   var == CL:
            self._cl = vals 
        elif var == CD:
            self._cd = vals
        elif var == ALPHA:
            self._alpha = vals
        elif var == GLIDE:
            self._glide = vals
        elif var == SINK:
            self._sink = vals
        elif var == CM:
            self._cm = vals
        elif var == XTRT:
            self._xtrt = vals
        elif var == XTRB:
            self._xtrb = vals
        else:
            raise ValueError ("Unkown polar variable: %s" % var)
        return vals

   
    def ofVars (self, xyVars: Tuple[str, str]):
        """ returns x,y polar of the tuple xyVars"""

        x, y = [], []
        
        if isinstance(xyVars, tuple):
            x = self._ofVar (xyVars[0])
            y = self._ofVar (xyVars[1])

            # sink polar - cut values <= 0 
            if SINK in xyVars: 
                i = 0 
                if SINK == xyVars[0]:
                    for i, val in enumerate(x):
                        if val > 0.0: break
                else: 
                    for i, val in enumerate(y):
                        if val > 0.0: break
                x = x[i:]
                y = y[i:]
        return x,y 



    def _get_values_forVar (self, var) -> list:
        """ copy vaues of var from op points to list"""

        nPoints = len(self.opPoints)
        if nPoints == 0: return [] 

        values  = [0] * nPoints
        op : OpPoint
        for i, op in enumerate(self.opPoints):
            values[i] = op.get_value (var)
        return values 


    def get_optValue (self, specVar, specVal, optVar):
        """ interpolates optvar in polar (specVar, optVar)"""

        if not self.isLoaded: return None

        specVals = self._ofVar (specVar)
        optVals  = self._ofVar (optVar)

        # find the index in self.x which is right before x
        jl = bisection (specVals, specVal)
        
        # now interpolate the y-value on lower side 
        if jl < (len(specVals) - 1):
            x1 = specVals[jl]
            x2 = specVals[jl+1]
            y1 = optVals[jl]
            y2 = optVals[jl+1]
            y = interpolate (x1, x2, y1, y2, specVal)
        else: 
            y = optVals[-1]

        if optVar == CD:
            y = round (y,5)
        else:
            y = round(y,2) 

        return y


    #--------------------------------------------------------

    
    def generate (self):
        """ 
        create polar from spline 
        """

        u = self._get_u_distribution (50)

        # x, y = self.spline.eval (u)
        x = u 
        y = self.spline.eval (u)

        self._set_var (self._xVar, x)
        self._set_var (self._yVar, y)
            
        return 

 

    def _get_u_distribution (self, nPoints):
        """ 
        returns u with nPoints 0..1
        """

        uStart = self._x[0] # 0.0
        uEnd   = self._x[-1] # 1.0
        u = np.linspace(uStart, uEnd , nPoints) 
        return u 