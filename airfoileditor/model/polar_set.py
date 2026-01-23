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
from copy                   import copy 
from typing                 import Tuple, override
from enum                   import StrEnum

import numpy as np

from ..base.common_utils      import * 
from ..base.math_util         import * 
from ..base.spline            import Spline1D, Spline2D

from .airfoil               import Airfoil, Airfoil_Bezier
from .airfoil               import Flap_Definition
from .xo2_driver            import Worker, file_in_use   

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


#-------------------------------------------------------------------------------
# enums   
#-------------------------------------------------------------------------------

class StrEnum_Extended (StrEnum):
    """ enum extension to get a list of all enum values"""
    @classmethod
    def values (cls):
        return [c.value for c in cls]


class var (StrEnum_Extended):

    @classmethod
    def list_small (cls):
        """ returns a small list of main polar variables"""
        l = list (cls) [:]
        l.remove(var.CDF)
        l.remove(var.XTR)
        return l


    @override
    @classmethod
    def values (cls):
        """ returns a list of all enum values"""

        # exclude cdf (friction drag) from list of values
        val_list = super().values()
        val_list.remove("cdf")
        val_list.remove("xtr")

        return val_list


    """ polar variables """
    ALPHA   = "alpha"               
    CL      = "cl"               
    CD      = "cd"               
    CDP     = "cdp"                                     # pressure drag
    CDF     = "cdf"                                     # friction drag
    GLIDE   = "cl/cd" 
    CM      = "cm"   
    RE_CALC = "Re"                                      # Reynolds number calculated for Type 2 polars
    SINK    = "sink"                                    # "cl^1.5/cd"              
    XTRT    = "xtrt"               
    XTRB    = "xtrb"    
    XTR     = "xtr"                                     # mean value of xtrt and xtrb (used by xo2)       


class polarType (StrEnum_Extended):
    """ xfoil polar types """
    T1      = "T1"
    T2      = "T2"


SPEC_ALLOWED = [var.ALPHA, var.CL]

RE_SCALE_ROUND_TO  = 5000                               # round when polar is scaled down 
MA_SCALE_ROUND_DEC = 2


#--- Aero constants ---------------------------------------------------------------------------

TEMP_DEFAULT = 15                       # default temperature in °C
ALT_DEFAULT  = 0                        # default altitude in m (sea level)


def air_rho (temp_C = TEMP_DEFAULT, alt_m = ALT_DEFAULT) -> float: 
    """ 
    calc air density ρ (rho) in kg/m³ from temperature and altitude

    Args:   
        temp_C: temperature in °C
        alt_m: altitude in m
    """

    p = 101325 * (1 - 2.25577e-5 * alt_m)**5.25588      # calc pressure p in Pa
    t = temp_C + 273.15                                 # calc absolute temperature t in K
    
    rho = p / (287.05 * t)                              # calc air density ρ (rho) in kg/m³

    return round (rho, 3)


def air_eta (temp_C = TEMP_DEFAULT) -> float:
    """ 
    calc dynamic viscosity η (eta) in Pa·s (k/m.s) from temperature

    Args:   
        temp_C: temperature in °C
    """

    t = temp_C + 273.15                                 # calc absolute temperature t in K

    eta = 1.458e-6 * t**1.5 / (t + 110.4)               # Sutherland's formula

    return round(eta, 10)


def air_ny (temp_C = TEMP_DEFAULT, alt_m = ALT_DEFAULT) -> float:
    """ 
    calc kinematic viscosity ν (nu) in m²/s from temperature and altitude

    Args:   
        temp_C: temperature in °C
        alt_m: altitude in m
    """

    rho = air_rho (temp_C, alt_m)
    eta = air_eta (temp_C)

    ny = eta / rho 

    return round(ny, 10)


# convenience constants - at 15°C, sea level

AIR_RHO     = air_rho (temp_C = TEMP_DEFAULT, alt_m = ALT_DEFAULT)  # density air kg/m³ at 15°C, sea level
AIR_ETA     = air_eta (temp_C = TEMP_DEFAULT)                       # η dynamic viscosity air Pa·s (k/m.s) at 15°C, sea level
AIR_NY      = AIR_ETA / AIR_RHO                                     # ν kinematic viscosity air m²/s at 15°C, η = ν * ρ



#--- Re, Re*sqrt(CL), v ----------------------------------------------------------------


def re_from_v (v : float, chord : float, round_to = 1000) -> float:
    """ 
    calc Re number from v (velocity)
    
    Args:   
        v: velocity in m/s
        chord: chord length in m
        round_to: if int, will round the Re number to this value
    """

    re = round (v * chord * AIR_RHO / AIR_ETA,0)

    if isinstance (round_to, int) and round_to:
        re = round (re / round_to, 0)
        re = re * round_to

    return re


def v_from_re (re : float, chord : float, round_dec = 1) -> float:
    """ 
    calc v (velocity) from Renumber

    Args:   
        re: Reynolds number
        chord: chord length in m
        round_dec: if int, will round the velocity to this decimal places
    """

    v = re * AIR_ETA / (chord * AIR_RHO)

    if isinstance (round_dec, int):
        v = round (v, round_dec)

    return v


def re_sqrt_from_load (load : float, chord : float, round_to = 1000) -> float:
    """ 
    calc Re*sqrt(CL) from load (kg/m²)
    
    Args:   
        load: load in kg/m² = 10 * g/dm²
        chord: chord length in m
        round_to: if int, will round the Re number to this value
    """

    re_sqrt_cl = chord * np.sqrt(AIR_RHO) / AIR_ETA * np.sqrt(2 * 9.81 * load)
    re_sqrt_cl = round (re_sqrt_cl,0)

    if isinstance (round_to, int) and round_to:
        re_sqrt_cl = round (re_sqrt_cl / round_to, 0)
        re_sqrt_cl = re_sqrt_cl * round_to

    return re_sqrt_cl




def load_from_re_sqrt (re_sqrt_cl : float, chord : float, round_dec = None) -> float:
    """ 
    calc load (kg/m²) from Re*sqrt(CL)
    
    Args:   
        re_sqrt_cl: Re*sqrt(CL)
        chord: chord length in m
        round_to: if int, will round the load to this value
    """

    load = (re_sqrt_cl * AIR_ETA / (np.sqrt(AIR_RHO) * chord))**2  / (2 * 9.81)

    if isinstance (round_dec, int):
        load = round (load / round_dec, 0)
 
    return load 


#------------------------------------------------------------------------------


