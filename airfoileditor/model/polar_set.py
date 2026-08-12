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

from .airfoil               import Airfoil, Flap_Definition
from .geometry_cst          import Geometry_CST
from .polar_dto             import Polar_Data_Set, Polar_File_Meta
from .xo2_driver            import Worker
from .nf_driver             import Neuralfoil_Evaluator, Airfoil_As_CST

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
    def list_small (cls) -> list['var']:
        """ returns a small list of main polar variables vars"""
        l = list (cls) [:]
        l.remove(var.CDF)
        l.remove(var.XTR)
        l.remove(var.BUBBLE_TOP)
        l.remove(var.BUBBLE_BOT)
        return l


    @override
    @classmethod
    def values (cls) -> list[str]:
        """ returns a list of all enum values as strings"""

        # exclude cdf (friction drag) from list of values
        val_list = super().values()
        val_list.remove("cdf")
        val_list.remove("xtr")
        val_list.remove("bubble_top")
        val_list.remove("bubble_bot")

        return val_list


    """ polar variables """
    ALPHA   = "alpha"               
    CL      = "cl"               
    CD      = "cd"               
    CDP     = "cdp"                                     # pressure drag
    CDF     = "cdf"                                     # friction drag
    GLIDE   = "cl/cd" 
    CM      = "cm"   
    CP_MIN  = "cp_min"
    RE_CALC = "Re"                                      # Reynolds number calculated for Type 2 polars
    SINK    = "sink"                                    # "cl^1.5/cd"              
    XTRT    = "xtrt"               
    XTRB    = "xtrb"    
    XTR     = "xtr"                                     # mean value of xtrt and xtrb (used by xo2)       
    BUBBLE_TOP      = "bubble_top"                      # bubble chord range on top side
    BUBBLE_BOT      = "bubble_bot"                      # bubble chord range on bottom side
    NF_CONFIDENCE   = "nf_confidence"                   # NeuralFoil prediction confidence [0..1]


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
    XTRIP_DEFAULT = 0.7                         # default xtript/xtripb for normal polars

    MAX_POLAR_DEFS  = 5                         # limit to check in App

    VAL_RANGE_ALPHA = [-4.0, 13.0, 0.3]         # default value range for alpha polar
    VAL_RANGE_CL    = [-0.2, 1.2, 0.05]


    POLAR_XFOIL      = 'XFOIL'                  # driver of polar calculation 
    POLAR_NEURALFOIL = 'NeuralFoil'


    @staticmethod
    def drivers () -> list[str]:
        """ list of available polar drivers (e.g. xfoil, neuralfoil)"""
        drivers = []
        if Worker.ready:
            drivers.append(Polar_Definition.POLAR_XFOIL)
        if Neuralfoil_Evaluator.ready:
            drivers.append(Polar_Definition.POLAR_NEURALFOIL)
        return drivers


    def __init__(self, dataDict : dict = None):
        
        self._nf_model_size = fromDict (dataDict, "nf_model_size", None)    # None → xfoil polar

        # sanity check for xfoil and neuralfoil availability
        if self.is_neuralfoil and not Neuralfoil_Evaluator.ready:
            self.set_is_xfoil(True)
            logger.warning (f"NeuralFoil is not available, switching to Xfoil polar")
        elif self.is_xfoil and not Worker.ready:
            self.set_is_neuralfoil(True)
            logger.info (f"Worker (Xfoil) is not available, switching to NeuralFoil polar")

        # init instance variables from dataDict or defaults

        self._autoRange = fromDict (dataDict, "autoRange",True)
        self._valRange  = fromDict (dataDict, "valRange", self.VAL_RANGE_ALPHA)
        if isinstance(self._valRange, tuple):
            self._valRange = list(self._valRange)
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
        if self._nf_model_size is not None:
            toDict (d, "nf_model_size", self._nf_model_size)
        return d


    def as_meta (self) -> Polar_File_Meta:
        """ polar parameters as a Polar_File_Meta DTO """
        flap = self._flap_def
        return Polar_File_Meta (
            nf_model_size = self._nf_model_size,
            polar_type  = str (self.type),
            re          = self.re,
            ma          = self.ma,
            ncrit       = self.ncrit,
            xtript      = self._xtript,
            xtripb      = self._xtripb,
            flap_angle  = flap.flap_angle  if flap else None,
            x_flap      = flap.x_flap      if flap else None,
            y_flap      = flap.y_flap      if flap else None,
            y_flap_spec = flap.y_flap_spec if flap else None,
            spec_var    = str (self.specVar),
            val_range   = tuple(self.valRange) if self.valRange is not None else None,
            auto_range  = self.autoRange,
        )
    
    
    def as_copy (self) -> 'Polar_Definition':
        """ return a copy of self """
        return Polar_Definition (dataDict=self._as_dict())


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
        if aVal is None or aVal == 1.0:
            self._xtript = None
        else:
            self._xtript = round (clip (aVal, 0.0, 1.0), 2)


    @property
    def xtripb (self) -> float:
        """ forced transition bottom side 0..1"""
        return self._xtripb if self._xtripb is not None else 1.0

    def set_xtripb (self, aVal : float):
        if aVal is None or aVal == 1.0:
            self._xtripb = None
        else:
            self._xtripb = round (clip (aVal, 0.0, 1.0), 2)

    @property
    def has_xtrip (self) -> bool:
        """ True if forced transition is set on top or bottom side"""
        return (self._xtript is not None) or (self._xtripb is not None)

    def set_has_xtrip (self, aBool : bool):
        if not aBool:
            self.set_xtript (None)
            self.set_xtripb (None)
        else:
            if self._xtript is None:
                self.set_xtript (self.XTRIP_DEFAULT)
            if self._xtripb is None:
                self.set_xtripb (self.XTRIP_DEFAULT)


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

        if self.is_neuralfoil:
            aVar = var.ALPHA                                            # NeuralFoil supports alpha sweep only

        if aVar in (var.ALPHA, var.CL) and self._specVar != aVar:
            self._specVar = aVar 
            if self._specVar == var.ALPHA:                              # reset value range only when changed
                self._valRange = self.VAL_RANGE_ALPHA.copy()
            else: 
                self._valRange = self.VAL_RANGE_CL.copy()

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

        if self.is_neuralfoil:
            aType = polarType.T1                    # NeuralFoil supports T1 only

        if isinstance (aType, polarType) and self._type != aType: 
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
        if isinstance(aRange, list) and len(aRange) == 3:
            self._valRange = aRange.copy()         # make a copy!
        elif isinstance(aRange, tuple) and len(aRange) == 3:
            self._valRange = list(aRange)


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
        if self.is_neuralfoil:
            self._ma = 0.0                          # NeuralFoil is incompressible
        else:
            mach = aMach if aMach is not None else 0.0 
            self._ma = clip (round(mach,2), 0.0, 1.0)


    @property
    def name (self): 
        """ returns polar name as a label  """

        text  = f"{self.type} Re{int(self.re/1000)}k"
        text += f" N{self.ncrit:.2f}".rstrip('0').rstrip('.')
        text += f" M{self.ma:.2f}".rstrip('0').rstrip('.') if self.ma else ""
        text += f" Trt{self._xtript:.0%}" if self._xtript is not None else ""
        text += f" Trb{self._xtripb:.0%}" if self._xtripb is not None else ""

        flap_def = self.flap_def
        if flap_def:
            text += f" F{flap_def.flap_angle:.1f}".rstrip('0').rstrip('.') +"°" if flap_def else ""
            text += f" H{flap_def.x_flap:.0%}" if flap_def.x_flap != 0.75 else ""

        text += " - NF" if self.is_neuralfoil else " - XFOIL"
        return text


    @property
    def name_long (self):
        """ returns polar extended name self represents """
        return f"{self.name}  {self.specVar}: {self.valRange_string}"    

    def name_with_v (self, chord : float):
        """ returns polar name with velocity for given chord """
        v = self.calc_v_for_chord(chord)
        return f"{self.name} | {v:.1f}m/s" if v is not None else self.name


    def is_equal_to (self, aDef: 'Polar_Definition', 
                     ignore_active=False, ignore_xtrip=False,
                     re_abs_tolerance: float | None = None) -> bool:
        """ True if aPolarDef is equals self"""

        if isinstance (aDef, Polar_Definition):
            if re_abs_tolerance is not None:
                if abs (self.re - aDef.re) > re_abs_tolerance:
                    return False

            self_dict = self._as_dict()
            aDef_dict = aDef._as_dict()

            if re_abs_tolerance is not None:
                self_dict.pop('re', None)
                aDef_dict.pop('re', None)

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
        if self.is_xfoil:
            self._flap_def = aDef
        else:
            self._flap_def = None                       # NeuralFoil does not support flaps


    @property
    def nf_model_size (self) -> str | None:
        """ NeuralFoil model size — None means this is an xfoil polar """
        return self._nf_model_size

    def set_nf_model_size (self, model_size: str | None):
        if model_size is not None and model_size not in Neuralfoil_Evaluator.available_model_sizes ():
            return
        self._nf_model_size = model_size
        if model_size is not None:                      # switching to NeuralFoil — enforce constraints
            self.set_type     (polarType.T1)            # T1 only (fixed Re sweep)
            self.set_specVar  (var.ALPHA)               # alpha sweep only
            self.set_ma       (0.0)                     # incompressible only
            self.set_flap_def (None)                    # no flap support

    @property
    def is_neuralfoil (self) -> bool:   
        return self._nf_model_size is not None

    def set_is_neuralfoil (self, aBool : bool):
        if aBool:
            self.set_nf_model_size (Neuralfoil_Evaluator.MODEL_SIZE_DEFAULT)
        else:
            self.set_nf_model_size (None)

    @property
    def is_xfoil (self) -> bool:        
        return self._nf_model_size is None

    def set_is_xfoil (self, aBool : bool):
        self.set_is_neuralfoil (not aBool)


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

        self._airfoil           = myAirfoil
        self._airfoil_as_CST    = None                  # CST repersentation of airfoil for NeuralFoil (lazy loaded)
        self._polars            = []                    # list of Polars of self is holding

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
        """ returns absolute path of airfoil used for polar generation"""

        if self.airfoil:
            if self.airfoil.isBezierBased:          # in case of Bezier we'll write only the .bez file 
                return self.airfoil.pathFileName_abs
            else:                                   # in all other cases .dat
                return self.airfoil.pathFileName_abs_dat
        else:
            return None     


    def airfoil_ensure_being_saved (self):
        """ check and ensure that airfoil is saved to file (Worker needs it)"""

        # worker can handle .dat and .bez files 
        if os.path.isfile (self.airfoil_pathFileName_abs) and not self.airfoil.isModified:
            pass 
        else: 
            if self.airfoil.isBezierBased:                      # for Bezier write only .bez - no dat
                self.airfoil.save(onlyShapeFile=True)
            else: 
                self.airfoil.save()
            logger.debug (f'Airfoil {self.airfoil_pathFileName_abs} saved for polar generation') 

    @property
    def airfoil_as_CST (self) -> Airfoil_As_CST | None:
        """ returns a CST representation of the airfoil for NeuralFoil """

        if self._airfoil_as_CST is None and self._airfoil is not None:

            w_upper, w_lower, le_weight, te_thickness, derotation_angle = Geometry_CST.geometry_as_CST (
                self._airfoil.geo, n_weights=8)

            self._airfoil_as_CST = Airfoil_As_CST(
                upper_weights       = w_upper,
                lower_weights       = w_lower,
                leading_edge_weight = le_weight,
                TE_thickness        = te_thickness,
                derotation_angle    = derotation_angle)

            logger.debug (f'Airfoil {self.airfoil} converted to CST. Derotation angle: {derotation_angle:.2f}°')
            
        return self._airfoil_as_CST

    @property
    def polars (self) -> list ['Polar']: 
        return self._polars


    @property
    def polars_VLM (self) -> list ['Polar']: 
        """ VLM polars of self which typically have a forced transition"""
        return [polar for polar in self.polars if polar.is_VLM_polar]


    @property
    def polars_normal (self) -> list ['Polar']: 
        """ normal polars of self which are not for VLM (forced transition)"""
        return [polar for polar in self.polars if not polar.is_VLM_polar]


    @property
    def has_polars_not_loaded (self) -> bool: 
        """ are there polars which are still not lazyloadeds when async polar generation """
        
        polars_not_loaded = [polar for polar in self.polars if not polar.isLoaded] 
        return len(polars_not_loaded) > 0
        
        
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
                self._add_polar_defs (vlm_polar_def, only_active=False)


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

        polars_to_add = []

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

                polars_to_add.append (new_polar)

        self.polars.extend(polars_to_add)


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


    def load_or_generate_polars (self, normal=True, VLM=True):
        """ 
        Either loads or (if not already exist) generate polars of myAirfoil 
            for normal and/or VVLM polars of self.
        """
        # select polars to be loaded/generated

        polars : list['Polar'] = []
        if normal:
            polars.extend (self.polars_normal)

        if VLM:
            polars.extend (self.polars_VLM)

        # load already existing polar file (xfoil) or generate and load polar (Neuralfoil)

        polars_not_loaded = []

        for polar in polars: 
            if not polar.isLoaded:

                polar.load_polar ()

                if polar.is_xfoil and not polar.isLoaded:
                    polars_not_loaded.append(polar)                         # lazy load failed - has to be generated

        # polars missing - if not already done, create polar_task for Worker to generate polar 

        if polars_not_loaded:

            self.airfoil_ensure_being_saved ()                                  # a real airfoil file needed

            all_polars_of_tasks = Polar_Task.get_polars_of_tasks ()
    
            # build polar tasks bundled for same ncrit, type, ... 

            new_tasks : list [Polar_Task] = []

            for polar in polars_not_loaded: 

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


    def reset_neuralfoil_polars (self):
        """ 
        Reset all NeuralFoil polars of self to be re-generated 
        (e.g. after flap setting)
        """
        polar: Polar
        for polar in self.polars:
            if polar.is_neuralfoil and polar.isLoaded:
                polar.unload ()

        # reset CST representation of airfoil for NeuralFoil
        self._airfoil_as_CST = None

