#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Geometry of a B-Spline based airfoil  

    Implements a kind of 'strategy pattern' for the different approaches how 
    the geometry of an airfoil is determined and modified:

"""

import numpy as np
from typing                 import override
from timeit import default_timer as timer

from ..base.common_utils    import toDict, fromDict

from ..base.math_util       import * 
from ..base.spline          import BSpline

from .airfoil_geometry      import Line
from .geometry_curve        import (Panelling_Curve, Geometry_Curve, Side_Airfoil_Curve,
                                    Deviation_Line)

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# -----------------------------------------------------------------------------
#  Panel Distribution  
# -----------------------------------------------------------------------------

class Panelling_BSpline (Panelling_Curve):
    """
    Helper class which represents the target panel distribution of a B-Spline based airfoil 

    Calculates new panel distribution u for an airfoil side (B-Spline curve)  
    """ 

    @classmethod    
    def to_dict (cls, d:dict) :
        """ save current values of panelling parameters to dict"""

        # save panelling values 
        if cls._nPanels != cls.N_PANELS_DEFAULT:
            d["bspline_nPanels"] = cls._nPanels
        else: 
            d.pop ("bspline_nPanels", None)

        if cls._le_bunch != cls.LE_BUNCH_DEFAULT:
            d["bspline_le_bunch"] = cls._le_bunch
        else:
            d.pop ("bspline_le_bunch", None) 

        if cls._te_bunch != cls.TE_BUNCH_DEFAULT:
            d["bspline_te_bunch"] = cls._te_bunch
        else:
            d.pop ("bspline_te_bunch", None)


    @classmethod
    def from_dict (cls, d:dict) :
        """ load panelling parameters from dict and set them as class variables"""

        # load panelling values 
        if "bspline_nPanels" in d:
            cls._nPanels = d["bspline_nPanels"]
        if "bspline_le_bunch" in d:
            cls._le_bunch = d["bspline_le_bunch"]
        if "bspline_te_bunch" in d:
            cls._te_bunch = d["bspline_te_bunch"]


    @override
    def _get_u (self, nPanels_per_side, curve=None) -> np.ndarray:
        """ 
        returns numpy array of u having arc-length based cosine distribution for one curve side  
            - running from 0..1
            - having nPanels+1 points
        """

        nPoints = nPanels_per_side + 1

        u_cos = self._cosine_distribution (nPoints, self.le_bunch, self.te_bunch)
        return self._u_of_arc_fractions(curve, u_cos)


# -----------------------------------------------------------------------------
#  Single Side of Airfoil Geometry - B-Spline based  
# -----------------------------------------------------------------------------

class Side_Airfoil_BSpline (Side_Airfoil_Curve): 
    """ 
    1D line of an airfoil like upper, lower side based on a B-Spline curve with x 0..1
    """

    isBSpline        = True

    _le_exponent         = 0.5          # fitting: exponent for leading edge clustering of control points 
    _te_exponent         = 1.0          # fitting: exponent for trailing edge clustering of control points

    NCP_DEFAULT    = 8                  # default number of control points for B-Spline curve
    NCP_BOUNDS     = (4,10)             # reasonable range for number of control points for fitting



    def __init__ (self, cpx_or_cp, cpy=None, knots=None, degree=4, **kwargs):
        """
        1D line of an airfoil like upper, lower side based on a B-Spline curve with x 0..1
        
        Args:
            cpx, cpy: Control point coordinates of the B-Spline
            knots: optional knot vector for the B-Spline curve
            degree: degree of the B-Spline curve (if None and knots provided, derived from knots)
        """
        super().__init__(None, None, **kwargs)

        if cpx_or_cp is None:
            raise ValueError ("B-Spline points missing")

        self._curve = BSpline(cpx_or_cp, cpy, degree=degree, knots=knots)  

        # panel distribution for this side will be based on nPanels default of airfoil 
        self._u         = None

        # for fitting - store target coordinates to fit to - used for curvature comb and error calculation
        self._target_side : Line = None
        self._target_deviation : Deviation_Line = None


    @classmethod
    def on_dict (cls, dataDict, linetype : Line.Type |None = None):
        """
        Alternate constructor for BSpline based side from a dataDict - used for loading from file

        Args:
            dataDict: dictionary with "px","py", "knots" keys
            linetype: Line.Type for the new side (UPPER or LOWER)
        """
        cpx     = fromDict(dataDict, "px", None)
        cpy     = fromDict(dataDict, "py", None)
        knots   = fromDict(dataDict, "knots", None)
        # degree will be derived from knots if present, otherwise use stored value or default
        degree  = fromDict(dataDict, "degree", None)

        return cls (cpx, cpy, knots=knots, degree=degree, linetype=linetype)


    @classmethod
    def on_side (cls, target_side : Line, degree=4, ncp=None,  **kwargs):
        """
        Alternate constructor for BSpline based side from a target side 
        - used for fitting a B-Spline to data points

        Parameters for fitting can be set via class variables 
            _le_exponent, _te_exponent and _le_tangent_vertical

        Args:
            target_side: Line object representing the target side to fit
            degree: degree of the B-Spline curve
            ncp: number of control points for the B-Spline curve
        """

        ncp = ncp if ncp is not None else cls.NCP_DEFAULT

        cp = BSpline.fit_curve(
                    target_side.x, target_side.y,
                    degree=degree,
                    ncp = ncp,
                    le_exponent=cls._le_exponent, te_exponent=cls._te_exponent )
        
        instance = cls(cp, knots=None, degree=degree, **kwargs)
        
        # deviation to target side 
        instance.set_target_deviation_from (target_side)
        
        return instance


    def _as_dict (self):
        """ returns a data dict with the parameters of self """

        d = {}
        toDict (d, "px",        list(self.bspline.cpoints_x))                  
        toDict (d, "py",        list(self.bspline.cpoints_y)) 
        toDict (d, "knots",     list(self.bspline.knots))
        toDict (d, "degree",    self.bspline.degree) 
        return d


    @override
    @property
    def curve(self) -> BSpline:
        return super().curve    

    @property
    def bspline(self) -> BSpline:
        """ returns the B-Spline object of self"""
        return self._curve 

    @override
    @property
    def u (self ) -> list [float]:
        """ B-Spline panel distribution equals curve parameter u of B-Spline"""
        if self._u is None:
            panelling = Panelling_BSpline()
            nPanels = panelling.nPanels_default_of (self.type)
            self._u = panelling._get_u (nPanels, curve=self.curve)
        return self._u


    @override
    def re_fit_curve (self, target_side : Line = None, ncp = None): 
        """ re-fit the B-Spline curve to the target coordinates - used after control point changes to update curve"""

        if ncp is None:
            ncp = self.ncp

        if target_side is None:
            if self._target_deviation is not None:
                target_side = self.target_deviation
            else:
                raise ValueError ("No target side provided for re-fitting the curve")

        # re-fit curve to target coordinates with current settings for fitting
        cp = BSpline.fit_curve(
                target_side.x, target_side.y,
                degree=self.bspline.degree,
                ncp = ncp,
                le_exponent=self._le_exponent, te_exponent=self._te_exponent)

        # update control points of self - this update B-Spline
        self.set_controlPoints(cp)



# -----------------------------------------------------------------------------
#  Geometry  
# -----------------------------------------------------------------------------

class Geometry_BSpline (Geometry_Curve): 
    """ 
    Geometry based on two B-Spline curves for upper and lower side
    """
    
    isBasic         = False 
    isBSpline       = True
    isCurve         = True
    description     = "based on 2 B-Spline curves"

    side_class = Side_Airfoil_BSpline

    CURVE_NAME      = "B-Spline"                  
    MOD_CURVE       = CURVE_NAME                 # modification string overritten from Geometry

    @override
    @property
    def upper(self) -> 'Side_Airfoil_BSpline' : 
        """upper side as Side_Airfoil_BSpline object"""
        if self._upper is None: 
            raise ValueError ("Upper side not set for Geometry_BSpline")
        return self._upper 


    @override
    @property
    def lower(self) -> 'Side_Airfoil_BSpline' : 
        """lower side as Side_Airfoil_BSpline object"""
        if self._lower is None: 
            raise ValueError ("Lower side not set for Geometry_BSpline")        
        return self._lower 


    @override
    @property 
    def panelling (self) -> Panelling_BSpline:
        """ returns the target panel distribution / helper """
        if self._panelling is None:
            self._panelling = Panelling_BSpline()  
        return self._panelling