class Polar_Definition:
    """ 
    Defines the properties of a Polar (independent of an airfoil) 

    Polar_Definition
    Airfoil 
        |--- Polar_Set 
                |--- Polar    <-- Polar_Definition

    """
    XTRIP_VLM = 0.05                            # default xtript/xtripb for VLM sims

    MAX_POLAR_DEFS  = 5                         # limit to check in App

    VAL_RANGE_ALPHA = [-4.0, 13.0, 0.3]         # default value range for alpha polar
    VAL_RANGE_CL    = [-0.2, 1.2, 0.05]

    def __init__(self, dataDict : dict = None):
        
        self._autoRange = fromDict (dataDict, "autoRange",True)
        self._valRange  = fromDict (dataDict, "valRange", self.VAL_RANGE_ALPHA)
        self._specVar   = None 
        self.set_specVar (fromDict (dataDict, "specVar",  var.ALPHA))       # it is a enum
        self._type      = None 
        self.set_type    (fromDict (dataDict, "type",     polarType.T1))    # it is a enum

        self._ncrit     = fromDict (dataDict, "ncrit",    7.0)
        self._xtript    = fromDict (dataDict, "xtript",   None)             # forced transition top side
        self._xtripb    = fromDict (dataDict, "xtripb",   None)             # forced transition bot side

        self._re        = fromDict (dataDict, "re",       400000)             
        self._ma        = fromDict (dataDict, "mach",     0.0)

        flap_dict       = fromDict (dataDict, "flap",     None)
        self._flap_def  = Flap_Definition (dataDict=flap_dict) if flap_dict else None

        self._active    = fromDict (dataDict, "active",   True)             # a polar definition can be in-active

        self._is_mandatory = False                                          #  polar needed e.g. for xo2



    def __repr__(self) -> str:
        """ nice print string polarType and Re """
        return f"<{type(self).__name__} {self.name}>"

    # --- save --------------------- 

    def _as_dict (self):
        """ returns a data dict with the parameters of self """

        d = {}
        toDict (d, "type",           str(self.type))                    # type is enum
        toDict (d, "re",             self.re) 
        toDict (d, "ma",             self.ma) 
        toDict (d, "ncrit",          self.ncrit) 
        toDict (d, "specVar",        str(self.specVar))                 # specVar is enum
        toDict (d, "autoRange",      self.autoRange) 
        toDict (d, "valRange",       self.valRange) 
        toDict (d, "active",         self.active) 

        if self._xtript is not None:
            toDict (d, "xtript",    self._xtript)
        if self._xtripb is not None:
            toDict (d, "xtripb",    self._xtripb)

        if self._flap_def:
            toDict (d, "flap", self._flap_def._as_dict ())
        return d


    def _get_label (self, polarType, re : float, ma : float, 
                    ncrit : float, 
                    xtript: float | None, xtripb: float | None,
                    flap_def : Flap_Definition): 
        """ return a label of these polar variables"""
        ncirt_str  = f" N{ncrit:.2f}".rstrip('0').rstrip('.') 
        ma_str     = f" M{ma:.2f}".rstrip('0').rstrip('.') if ma else ""
        xtript_str = f" Trt{xtript:.0%}" if xtript is not None else ""
        xtripb_str = f" Trb{xtripb:.0%}" if xtripb is not None else ""

        if flap_def:
            flap_str  = f" F{flap_def.flap_angle:.1f}".rstrip('0').rstrip('.') +"°" if flap_def else ""
            flap_str += f" H{flap_def.x_flap:.0%}" if flap_def.x_flap != 0.75 else ""
        else:
            flap_str = ""

        return f"{polarType} Re{int(re/1000)}k{ma_str}{ncirt_str}{flap_str}{xtript_str}{xtripb_str}"
    

    @property
    def active (self) -> bool:
        """ True - self is in use"""
        return self._active 
    
    def set_active (self, aBool : bool):
        self._active = aBool == True 


    @property 
    def is_mandatory (self) -> bool:
        """ is self needed e.g. for Xoptfoil2"""
        return self._is_mandatory
    
    def set_is_mandatory (self, aBool):
        self._is_mandatory = aBool == True


    @property
    def ncrit (self) -> float:
        """ ncrit of polar""" 
        return self._ncrit
    def set_ncrit (self, aVal : float): 
        if aVal is not None and (aVal > 0.0 and aVal < 20.0):
            self._ncrit = aVal 


    @property
    def xtript (self) -> float:
        """ forced transition top side 0..1"""
        return self._xtript if self._xtript is not None else 1.0

    def set_xtript (self, aVal : float):
        if aVal is None:
            self._xtript = None
        else:
            xtript = round (clip (aVal, 0.0, 1.0), 2)
            self._xtript = xtript if xtript < 1.0 else None


    @property
    def xtripb (self) -> float:
        """ forced transition bottom side 0..1"""
        return self._xtripb if self._xtripb is not None else 1.0

    def set_xtripb (self, aVal : float):
        if aVal is None:
            self._xtripb = None
        else:
            xtripb = round (clip (aVal, 0.0, 1.0), 2)
            self._xtripb = xtripb if xtripb < 1.0 else None

    @property
    def has_xtrip (self) -> bool:
        """ True if forced transition is set on top or bottom side"""
        return (self.xtript < 1.0) or (self.xtripb < 1.0)

    @property
    def is_VLM_polar (self) -> bool:
        """ True if self is a VLM polar definition (xtript and xtripb set to default VLM values)"""
        return (self._xtript == self.XTRIP_VLM) and (self._xtripb == self.XTRIP_VLM)    


    @property
    def specVar (self): 
        """ ALPHA or CL defining value range"""
        return self._specVar
    
    def set_specVar (self, aVar : var): 
        """ set specVar by string or polarType"""

        if not isinstance (aVar, var):
            try:
                aVar = var(aVar)
            except ValueError:
                raise ValueError(f"{aVar} is not a valid specVar")
            
        if aVar == var.ALPHA or aVar == var.CL: 
            self._specVar = aVar 
            if self._specVar == var.ALPHA:                                       # reset value range 
                self._valRange = self.VAL_RANGE_ALPHA
            else: 
                self._valRange = self.VAL_RANGE_CL

    @property
    def type (self) -> polarType: 
        """ polarType.T1 or T2"""
        return self._type
    
    def set_type (self, aType : polarType | str):
        """ set polar type by string or polarType"""

        if not isinstance (aType, polarType):
            try:
                aType = polarType(aType)
            except ValueError:
                raise ValueError(f"{aType} is not a valid polar type")
            
        if isinstance (aType, polarType): 
            self._type = aType 
            # set specification variable depending on polar type 
            if self.type == polarType.T1:
                self.set_specVar (var.ALPHA)
            else: 
                self.set_specVar (var.CL)

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
        if self.specVar == var.ALPHA:
            aVal = clip (aVal, 0.1, 1.0)
        else: 
            aVal = clip (aVal, 0.01, 0.1)
        self._valRange[2] = aVal


    @property
    def re (self) -> float: 
        """ Reynolds number of polar - in case of Type 2 it is the Re*sqrt(cl)"""
        return self._re
    def set_re (self, re): 
        self._re = clip (re, 1000, 1e+8 - 1)

    @property
    def re_asK (self) -> int: 
        """ Reynolds number base 1000 - in case of Type 2 it is the Re*sqrt(cl)"""
        return int (self.re/1000) if self.re is not None else 0 
    def set_re_asK (self, aVal): 
        self.set_re (int(aVal) * 1000)


    @property
    def ma (self) -> float: 
        """ Mach number like 0.3"""
        return self._ma
    def set_ma (self, aMach):
        mach = aMach if aMach is not None else 0.0 
        self._ma = clip (round(mach,2), 0.0, 1.0)   


    @property
    def name (self): 
        """ returns polar name as a label  """
        return self._get_label (self.type, self.re, self.ma, self.ncrit, self._xtript, self._xtripb, self.flap_def)

    @property
    def name_long (self):
        """ returns polar extended name self represents """
        return f"{self.name}  {self.specVar}: {self.valRange_string}"    

    def name_with_v (self, chord : float):
        """ returns polar name with velocity for given chord """
        v = self.calc_v_for_chord(chord)
        return f"{self.name} | {v:.1f}m/s" if v is not None else self.name


    def is_equal_to (self, aDef: 'Polar_Definition', 
                     ignore_active=False, ignore_xtrip=False) -> bool:
        """ True if aPolarDef is equals self"""

        if isinstance (aDef, Polar_Definition):
            self_dict = self._as_dict()
            aDef_dict = aDef._as_dict()
            if ignore_active:
                self_dict.pop('active', None)
                aDef_dict.pop('active', None)
            if ignore_xtrip:
                self_dict.pop('xtript', None)
                self_dict.pop('xtripb', None)
                aDef_dict.pop('xtript', None)
                aDef_dict.pop('xtripb', None)
            return self_dict == aDef_dict
        else:
            return False

    def is_in (self, polar_defs : list['Polar_Definition']):
        """ True if self is already equal in list of polar definitions"""
        for polar_def in polar_defs:
            if self.is_equal_to (polar_def, ignore_active=True): return True 
        return False 


    @property
    def is_flapped (self) -> bool:
        """ True if self has a flap definition"""
        return isinstance (self._flap_def, Flap_Definition)
    
    def set_is_flapped (self, aBool : bool):
        if aBool: 
            self.set_flap_def (Flap_Definition())
        else: 
            self.set_flap_def (None)
    
    @property
    def flap_def (self) -> Flap_Definition:
        """ an optional flap definition of self"""
        return self._flap_def 
    
    def set_flap_def (self, aDef : Flap_Definition | None):
        self._flap_def = aDef


    def calc_v_for_chord (self, chord : float) -> float | None:
        """ 
        calc velocity for given chord length in mm based on Re
            - only for Type 1 polars 
            - rounded to 1 decimal place
        """

        if chord and self.type == polarType.T1:
            v = v_from_re (self.re, chord / 1000, round_dec=1) 
            return v 
        else:
            return None
        