#------------------------------------------------------------------------------


class Polar_Point:
    """ 
    A single point of a polar of an airfoil   

    airfoil 
        --> Polar_Set 
            --> Polar   (1..n) 
                --> Polar_Point  (1..n) 
    """
    def __init__(self, values: dict[var, np.ndarray] | None = None, index: int | None = None):
        """
        Main constructor for new opPoint 

        """
        self.spec   = var.ALPHA                         # self based on ALPHA or CL
        self.alpha : float = None
        self.cl    : float = None
        self.cd    : float = None
        self.cdp   : float = None
        self.cm    : float = None 
        self.cp_min: float = None
        self.xtrt  : float = None                       # transition top side
        self.xtrb  : float = None                       # transition bot side

        self.bubble_top : tuple = None                  # bubble top side (x_start, x_end)
        self.bubble_bot : tuple = None                  # bubble bot side (x_start, x_end)

        self.nf_confidence : float = None               # NeuralFoil confidence value for this point

        if values is not None and index is not None:
            self._set_from_values_cache (values, index)


    def _set_from_values_cache (self, values: dict[var, np.ndarray], index: int):
        """Load one operating point from cached polar value arrays."""

        self.alpha = values[var.ALPHA][index]
        self.cl = values[var.CL][index]
        self.cd = values[var.CD][index]
        self.cdp = values[var.CDP][index]
        self.cm = values[var.CM][index]
        self.cp_min = values[var.CP_MIN][index]
        self.xtrt = values[var.XTRT][index]
        self.xtrb = values[var.XTRB][index]
        self.bubble_top = values[var.BUBBLE_TOP][index]
        self.bubble_bot = values[var.BUBBLE_BOT][index]
        self.nf_confidence = values[var.NF_CONFIDENCE][index] 

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
        elif op_var == var.CDF:
            val = self.cdf
        elif op_var == var.CDP:
            val = self.cdp
        elif op_var == var.CL:
            val = self.cl
        elif op_var == var.ALPHA:
            val = self.alpha
        elif op_var == var.CM:
            val = self.cm
        elif op_var == var.CP_MIN:
            val = self.cp_min
        elif op_var == var.XTRT:
            val = self.xtrt
        elif op_var == var.XTRB:
            val = self.xtrb
        elif op_var == var.BUBBLE_TOP:
            val = self.bubble_top
        elif op_var == var.BUBBLE_BOT:
            val = self.bubble_bot
        elif op_var == var.GLIDE:
            val = self.glide
        elif op_var == var.RE_CALC:
            val = None                                              # not available here 
        elif op_var == var.SINK:
            val = self.sink
        elif op_var == var.XTR:
            val = self.xtr
        elif op_var == var.NF_CONFIDENCE:
            val = self.nf_confidence
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
        elif op_var == var.CP_MIN:
            self.cp_min = val
        elif op_var == var.XTRT:
            self.xtrt  = val
        elif op_var == var.XTRB:
            self.xtrb = val
        elif op_var == var.BUBBLE_TOP:
            self.bubble_top = val
        elif op_var == var.BUBBLE_BOT:
            self.bubble_bot = val
        else:
            raise ValueError (f"Op point variable '{op_var}' not supported")

    @classmethod
    def from_values (cls,
                     alpha: float = None,
                     cl: float = None,
                     cd: float = None,
                     cdp: float = None,
                     cm: float = None,
                     cp_min: float = None,
                     xtrt: float = None,
                     xtrb: float = None,
                     bubble_top: tuple = None,
                     bubble_bot: tuple = None) -> 'Polar_Point':
        """Alternate constructor: build a Polar_Point from cached values."""
        op = cls ()
        op.alpha  = alpha
        op.cl     = cl
        op.cd     = cd
        op.cdp    = cdp
        op.cm     = cm
        op.cp_min = cp_min
        op.xtrt   = xtrt
        op.xtrb   = xtrb
        op.bubble_top = bubble_top
        op.bubble_bot = bubble_bot
        return op


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
            _, x_end = self.bubble_bot
            return x_end >= min(1.0, self.xtrb + 0.02) and self.xtrb < 1.0
        else:
            return False
        
    @property
    def is_bubble_top_turbulent_separated (self) -> bool:
        """ True if top side has turbulent separated bubble """
        if self.bubble_top:
            _, x_end = self.bubble_top
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

        self._error_reason = None                           # if error occurred during polar generation 

        self._values : dict[var, np.ndarray] = {}           # cached polar values: var → array

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
            self.set_valRange   (polar_def.valRange)        # at the end to ensure correct specVar and autoRange are set first

            if re_scale is not None and re_scale != 1.0:                              # scale reynolds if requested
                re_scaled = round (self.re * re_scale / RE_SCALE_ROUND_TO, 0)
                re_scaled = re_scaled * RE_SCALE_ROUND_TO
                ma_scaled = round (self.ma * re_scale,  MA_SCALE_ROUND_DEC)
                self.set_re (re_scaled)
                self.set_ma (ma_scaled)
                self._re_scale  = 1.0                         # scale is now 1.0 again

            # sanity - no polar with flap angle == 0.0 
            if polar_def.flap_def and polar_def.flap_def.flap_angle != 0.0:
                self.set_flap_def   (copy (polar_def.flap_def))

            self.set_nf_model_size  (polar_def.nf_model_size)   # neuralfoil model size - None means xfoil polar


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


    def point_at (self, index: int) -> Polar_Point | None:
        """Return one Polar_Point view at index."""

        if index < 0 or index >= self._n_points:
            return None

        return self._make_point_at (index)


    @property
    def _n_points (self) -> int:
        """Number of cached operating points."""

        alpha = self._values.get (var.ALPHA)
        return len (alpha) if alpha is not None else 0


    def _make_point_at (self, index: int) -> Polar_Point:
        """Build one Polar_Point view from the cached value arrays."""

        return Polar_Point (self._values, index)
        
    @property
    def isLoaded (self) -> bool: 
        """ is polar data loaded from file (for async polar generation)"""
        return bool (self._values) or self.error_occurred
    
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
    def alpha (self) -> np.ndarray:     return self._ofVar (var.ALPHA)

    @property
    def cl (self) -> np.ndarray:        return self._ofVar (var.CL)

    @property
    def cd (self) -> np.ndarray:        return self._ofVar (var.CD)

    @property
    def cdp (self) -> np.ndarray:       return self._ofVar (var.CDP)

    @property
    def cdf (self) -> np.ndarray:       return self._ofVar (var.CDF)

    @property
    def glide (self) -> np.ndarray:     return self._ofVar (var.GLIDE)

    @property
    def sink (self) -> np.ndarray:      return self._ofVar (var.SINK)

    @property
    def re_calc (self) -> np.ndarray:   return self._ofVar (var.RE_CALC)

    @property
    def cm (self) -> np.ndarray:        return self._ofVar (var.CM)

    @property
    def cp_min (self) -> np.ndarray:    return self._ofVar (var.CP_MIN)

    @property
    def xtrt (self) -> np.ndarray:      return self._ofVar (var.XTRT)

    @property
    def xtrb (self) -> np.ndarray:      return self._ofVar (var.XTRB)

    @property
    def xtr (self) -> np.ndarray:       return self._ofVar (var.XTR)

    @property
    def bubble_top (self) -> np.ndarray:
        return self._ofVar (var.BUBBLE_TOP)

    @property
    def bubble_bot (self) -> np.ndarray:
        return self._ofVar (var.BUBBLE_BOT)

    @property
    def nf_confidence (self) -> np.ndarray: return self._ofVar (var.NF_CONFIDENCE)


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
        bubble_top = self._values.get (var.BUBBLE_TOP)
        return bool (bubble_top is not None and any (bubble_top))        
    
    @property
    def has_bubble_bot (self) -> bool:  
        """ True if bubble bot side is defined in any polar point """
        bubble_bot = self._values.get (var.BUBBLE_BOT)
        return bool (bubble_bot is not None and any (bubble_bot))


    def is_bubble_top_turbulent_separated_at (self, index: int) -> bool:
        """True if the top-side bubble at index is turbulent separated."""

        if index < 0 or index >= len (self.xtrt):
            return False

        bubble = self.bubble_top[index]
        if bubble:
            _, x_end = bubble
            return x_end >= min (1.0, self.xtrt[index] + 0.02) and self.xtrt[index] < 1.0
        else:
            return False


    def is_bubble_bot_turbulent_separated_at (self, index: int) -> bool:
        """True if the bottom-side bubble at index is turbulent separated."""

        if index < 0 or index >= len (self.xtrb):
            return False

        bubble = self.bubble_bot[index]
        if bubble:
            _, x_end = bubble
            return x_end >= min (1.0, self.xtrb[index] + 0.02) and self.xtrb[index] < 1.0
        else:
            return False


    @property
    def min_cd (self) -> Polar_Point:
        """ returns a Polar_Point at min cd - or None if not valid"""
        if np.any(self.cd):
            ip = np.argmin (self.cd)
            return self.point_at (ip)


    @property
    def max_glide (self) -> Polar_Point:
        """ returns a Polar_Point at max glide - or None if not valid"""
        if np.any(self.glide):
            ip = np.argmax (self.glide)
            return self.point_at (ip)

    @property
    def max_cl (self) -> Polar_Point:
        """ returns a Polar_Point at max cl - or None if not valid"""
        if np.any(self.cl):
            ip = np.argmax (self.cl)
            return self.point_at (ip)

    @property
    def min_cl (self) -> Polar_Point:
        """ returns a Polar_Point at min cl - or None if not valid"""
        if np.any(self.cl):
            ip = np.argmin (self.cl)
            return self.point_at (ip)


    @property
    def alpha0_lr (self) -> float:
        """ 
        alpha at cl=0 from linear regression of polar of alpha range around alpha0
            Use forced transition at 0.05 on upper and lower for good results
            ! no advantage in this case to alpha0 (linear interpolation)  !
        """
        if not np.any(self.cl) or not np.any(self.alpha): return None

        # define mask range around alpha0 for linear regression
        alpha_min = self.alpha0 - 2.0
        alpha_max = self.alpha0 + 4.0
        mask = (self.alpha >= alpha_min) & (self.alpha <= alpha_max)
        if np.sum(mask) < 2: return None                     # not enough points for linear regression

        cl_lr    = self.cl[mask]
        alpha_lr = self.alpha[mask]

        # do linear regression
        a, b = np.polyfit(alpha_lr, cl_lr, 1)
        alpha0_lr = -b / a

        return round(alpha0_lr, 2)


    @property
    def alpha0 (self) -> float:
        """ 
        alpha at cl=0 from linear interpolation of polar for cl=0
            Use forced transition at 0.05 on upper and lower for good results!
        """
        if np.any(self.cl) and np.any(self.alpha):
            return self.get_interpolated (var.CL, 0.0, var.ALPHA)
        else: 
            return None


    @property
    def cm_0 (self) -> float:
        """ returns cm at alpha=0 - or None if not valid"""
        if np.any(self.cm) and np.any(self.alpha):
            return self.get_interpolated (var.ALPHA, 0.0, var.CM)
        else:
            return None



    def ofVars (self, xyVars: Tuple[var, var]):
        """ returns x,y polar of the tuple xyVars"""
    
        if isinstance(xyVars, tuple):
            x = self._ofVar (xyVars[0])
            y = self._ofVar (xyVars[1])
        else:
            x, y = np.array([]), np.array([])
        return x,y 


    def _ofVar (self, polar_var: var) -> np.ndarray:
        """ return cached values for a polar variable """
        return self._values.get (polar_var, np.array([]))
        

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

        point_values = {xVar: xVal}

        # do not interpolate self 
        vars =  [var.CL, var.CD, var.CDP, var.ALPHA, var.CM, var.CP_MIN, var.XTRT, var.XTRB]
        if xVar in vars: vars.remove(xVar)

        # set other polar variables interpolated
        for yVar in vars:

            yVal = self.get_interpolated (xVar, xVal, yVar, allow_outside_range=allow_outside_range)

            if yVal is None:
                return None                                     # no interpolation possible     

            point_values[yVar] = yVal

        return Polar_Point.from_values (
            alpha = point_values.get (var.ALPHA),
            cl = point_values.get (var.CL),
            cd = point_values.get (var.CD),
            cdp = point_values.get (var.CDP),
            cm = point_values.get (var.CM),
            cp_min = point_values.get (var.CP_MIN),
            xtrt = point_values.get (var.XTRT),
            xtrb = point_values.get (var.XTRB),
        )


    @property
    def info_as_html (self) -> str:
        """ polar key values as HTML table for the click-info tooltip """

        def row (label: str, value: str, label_at : str=None, value_at: str=None) -> str:
            return (f"<tr>"
                    f"<td style='padding-right: 5px'>{label}</td>"
                    f"<td style='padding-right:10px'>{value}</td>"
                    f"<td style='padding-right: 5px'>{'at'     if label_at is not None else ''}</td>"
                    f"<td style='padding-right: 5px'>{label_at if label_at is not None else ''}</td>"
                    f"<td style='padding-right: 5px'>{value_at if value_at is not None else ''}</td>"
                    f"</tr>")

        rows = [
            row ("cl_max",     f"{self.max_cl.cl:.2f}",       "alpha", f"{self.max_cl.alpha:.2f}°"),
            row ("cd_min",     f"{self.min_cd.cd:.5f}",       "cl",    f"{self.min_cd.cl:.2f}"),
            row ("cl/cd max",  f"{self.max_glide.glide:.1f}", "cl",    f"{self.max_glide.cl:.2f}" ),
            row ("cm_0",       f"{self.cm_0:.3f}"),
            row ("alpha_0",    f"{self.alpha0:.2f}°"),
        ]

        html  = f"<b>{self.polar_set.airfoil.fileName}</b><br>"""
        html += f"{self.name}<br>"""
        html += f"<table>{''.join(rows)}</table>"
        return html



    #--------------------------------------------------------
   

    def load_polar (self):
        """ 
        Loads self from Xfoil polar file or evaluates via NeuralFoil.

        If loading could be done or error occurred, isLoaded will be True 
        """

        if self.isLoaded: return 

        try: 
            if self.is_xfoil:
                path = self.polar_set.airfoil_pathFileName_abs
                data_set = Worker.load_polar_data_set (path, self.as_meta())
            else:
                cst = self.polar_set.airfoil_as_CST
                data_set = Neuralfoil_Evaluator.get_polar_data_set (cst,
                                                                    self.as_meta(),
                                                                    model_size=self.nf_model_size)
            if data_set:
                self._import_from_data_set (data_set)
                logger.debug (f'{self} loaded for {self.polar_set.airfoil}') 

        except (RuntimeError) as exc:  

            self.set_error_reason (str(exc))                # polar will be 'loaded' with error
            logger.error (f'{self} load failed: {exc}')


    def unload (self):
        """ unloads self - clears cached polar values """
        self._values.clear ()
        self._error_reason = None


    def _import_from_data_set (self, data_set: Polar_Data_Set):
        """
        Map backend-agnostic polar DTO payload into cached arrays.
        """

        self._validate_data_set_meta (data_set)

        if not data_set.rows:
            raise RuntimeError("Could not map polar dataset")

        self._values.clear ()

        n_points = len (data_set.rows)

        self._values[var.ALPHA] = np.empty (n_points)
        self._values[var.CL] = np.empty (n_points)
        self._values[var.CD] = np.empty (n_points)
        self._values[var.CDP] = np.empty (n_points)
        self._values[var.CM] = np.empty (n_points)
        self._values[var.CP_MIN] = np.empty (n_points)
        self._values[var.XTRT] = np.empty (n_points)
        self._values[var.XTRB] = np.empty (n_points)
        self._values[var.BUBBLE_TOP] = np.empty (n_points, dtype=object)
        self._values[var.BUBBLE_BOT] = np.empty (n_points, dtype=object)
        self._values[var.NF_CONFIDENCE] = np.empty (n_points)

        for i, row in enumerate (data_set.rows):
            self._values[var.ALPHA][i] = row.alpha
            self._values[var.CL][i] = row.cl
            self._values[var.CD][i] = row.cd
            self._values[var.CDP][i] = row.cdp if row.cdp is not None else np.nan
            self._values[var.CM][i] = row.cm
            self._values[var.CP_MIN][i] = row.xf_cp_min if row.xf_cp_min is not None else np.nan
            self._values[var.XTRT][i] = row.xtrt
            self._values[var.XTRB][i] = row.xtrb
            self._values[var.BUBBLE_TOP][i] = (row.xf_bubble_top.x_start, row.xf_bubble_top.x_end) if row.xf_bubble_top else None
            self._values[var.BUBBLE_BOT][i] = (row.xf_bubble_bot.x_start, row.xf_bubble_bot.x_end) if row.xf_bubble_bot else None
            self._values[var.NF_CONFIDENCE][i] = row.nf_confidence if row.nf_confidence is not None else np.nan

        cl = self._values[var.CL]
        cd = self._values[var.CD]
        cdp = self._values[var.CDP]
        xtrt = self._values[var.XTRT]
        xtrb = self._values[var.XTRB]

        self._values[var.CDF] = cd - cdp
        self._values[var.XTR] = (xtrt + xtrb) / 2

        glide = np.zeros (n_points)
        glide_mask = (cd != 0.0) & (cl != 0.0)
        glide[glide_mask] = np.round (cl[glide_mask] / cd[glide_mask], 3)
        self._values[var.GLIDE] = glide

        sink = np.zeros (n_points)
        sink_mask = (cd > 0.0) & (cl >= 0.0)
        sink[sink_mask] = np.round (cl[sink_mask] ** 1.5 / cd[sink_mask], 3)
        self._values[var.SINK] = sink

        if self.type == polarType.T2:
            re_calc = np.zeros (n_points)
            if self.re:
                re_mask = cl != 0.0
                re_calc[re_mask] = self.re / np.sqrt (np.abs (cl[re_mask]))
        else:
            re_calc = np.full (n_points, self.re if self.re else 0.0)
        self._values[var.RE_CALC] = re_calc


    def _validate_data_set_meta (self, data_set: Polar_Data_Set):
        """Validate DTO metadata against this Polar definition where available."""

        my  = self.as_meta()
        got = data_set.meta
        mismatches = []

        if my.re         != got.re:          mismatches.append (f"Re {my.re} ≠ {got.re}")
        if my.ma         != got.ma:          mismatches.append (f"Ma {my.ma} ≠ {got.ma}")
        if my.polar_type != got.polar_type:  mismatches.append (f"type {my.polar_type} ≠ {got.polar_type}")
        if my.ncrit      != got.ncrit:       mismatches.append (f"Ncrit {my.ncrit} ≠ {got.ncrit}")
        if my.xtript     != got.xtript:      mismatches.append (f"xtript {my.xtript} ≠ {got.xtript}")
        if my.xtripb     != got.xtripb:      mismatches.append (f"xtripb {my.xtripb} ≠ {got.xtripb}")
        if got.flap_angle is not None and my.flap_angle != got.flap_angle:
            mismatches.append (f"flap_angle {my.flap_angle} ≠ {got.flap_angle}")
        if got.x_flap is not None and my.x_flap != got.x_flap:
            mismatches.append (f"x_flap {my.x_flap} ≠ {got.x_flap}")
        if got.y_flap is not None and my.y_flap != got.y_flap:
            mismatches.append (f"y_flap {my.y_flap} ≠ {got.y_flap}")

        if mismatches:
            msg = f"Polar Data Set does not match: {', '.join(mismatches)}"
            logger.error (msg)
            raise RuntimeError (msg)




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
                    polar.load_polar ()

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