#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Geometry of an Hicks Henne based Airfoil  

    Implements a kind of 'strategy pattern' for the different approaches how 
    the geometry of an airfoil is determined and modified:

"""

import numpy as np

from ..base.math_util       import * 
from ..base.spline          import HicksHenne

from .airfoil_geometry      import Geometry, Line

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)



class Side_Airfoil_HicksHenne (Line): 
    """ 
    1D line of an airfoil like upper, lower side based on a seed and hh bump functions
    """

    isHicksHenne    = True

    def __init__ (self, seed_x, seed_y, hhs, **kwargs):
        """
        1D line of an airfoil like upper, lower side based on a seed and hh bump functions

        Parameters
        ----------
        seed_x, seed_y : coordinates of side 1 line, x = 0..1 
        hhs : list of hicks henne functions  
        """

        super().__init__(None, None, **kwargs)

        if not hhs:
            self._hhs = []
        else:
            self._hhs = hhs                         # the hicks henne functions

        if seed_x is None or seed_y is None:
            raise ValueError ("seed coordinates for hicks henne side are missing")
        else:
            self._seed_x    = seed_x            
            self._seed_y    = seed_y            


    @property
    def hhs(self) -> list:
        """ returns the hicks henne functions of self"""
        return self._hhs

    def set_hhs (self, hhs : list):
        """ set the hicks henne functions of self"""
        self._hhs = hhs

    @property
    def nhhs (self): 
        """ number of hicks henne functions """
        return len(self.hhs)


    @property
    def x (self) -> np.ndarray:
        # overloaded - master is seed 
        return self._seed_x
    
    @property
    def y (self)  -> np.ndarray: 
        # overloaded  - sum up hicks henne functions to seed_y

        if isinstance(self._y, np.ndarray) and not self._y.any(): 
            self._y = self._seed_y
            hh : HicksHenne

            for hh in self._hhs: 
                self._y = self._y + hh.eval (self.x)

        return self._y
        # return self._seed_y

    # ------------------


class Geometry_HicksHenne (Geometry): 
    """ 
    Geometry based on a seed airfoil and hicks henne bump (hh) functions for upper and lower side 
    """
    
    isBasic         = False 
    isHicksHenne    = True
    description     = "based on a seed and hicks henne functions"

    side_class = Line

    def __init__ (self, seed_x : np.ndarray, seed_y : np.ndarray, **kwargs):
        """new Geometry based on a seed airfoil and hicks henne bump (hh) functions for upper and lower side"""
        super().__init__(None, None, **kwargs)        

        self._seed_x     = seed_x
        self._seed_y     = seed_y 
        self._upper      = None                 # upper side as Side_Airfoil_HicksHenne object
        self._lower      = None                 # lower side 

    @property
    def upper(self) -> 'Side_Airfoil_HicksHenne': 
        """the upper surface as a Side_Airfoil_HicksHenne object - where x 0..1"""
        # overloaded
        if self._upper is None: 
            iLe = int(np.argmin (self._seed_x))
            upper_x = np.flip (self._seed_x [0: iLe + 1])
            upper_y = np.flip (self._seed_y [0: iLe + 1])
            self._upper = Side_Airfoil_HicksHenne (upper_x, upper_y, [], linetype=Line.Type.UPPER)
        return self._upper 
            
    @property
    def lower(self) -> 'Side_Airfoil_HicksHenne': 
        """the lower surface as a Side_Airfoil_HicksHenne object - where x 0..1"""
        # overloaded
        if self._lower is None: 
            iLe = int(np.argmin (self._seed_x))
            lower_x = self._seed_x [iLe:]
            lower_y = self._seed_y [iLe:]
            self._lower = Side_Airfoil_HicksHenne (lower_x, lower_y, [], linetype=Line.Type.LOWER)
        return self._lower 
            
    @property
    def x (self):
        # overloaded  - take from hicks henne 
        return np.concatenate ((np.flip(self.upper.x), self.lower.x[1:]))

    @property
    def y (self):
        # overloaded  - take from hcks henne  
        return np.concatenate ((np.flip(self.upper.y), self.lower.y[1:]))
    
    @property
    def nPoints (self): 
        """ number of coordinate points"""
        return len (self.upper.x) + len (self.lower.x) - 1


# ------------ test functions - to activate  -----------------------------------


if __name__ == "__main__":

    # ---- Test -----

    pass