#------------------------------------------------------------------------------

class Polar_Set:
    """ 
    Manage the polars of an airfoil   

    Polar_Definition

    Airfoil 
        |--- Polar_Set 
                |--- Polar    <-- Polar_Definition

    """

    instances : list ['Polar_Set']= []               # keep track of all instances created to reset 


    def __init__(self, myAirfoil: Airfoil, 
                 polar_def : Polar_Definition | list | None = None,
                 re_scale : float | None = None,
                 only_active : bool = False):
        """
        Main constructor for new polar set which belongs to an airfoil 

        Args:
            myAirfoil: the airfoil object it belongs to 
            polar_def: (list of) Polar_Definition to be added initially
            re_scale: will scale (down) all polars reynolds and mach number of self
            only_active: add only the 'active' polar definitions
        """

        self._airfoil = myAirfoil 
        self._polars = []                                   # list of Polars of self is holding

        re_scale = re_scale if re_scale is not None else 1.0 
        self._re_scale = clip (re_scale, 0.001, 100)

        self._add_polar_defs (polar_def, re_scale=self._re_scale, only_active=only_active)  # add initial polar def 


    def __repr__(self) -> str:
        """ nice representation of self """
        return f"<{type(self).__name__} of {self.airfoil}>"


    @property
    def airfoil (self) -> Airfoil: return self._airfoil

    @property
    def airfoil_pathFileName_abs (self) -> str:
        """ returns absolute path of airfoil"""
        abs_path = None
        if self.airfoil:
            abs_path = self.airfoil.pathFileName_abs

            # in case of Bezier we'll write only the .bez file 
            if self.airfoil.isBezierBased:
                abs_path = os.path.splitext(abs_path)[0] + Airfoil_Bezier.Extension

            # in case of hicks henne .dat is used 
            elif self.airfoil.isHicksHenneBased:
                abs_path = os.path.splitext(abs_path)[0] + Airfoil.Extension

        return abs_path


    def airfoil_ensure_being_saved (self):
        """ check and ensure that airfoil is saved to file (Worker needs it)"""

        if os.path.isfile (self.airfoil_pathFileName_abs) and not self.airfoil.isModified:
            pass 
        else: 
            if self.airfoil.isBezierBased:                      # for Bezier write only .bez - no dat
                self.airfoil.save(onlyShapeFile=True)
            else: 
                self.airfoil.save()
            logger.debug (f'Airfoil {self.airfoil_pathFileName_abs} saved for polar generation') 


    @property
    def polars (self) -> list ['Polar']: 
        return self._polars

    @property
    def polars_not_loaded (self) -> list ['Polar']: 
        """ not loaded polars of self """
        return list(filter(lambda polar: not polar.isLoaded, self.polars)) 


    @property
    def polars_VLM (self) -> list ['Polar']: 
        """ VLM polars of self which typically have a forced transition"""
        return list(filter(lambda polar: polar.is_VLM_polar, self.polars))


    @property
    def has_polars (self): return len (self.polars) > 0 
    

    @property
    def has_polars_not_loaded (self) -> bool: 
        """ are there polars which are still not lazyloadeds when async polar generation """
        return len(self.polars_not_loaded) > 0
        
    
    @property
    def has_all_polars_loaded (self) -> bool: 
        """ all polars are loaded """
        return not self.has_polars_not_loaded


    def set_polars_not_loaded (self):
        """ set all polars to not_loaded - so they will be refreshed with next access"""

        for i, polar in enumerate (self.polars[:]):
            
            self.polars[i] = Polar (self, polar, re_scale=polar.re_scale)

            # clean up old polar  
            polar.polar_set_detach ()
            Polar_Task.terminate_task_of_polar (polar) 
        
    @property
    def re_scale (self) -> float:
        """ scale factor for re of polars """
        return self._re_scale


    def is_equal_to (self, polar_set: 'Polar_Set'):
        """ True if polar_set has the same polars (defs) """

        if polar_set is None:
            return False
        
        if self.re_scale != polar_set.re_scale: 
            return False 
        
        if len(self.polars) == len(polar_set.polars):
            for i, polar in enumerate (self.polars):
                if not polar.is_equal_to (polar_set.polars[i], ignore_active=False):
                    return False
        else:
            return False 
        return True 


    def ensure_polars_VLM (self):
        """ ensure that every 'normal' polar has a sister VLM polar in self """

        polars_normal = list(filter(lambda polar: not polar.is_VLM_polar, self.polars))
        polars_VLM    = self.polars_VLM

        for polar in polars_normal:
            # is there already a VLM polar for this polar def ?
            has_vlm = False
            for vlm_polar in polars_VLM:
                if polar.is_equal_to (vlm_polar, ignore_active=True, ignore_xtrip=True):
                    has_vlm = True
                    break
            if not has_vlm:
                # create VLM polar def 
                vlm_polar_def = Polar_Definition(polar._as_dict())
                vlm_polar_def.set_xtript (Polar_Definition.XTRIP_VLM)
                vlm_polar_def.set_xtripb (Polar_Definition.XTRIP_VLM)

                # add VLM polar 
                self._add_polar_defs (vlm_polar_def, re_scale=self._re_scale, only_active=False)


    #---------------------------------------------------------------

    def _add_polar_defs (self, polar_defs, 
                        re_scale :float | None = None,
                        only_active : bool = False):
        """ 
        Adds polars based on a active polar_def to self.
        The polars won't be loaded (or generated) 

        polar_defs can be a list or a single Polar_Definition

        re_scale will scale (down) reynolds and mach number of all polars 
        only_active will add only the 'active' polar definitions
        """

        if isinstance(polar_defs, list):
            polar_def_list = polar_defs
        else: 
            polar_def_list = [polar_defs]

        # create polar for each polar definition 
        polar_def : Polar_Definition
        for polar_def in polar_def_list:

            # append new polar if it is active 
            if not only_active or (only_active and polar_def.active) or polar_def.is_mandatory:

                new_polar = Polar(self, polar_def, re_scale=re_scale)

                # is there already a similar polar - remove old one 
                for polar in self.polars[:]: 
                    if polar.name == new_polar.name: 
                        polar.polar_set_detach ()
                        self.polars.remove(polar)

                self.polars.append (new_polar)


    def remove_polars (self):
        """ Removes all polars of self  """
        polar: Polar
        for polar in self.polars[:]: 
            polar.polar_set_detach ()
            self.polars.remove(polar)


    def remove_polars_VLM (self):
        """ remove all VLM polars from self """
        polar: Polar
        for polar in self.polars[:]: 
            if polar.is_VLM_polar:
                polar.polar_set_detach ()
                self.polars.remove(polar)


    def load_or_generate_polars (self):
        """ 
        Either loads or (if not already exist) generate polars of myAirfoil 
            for all polars of self.
        """

        # load already existing polar files 

        self.load_polars ()

        # polars missing - if not already done, create polar_task for Worker to generate polar 

        if self.has_polars_not_loaded:

            self.airfoil_ensure_being_saved ()                                  # a real airfoil file needed

            all_polars_of_tasks = Polar_Task.get_polars_of_tasks ()
    
            # build polar tasks bundled for same ncrit, type, ... 

            new_tasks : list [Polar_Task] = []

            for polar in self.polars_not_loaded: 

                if not polar in all_polars_of_tasks:                            # ensure polar isn't already in any task 
                    taken_over = False
                    for task in new_tasks:
                        taken_over =  task.add_polar (polar)                    # try to add to existing task (same ncrit etc) 
                        if taken_over: break
                    if not taken_over:                                          # new task needed 
                        new_tasks.append(Polar_Task(polar))   

            # run all worker tasks - class Polar_Task and WatchDog will take care 

            for task in new_tasks:
                task.run ()

        return 


    def load_polars (self) -> int:
        """ 
        loads all polars which exist (now).
        Returns number of new loaded polars
        """

        nLoaded    = 0
        for polar in self.polars: 

            if not polar.isLoaded:
                polar.load_xfoil_polar ()

                if polar.isLoaded: 
                    nLoaded += 1

        return nLoaded


#------------------------------------------------------------------------------


class Polar_Point:
    """ 
    A single point of a polar of an airfoil   

    airfoil 
        --> Polar_Set 
            --> Polar   (1..n) 
                --> Polar_Point  (1..n) 
    """
    def __init__(self):
        """
        Main constructor for new opPoint 

        """
        self.spec   = var.ALPHA                         # self based on ALPHA or CL
        self.alpha : float = None
        self.cl    : float = None
        self.cd    : float = None
        self.cdp   : float = None
        self.cm    : float = None 
        self.xtrt  : float = None                       # transition top side
        self.xtrb  : float = None                       # transition bot side

        self.bubble_top : tuple = None                  # bubble top side (x_start, x_end)
        self.bubble_bot : tuple = None                  # bubble bot side (x_start, x_end)

    @property
    def cdf (self) -> float: 
        if self.cd and self.cdp:                  
            return self.cd - self.cdp                   # friction drag = cd - cdp 
        else: 
            return 0.0 

    @property
    def glide (self) -> float: 
        if self.cd and self.cl:                  
            return round(self.cl/self.cd,3)  
        else: 
            return 0.0 

    @property
    def sink (self) -> float: 
        if self.cd > 0.0 and self.cl >= 0.0:                  
            return round(self.cl**1.5 / self.cd,3)
        else: 
            return 0.0 

    @property
    def xtr (self) -> float: 
        return (self.xtrt + self.xtrb) / 2 


    def get_value (self, op_var : var) -> float:
        """ get the value of the opPoint variable with id"""

        if op_var == var.CD:
            val = self.cd
        elif op_var == var.CDP:
            val = self.cdp
        elif op_var == var.CDF:
            val = self.cdf
        elif op_var == var.CL:
            val = self.cl
        elif op_var == var.ALPHA:
            val = self.alpha
        elif op_var == var.CM:
            val = self.cm
        elif op_var == var.XTRT:
            val = self.xtrt
        elif op_var == var.XTRB:
            val = self.xtrb
        elif op_var == var.GLIDE:
            val = self.glide
        elif op_var == var.RE_CALC:
            val = None                                              # not available here 
        elif op_var == var.SINK:
            val = self.sink
        elif op_var == var.XTR:
            val = self.xtr
        else:
            raise ValueError (f"Op point variable '{op_var}' not known")
        return val 


    def set_value (self, op_var : var, val : float) -> float:
        """ set the value of the opPoint variable with var id"""

        if op_var == var.CD:
            self.cd = val
        elif op_var == var.GLIDE:
            self.cd = round_down(self.cl/val,6) if val != 0.0 else 0.0
        elif op_var == var.SINK:
            self.cd = round_down(self.cl**1.5/val,6) if val != 0.0 else 0.0
        elif op_var == var.CDP:
            self.cdp = val
        elif op_var == var.CL:
            self.cl = val
        elif op_var == var.ALPHA:
            self.alpha = val
        elif op_var == var.CM:
            self.cm = val
        elif op_var == var.XTRT:
            self.xtrt  = val
        elif op_var == var.XTRB:
            self.xtrb = val
        else:
            raise ValueError (f"Op point variable '{op_var}' not supported")

    @property
    def is_bubble_bot_turbulent_separated (self) -> bool:
        """ 
        True if bottom side has turbulent separated bubble 

        Laminar BL separates, transition happens while still separated (xtr), 
        but the flow stays separated even though it’s now turbulent and only reattaches further downstream.

        Effect: You now have a turbulent separated bubble over a longer chordwise distance. 
        That thick, separated shear layer produces a big momentum deficit and a fatter wake.

        Drag: Strongly higher—longer separated region, larger displacement thickness, 
        much more pressure drag.
        """
        if self.bubble_bot:
            x_start, x_end = self.bubble_bot
            return x_end >= min(1.0, self.xtrb + 0.02) and self.xtrb < 1.0
        else:
            return False
        
    @property
    def is_bubble_top_turbulent_separated (self) -> bool:
        """ True if top side has turbulent separated bubble """
        if self.bubble_top:
            x_start, x_end = self.bubble_top
            return x_end >= min(1.0, self.xtrt + 0.02) and self.xtrt < 1.0
        else:
            return False

#------------------------------------------------------------------------------


class Polar (Polar_Definition):
    """ 
    A single polar of an airfoil created by Worker

    Polar_Definition

    Airfoil 
        |--- Polar_Set 
                |--- Polar    <-- Polar_Definition
    """

    def __init__(self, mypolarSet: Polar_Set, 
                       polar_def : Polar_Definition = None, 
                       re_scale = 1.0):
        """
        Main constructor for new polar which belongs to a polar set 

        Args:
            mypolarSet: the polar set object it belongs to 
            polar_def: optional the polar_definition to initialize self definitions
            re_scale: will scale (down) polar reynolds and mach number of self

        """
        super().__init__()
        self._polar_set = mypolarSet
        self._re_scale  = re_scale

        self._error_reason = None                       # if error occurred during polar generation 

        self._polar_points = []                         # the single polar points of self
        self._alpha = None
        self._cl    = None
        self._cd    = None
        self._cdp   = None
        self._cdf   = None
        self._cm    = None 
        self._cd    = None 
        self._xtrt  = None
        self._xtrb  = None
        self._glide = None
        self._sink  = None
        self._re_calc = None

        if polar_def: 
            self.set_active     (polar_def.active)
            self.set_type       (polar_def.type)
            self.set_re         (polar_def.re)     
            self.set_ma         (polar_def.ma)
            self.set_ncrit      (polar_def.ncrit)
            self.set_xtript     (polar_def.xtript)
            self.set_xtripb     (polar_def.xtripb)
            self.set_autoRange  (polar_def.autoRange)
            self.set_specVar    (polar_def.specVar)
            self.set_valRange   (polar_def.valRange)

            if re_scale != 1.0:                              # scale reynolds if requested
                re_scaled = round (self.re * re_scale / RE_SCALE_ROUND_TO, 0)
                re_scaled = re_scaled * RE_SCALE_ROUND_TO
                ma_scaled = round (self.ma * re_scale,  MA_SCALE_ROUND_DEC)
                self.set_re (re_scaled)
                self.set_ma (ma_scaled)
                self._re_scale  = 1.0                         # scale is now 1.0 again

            # sanity - no polar with flap angle == 0.0 
            if polar_def.flap_def and polar_def.flap_def.flap_angle != 0.0:
                self.set_flap_def   (copy (polar_def.flap_def))

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
    def re_scale (self) -> float:
        """ scale value for reynolds number """
        return self._re_scale

    @property
    def polar_points (self) -> list [Polar_Point]:
        """ returns the sorted list of Polar_Points of self """
        return self._polar_points
        
    @property
    def isLoaded (self) -> bool: 
        """ is polar data loaded from file (for async polar generation)"""
        return len(self._polar_points) > 0 or self.error_occurred
    
    @property 
    def error_occurred (self) -> bool:
        """ True if error occurred during polar generation"""
        return self._error_reason is not None
    
    @property
    def error_reason (self) -> str:
        """ reason of error during polar generation """
        return self._error_reason

    def set_error_reason (self, aStr: str):
        self._error_reason = aStr


    @property
    def alpha (self) -> np.ndarray:
        if not np.any(self._alpha): self._alpha = self._get_values_forVar (var.ALPHA)
        return self._alpha
    
    @property
    def cl (self) -> np.ndarray:
        if not np.any(self._cl): self._cl = self._get_values_forVar (var.CL)
        return self._cl
    
    @property
    def cd (self) -> np.ndarray:
        if not np.any(self._cd): self._cd = self._get_values_forVar (var.CD)
        return self._cd
    
    @property
    def cdp (self) -> np.ndarray:
        if not np.any(self._cdp): self._cdp = self._get_values_forVar (var.CDP)
        return self._cdp
        
    @property
    def cdf (self) -> np.ndarray:
        if not np.any(self._cdf): self._cdf  = self._get_values_forVar (var.CDF)
        return self._cdf
        
    @property
    def glide (self) -> np.ndarray:
        if not np.any(self._glide): self._glide = self._get_values_forVar (var.GLIDE)
        return self._glide
    
    @property
    def sink (self) -> np.ndarray:
        if not np.any(self._sink): self._sink = self._get_values_forVar (var.SINK)
        return self._sink
    
    @property
    def re_calc (self) -> np.ndarray:
        if not np.any(self._re_calc): self._re_calc = self._get_values_forVar (var.RE_CALC)
        return self._re_calc

    @property
    def cm (self) -> np.ndarray:
        if not np.any(self._cm): self._cm = self._get_values_forVar (var.CM)
        return self._cm
    
    @property
    def xtrt (self) -> np.ndarray:
        if not np.any(self._xtrt): self._xtrt = self._get_values_forVar (var.XTRT)
        return self._xtrt
    
    @property
    def xtrb (self) -> np.ndarray:
        if not np.any(self._xtrb): self._xtrb = self._get_values_forVar (var.XTRB)
        return self._xtrb

    @property
    def xtr (self) -> np.ndarray:
        """ returns the average transition values of self """
        return (self.xtrb + self.xtrt) / 2.0


    @property
    def xtript_end_idx (self) -> int | None:
        """ 
        Last index where forced transition on top side is active.
        Forced region: [0:idx+1], Natural region: [idx+1:]
        Returns None if not defined.
        """

        if self.xtrt is None or len(self.xtrt) == 0 or self._xtript is None:
            return None

        # sanity - first xtrt value must be equal forced transition
        if not np.isclose(self.xtrt[0], self._xtript, atol=1e-5):
            return None

        # find last polar point with xtrt == forced transition
        for i, xtrt in enumerate (self.xtrt):
            if not np.isclose(xtrt, self._xtript, atol=1e-5):
                return i-1
        return None


    @property
    def xtripb_start_idx (self) -> int | None:
        """
        First index where forced transition on bottom side starts.
        Natural region: [0:idx], Forced region: [idx:]
        Returns None if not defined.
        """
        if self.xtrb is None or len(self.xtrb) == 0 or self._xtripb is None:
            return None

        # no sanity as xfoil shows bug here - sometimes last xtrb value isn't equal forced transition

        # find first polar point with xtrb == forced transition
        for i, xtrb in enumerate (self.xtrb):
            if np.isclose(xtrb, self._xtripb, atol=1e-5):
                return i
        return None


    @property
    def has_bubble_top (self) -> bool:
        """ True if bubble top side is defined in any polar point """
        return any (p.bubble_top for p in self.polar_points)        
    
    @property
    def has_bubble_bot (self) -> bool:  
        """ True if bubble bot side is defined in any polar point """
        return any (p.bubble_bot for p in self.polar_points)


    @property
    def min_cd (self) -> Polar_Point:
        """ returns a Polar_Point at min cd - or None if not valid"""
        if np.any(self.cd):
            ip = np.argmin (self.cd)
            # sanity for somehow valid polar 
            if self.type == polarType.T1:
                if ip > 2 and ip < (len(self.cd) - 1):
                    return self.polar_points [ip]
            else:
                if ip < (len(self.cd) - 1):
                    return self.polar_points [ip]


    @property
    def max_glide (self) -> Polar_Point:
        """ returns a Polar_Point at max glide - or None if not valid"""
        if np.any(self.glide):
            ip = np.argmax (self.glide)
            # sanity for somehow valid polar 
            if ip > 2 and ip < (len(self.glide) - 3):
                return self.polar_points [ip]


    @property
    def max_cl (self) -> Polar_Point:
        """ returns a Polar_Point at max cl - or None if not valid"""
        if np.any(self.cl):
            ip = np.argmax (self.cl)
            # sanity for somehow valid polar 
            if ip > (len(self.cl) - 5):
                return self.polar_points [ip]


    @property
    def min_cl (self) -> Polar_Point:
        """ returns a Polar_Point at max cl - or None if not valid"""
        if np.any(self.cl):
            ip = np.argmin (self.cl)
            # sanity for somehow valid polar 
            if ip < (len(self.cl) - 5):
                return self.polar_points [ip]


    @property
    def alpha_cl0_inviscid (self) -> float:
        """ - don't use it... inviscid alpha_cl0 extrapolated from linear part of polar """
        if not np.any(self.cl) or not np.any(self.alpha): return None

        cl_alpha2 = self.get_interpolated (var.ALPHA, 2.0, var.CL)
        cl_alpha4 = self.get_interpolated (var.ALPHA, 4.0, var.CL)

        alpha_cl0 = interpolate (cl_alpha2, cl_alpha4, 2.0, 4.0, 0.0)
        return round(alpha_cl0,2)


    @property
    def alpha_cl0_lr (self) -> float:
        """ 
        alpha at cl=0 from linear regression of polar of alpha range around alpha0
            Use forced transition at 0.05 on upper and lower for good results
            ! no advantage in this case to alpha_cl0 (linear interpolation)  !
        """
        if not np.any(self.cl) or not np.any(self.alpha): return None

        # define mask range around alpha0 for linear regression
        alpha_min = self.alpha_cl0 - 2.0
        alpha_max = self.alpha_cl0 + 4.0
        mask = (self.alpha >= alpha_min) & (self.alpha <= alpha_max)
        if np.sum(mask) < 2: return None                     # not enough points for linear regression

        cl_lr    = self.cl[mask]
        alpha_lr = self.alpha[mask]

        # do linear regression
        a, b = np.polyfit(alpha_lr, cl_lr, 1)
        alpha_cl0 = -b / a

        return round(alpha_cl0, 2)


    @property
    def alpha_cl0 (self) -> float:
        """ 
        alpha at cl=0 from linear interpolation of polar for cl=0
            Use forced transition at 0.05 on upper and lower for good results!
        """
        if np.any(self.cl) and np.any(self.alpha):
            return self.get_interpolated (var.CL, 0.0, var.ALPHA)
        else: 
            return None


    def ofVars (self, xyVars: Tuple[var, var]):
        """ returns x,y polar of the tuple xyVars"""

        x, y = [], []
        
        if isinstance(xyVars, tuple):
            x = self._ofVar (xyVars[0])
            y = self._ofVar (xyVars[1])

            # sink polar - cut values <= 0 
            if var.SINK in xyVars: 
                i = 0 
                if var.SINK == xyVars[0]:
                    for i, val in enumerate(x):
                        if val > 0.0: break
                else: 
                    for i, val in enumerate(y):
                        if val > 0.0: break
                x = x[i:]
                y = y[i:]
        return x,y 

    # -----------------------

    def _ofVar (self, polar_var: var):

        vals = []
        if   polar_var == var.CL:
            vals = self.cl
        elif polar_var == var.CD:
            vals = self.cd
        elif polar_var == var.CDP:
            vals = self.cdp
        elif polar_var == var.CDF:
            vals = self.cdf
        elif polar_var == var.ALPHA:
            vals = self.alpha
        elif polar_var == var.GLIDE:
            vals = self.glide
        elif polar_var == var.RE_CALC:
            vals = self.re_calc
        elif polar_var == var.SINK:
            vals = self.sink
        elif polar_var == var.CM:
            vals = self.cm
        elif polar_var == var.XTRT:
            vals = self.xtrt
        elif polar_var == var.XTRB:
            vals = self.xtrb
        elif polar_var == var.XTR:
            vals = self.xtr
        else:
            raise ValueError ("Unknown polar variable: %s" % polar_var)
        return vals
    

    def _get_values_forVar (self, op_var) -> np.ndarray:
        """ copy values of var from op points to array"""

        nPoints = len(self.polar_points)
        if nPoints == 0: return np.array([]) 

        values = np.zeros (nPoints)
        for i, op in enumerate(self.polar_points):

            if op_var == var.RE_CALC:                                   # special case for re_calc    
                values[i] = self._re_calc_for_op (op)
            else:
                values[i] = op.get_value (op_var)
        return values 


    def _re_calc_for_op (self, op : Polar_Point) -> float:
        """ returns the re_calc value for a single polar point"""

        if self.type == polarType.T2:
            if op.cl and self.re:
                return self.re / np.sqrt(abs(op.cl))
            else:
                return 0.0      
        else:
            return self.re if self.re else 0.0
        

    def get_interpolated (self, xVar : var, xVal : float, yVar : var,
                          allow_outside_range = False) -> float:
        """
        Interpolates yVar in polar (xVar, yVar) - returns None if not successful
           allow_outside_range = True will return the y value at the boundaries 
        """

        if not self.isLoaded: return None

        xVals = self._ofVar (xVar)
        yVals = self._ofVar (yVar)

        # find the index in xVals which is right before x
        i = bisection (xVals, xVal)
        
        # now interpolate the y-value  
        if i < (len(xVals) - 1) and i >= 0:
            x1 = xVals[i]
            x2 = xVals[i+1]
            y1 = yVals[i]
            y2 = yVals[i+1]
            y = interpolate (x1, x2, y1, y2, xVal)
            y = round (y,5) if yVar == var.CD else round(y,3)

        elif allow_outside_range:
            y = yVals[0] if i < 0 else yVals[-1]                    # see return values of bisection

        else: 
            y = None

        return y




    def get_interpolated_point (self, xVar : var, xVal : float, allow_outside_range = False) -> Polar_Point:
        """
        Returns an interpolated Polar_Point for xVar at xVal.
            If not successful, None is returned.
        allow_outside_range = True will return the point at the boundaries"""

        if not self.isLoaded: return None

        point = Polar_Point()
        point.set_value (xVar, xVal)                            # set xVar value in point

        # do not interpolate self 
        vars =  [var.CL, var.CD, var.CDP, var.ALPHA, var.CM, var.XTRT, var.XTRB]
        if xVar in vars: vars.remove(xVar)

        # set other polar variables interpolated
        for yVar in vars:

            yVal = self.get_interpolated (xVar, xVal, yVar, allow_outside_range=allow_outside_range)

            if yVal is None:
                return None                                     # no interpolation possible     
            
            point.set_value (yVar, yVal)

        return point



    #--------------------------------------------------------
   

    def load_xfoil_polar (self):
        """ 
        Loads self from Xfoil polar file.

        If loading could be done or error occurred, isLoaded will be True 
        """

        if self.isLoaded: return 

        try: 
            # polar file existing?  - if yes, load polar
            if self.is_flapped:
                flap_angle  = self.flap_def.flap_angle 
                x_flap      = self.flap_def.x_flap
                y_flap      = self.flap_def.y_flap
                y_flap_spec = self.flap_def.y_flap_spec
            else:
                flap_angle  = None 
                x_flap      = None
                y_flap      = None
                y_flap_spec = None

            airfoil_pathFileName = self.polar_set.airfoil_pathFileName_abs
            polar_pathFileName   = Worker.get_existingPolarFile (airfoil_pathFileName, 
                                                self.type, self.re, self.ma, 
                                                self.ncrit, self._xtript, self._xtripb,
                                                flap_angle, x_flap, y_flap, y_flap_spec)

            if polar_pathFileName and not file_in_use (polar_pathFileName): 

                self._import_from_file(polar_pathFileName)
                logger.debug (f'{self} loaded for {self.polar_set.airfoil}') 

        except (RuntimeError) as exc:  

            self.set_error_reason (str(exc))                # polar will be 'loaded' with error


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
                airfoilname = splitline[1].strip()
            # scan for Re-Number and ncrit
            if  line.find(reTag) >= 0:
                splitline = line.split(reTag)
                splitline = splitline[1].split(ncritTag)

                re_string    = splitline[0].strip()
                splitstring = re_string.split("e")
                factor = float(splitstring[0].strip())
                Exponent = float(splitstring[1].strip())
                re = factor * (10**Exponent)

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
                    op = Polar_Point ()
                    op.alpha = float(dataPoints[0])
                    op.cl    = float(dataPoints[1])
                    op.cd    = float(dataPoints[2])
                    op.cdp   = float(dataPoints[3])
                    op.cm    = float(dataPoints[4])
                    op.xtrt  = float(dataPoints[5])
                    op.xtrb  = float(dataPoints[6])

                    # optional bubble start-end on top and bot 
                    if len(dataPoints) == 11:

                        bubble_def = (float(dataPoints[7]), float(dataPoints[8]))
                        op.bubble_top = bubble_def if bubble_def[0] > 0.0 and bubble_def[1] > 0.0 else None

                        bubble_def = (float(dataPoints[9]), float(dataPoints[10]))
                        op.bubble_bot = bubble_def if bubble_def[0] > 0.0 and bubble_def[1] > 0.0 else None

                    opPoints.append(op)
        fpolar.close()

        if len(opPoints) > 0: 

            self._polar_points = opPoints

        else: 
            logger.error (f"{self} - import from {polarPathFileName} failed")
            raise RuntimeError(f"Could not read polar file" )
 


#------------------------------------------------------------------------------


class Polar_Task:
    """ 
    Single Task for Worker to generate polars based on parameters
    May generate many polars having same ncrit and type    

    Polar_Definition

    Airfoil 
        |--- Polar_Set 
                |--- Polar    <-- Polar_Definition
                |--- Polar_Worker_Task
    """

    instances : list ['Polar_Task']= []                 # keep track of all instances created to reset 

    def __init__(self, polar: Polar =None):
        
        self._autoRange  = None
        self._specVar    = None
        self._valRange   = None
        self._type       = None 
        self._re         = []             
        self._ma         = []

        self._ncrit      = None
        self._xtript     = None                         # forced transition top side
        self._xtripb     = None                         # forced transition bot side

        self._flap_def   = None
        self._x_flap     = None
        self._y_flap     = None
        self._y_flap_spec= None
        self._flap_angle = []

        self._flap_def   = None

        self._nPoints    = None                         # speed up polar generation with limited coordinate points

        self._polars : list[Polar] = []                 # my polars to generate 
        self._myWorker   = None                         # Worker instance which does the job
        self._finalized  = False                        # worker has done the job  

        self._airfoil_pathFileName_abs = None           # airfoil file 

        if polar:
            self.add_polar (polar) 

        Polar_Task._add_to_instances (self) 


    def __repr__(self) -> str:
        """ nice representation of self """
        return f"<{type(self).__name__} of {self._type} Re {self._re} Ma {self._ma} Ncrit {self._ncrit} Flap {self._flap_angle}>"

    #---------------------------------------------------------------

    @classmethod
    def _add_to_instances (cls , aTask : 'Polar_Task'):
        """ add aTask to instances"""

        cls.instances.append (aTask)


    @classmethod
    def get_instances (cls) -> list ['Polar_Task']:
        """ removes finalized instances and returns list of active instances"""

        n_running   = 0 
        n_finalized = 0 

        for task in cls.instances [:]:                              # copy as we modify list 
            if task.isRunning():
                n_running += 1
            elif task._finalized:                                   # task finalized - remove from list 
                n_finalized += 1
                cls.instances.remove (task)

        if len (cls.instances):
            logger.debug (f"-- {cls.__name__} {len (cls.instances)} instances, {n_running} running, {n_finalized} finalized")

        return cls.instances


    @classmethod
    def get_polars_of_tasks (cls) -> list ['Polar']:
        """ list of all polars which are currently in tasks"""

        polars = []

        for task in cls.get_instances():
            polars.extend (task._polars)
        return polars


    @classmethod
    def get_total_n_polars_running (cls) -> int:
        """ total number of polars being generated in all tasks"""

        nPolarsRunning = 0

        for task in cls.get_instances():
            nPolarsRunning += task.n_polars_running
        return nPolarsRunning


    @classmethod
    def terminate_task_of_polar (cls, polar : Polar) -> 'Polar_Task':
        """ if polar is in a Task, terminate Task"""

        for task in cls.get_instances():
            if polar in task._polars:
                task.terminate()


    @classmethod
    def terminate_instances_except_for (cls, airfoils):
        """ terminate all polar tasks except for 'airfoil' and Designs"""

        tasks = cls.get_instances () 

        for task in tasks: 

            airfoil = task._polars[0].polar_set.airfoil             # a bit complicated to get airfoil of task 

            if (not airfoil in airfoils) and (not airfoil.usedAsDesign): 
                task.terminate()                                    # will kill process 


    #---------------------------------------------------------------

    @property
    def n_polars (self) -> int:
        """ number of polars of self should generate"""
        return len(self._polars)

    @property
    def n_polars_running (self) -> int:
        """ number of polars of self which are still running"""
        nRunning = 0
        for polar in self._polars:
            if not polar.isLoaded:
                nRunning += 1
        return nRunning
    

    def add_polar (self, polar : Polar) -> bool:
        """
        add (another) polar which fits for self (polar type, ncrit, ... are the same)
        Returns True if polar is taken over by self
        """    

        # sanity - - polar already generated and loaded 
        if polar.isLoaded: return  

        taken_over = True 
        
        if not self._re: 
            self._autoRange  = polar.autoRange
            self._specVar    = polar.specVar
            self._valRange   = polar.valRange
            self._type       = polar.type
        
            self._re         = [polar.re]             
            self._ma         = [polar.ma]

            self._ncrit      = polar.ncrit
            self._xtript     = polar._xtript                    # use instance variables to allow None
            self._xtripb     = polar._xtripb                    # use instance variables to allow None

            self._flap_def   = polar.flap_def
            self._x_flap     = polar.flap_def.x_flap      if polar.flap_def else None
            self._y_flap     = polar.flap_def.y_flap      if polar.flap_def else None
            self._y_flap_spec= polar.flap_def.y_flap_spec if polar.flap_def else None
            self._flap_angle = [polar.flap_def.flap_angle] if polar.flap_def else []

            self._polars     = [polar]
            self._airfoil_pathFileName_abs = polar.polar_set.airfoil_pathFileName_abs

        # collect all polars with same type, ncrit, xtript, xtripb, specVar, valRange 
        # to allow Worker multi-threading 
        elif  self._type==polar.type and self._ncrit == polar.ncrit and \
              self._xtript == polar._xtript and self._xtripb == polar._xtripb and \
              self._autoRange == polar.autoRange and \
              self._specVar == polar.specVar and self._valRange == polar.valRange and \
              Flap_Definition.have_same_hinge (self._flap_def, polar.flap_def):
            
            self._re.append (polar.re)
            self._ma.append (polar.ma)
            if polar.is_flapped:
                self._flap_angle.append (polar.flap_def.flap_angle)

            self._polars.append (polar)

        else: 
            taken_over = False

        return taken_over 


    def run (self):
        """ run worker to generate self polars"""

        self._myWorker = Worker ()

        try:
            self._myWorker.generate_polar (self._airfoil_pathFileName_abs, 
                        self._type, self._re, self._ma, self._ncrit, 
                        xtript=self._xtript, xtripb=self._xtripb,
                        autoRange=self._autoRange, spec=self._specVar, 
                        valRange=self._valRange, run_async=True,
                        flap_angle=self._flap_angle, x_flap=self._x_flap, y_flap=self._y_flap, 
                        y_flap_spec=self._y_flap_spec, 
                        nPoints=self._nPoints)
            logger.debug (f"{self} started")


        except Exception as exc:

            logger.warning (f"{self} - polar generation failed - error: {exc}")
            for polar in self._polars:
                polar.set_error_reason (str(exc))
            self.finalize ()


    def terminate (self):
        """ kill an active workerpolar generation """
        if self._myWorker and self.isRunning():
            logger.warning (f"terminating {self}")
            self._myWorker.terminate()
        self.finalize ()


    def finalize (self):
        """ all polars generated - worker clean up """

        if self._myWorker:
            self._myWorker.finalize ()
            self._myWorker = None 

        self._finalized = True 
        self._polars    = []


    def isRunning (self) -> bool:
        """ is worker still running"""
        return self._myWorker.isRunning() if self._myWorker else False


    def isCompleted (self) -> bool:
        """ True if all polars of self are loaded"""
        for polar in self._polars:
            if not polar.isLoaded: return False
        return True 



    def load_polars (self) -> int:
        """ 
        Tries to load new generated of self polars of Worker
            Returns number of newly loaded polars
        """

        if self.isRunning():   return 0                           # if worker is still working return 

        # get worker returncode 
        worker_returncode = self._myWorker.finished_returncode if self._myWorker else 0

        nLoaded    = 0
        for polar in self._polars:

            if not polar.isLoaded:
                if worker_returncode:
                    # set error into polar - will be 'loaded'
                    polar.set_error_reason (self._myWorker.finished_errortext)
                else: 
                    # load - if error occurs, error_reason will be set 
                    polar.load_xfoil_polar ()

                if polar.isLoaded: 
                    nLoaded += 1           

        return nLoaded



# ------------------------------------------



class Polar_Splined (Polar_Definition):
    """ 
    A single polar of an airfoil splined on basis of control points 

    Airfoil 
        --> Polar_Set 
            --> Polar   
    """

    def __init__(self, mypolarSet: Polar_Set, polar_def : Polar_Definition = None):
        """
        Main constructor for new polar which belongs to a polar set 

        Args:
            mypolarSet: the polar set object it belongs to 
            polar_def: optional the polar_definition to initialize self deinitions
        """
        super().__init__()

        self._polar_set = mypolarSet

        self._polar_points = []                     # the single oppoints of self
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

        logger.debug (f"spline x: {self._xVar}   y: {self._yVar}")

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
            logger.debug (f"{self} New {boundary} spline with {len (self._x)} knots")
        return self._spline


    @property
    def opPoints (self) -> list:
        """ returns the sorted list of opPoints of self """
        return self._polar_points
    
    
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
    
    def ofVars (self, xyVars: Tuple[var, var]):
        """ returns x,y polar of the tuple xyVars"""

        x, y = [], []
        
        if isinstance(xyVars, tuple):
            x = self._ofVar (xyVars[0])
            y = self._ofVar (xyVars[1])

            # sink polar - cut values <= 0 
            if var.SINK in xyVars: 
                i = 0 
                if var.SINK == xyVars[0]:
                    for i, val in enumerate(x):
                        if val > 0.0: break
                else: 
                    for i, val in enumerate(y):
                        if val > 0.0: break
                x = x[i:]
                y = y[i:]
        return x,y 


    def _get_values_forVar (self, var) -> list:
        """ copy values of var from op points to list"""

        nPoints = len(self.opPoints)
        if nPoints == 0: return [] 

        values  = [0] * nPoints
        op : Polar_Point
        for i, op in enumerate(self.opPoints):
            values[i] = op.get_value (var)
        return values 


    def get_interpolated_val (self, specVar, specVal, optVar):
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

        if optVar == var.CD:
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