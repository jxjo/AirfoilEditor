#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Geometry of a Bezier based airfoil  

    Implements a kind of 'strategy pattern' for the different approaches how 
    the geometry of an airfoil is determined and modified:

"""

from typing                 import override
from copy                   import deepcopy

from ..base.math_util       import * 
from ..base.spline          import Bezier

from .airfoil_geometry      import Line
from .geometry_curve        import (Side_Airfoil_Curve, Geometry_Curve, Panelling_Curve,
                                    Deviation_Line)

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


# -----------------------------------------------------------------------------
#  Panel Distribution  
# -----------------------------------------------------------------------------

class Panelling_Bezier (Panelling_Curve):
    """
    Helper class which represents the target panel distribution of a Bezier based airfoil 

    Calculates new panel distribution u for an airfoil side (Bezier curve)  
    """ 


# -----------------------------------------------------------------------------
#  Curvature  
# -----------------------------------------------------------------------------



# -----------------------------------------------------------------------------
#  Single Side of Airfoil Geometry - Bezier based  
# -----------------------------------------------------------------------------

class Side_Airfoil_Bezier (Side_Airfoil_Curve): 
    """ 
    1D line of an airfoil like upper, lower side based on a Bezier curve with x 0..1
    """

    isBezier        = True

    _le_weight = 3.0                    # fitting: eight at LE for fitting, can be adjusted
    _le_weight_distance = 0.1           # fitting: x position where weight transitions to 1 for fitting, can be adjusted
    _le_tangent_vertical = True         # fitting: whether to enforce vertical tangent at leading edge

    NCP_DEFAULT     = 6                 # default number of control points for Bezier curve
    NCP_BOUNDS     = (3, 8)             # reasonable range for number of control points for fitting


    def __init__ (self, cpx_or_cp, cpy=None, **kwargs):
        """
        1D line of an airfoil like upper, lower side based on a Bezier curve with x 0..1

        Args:
            cpx_or_cp, cpy : array of control point coordinates 
            nPoints : number of points 
             
        """
        super().__init__(None, None, **kwargs)

        if cpx_or_cp is None:
            raise ValueError ("Bezier points missing")
        else:
            self._curve    = Bezier(cpx_or_cp, cpy)             # the bezier curve 

        # panel distribution for this side will be based on nPanels default of airfoil 
        self._u = None

        # lazy filling Bezier cached values for x,y
        if not self._curve.has_u:
            self._curve.eval(self.u)

        # for fitting - store current deviation to target
        self._target_deviation : Deviation_Line = None



    @classmethod
    def on_side (cls, target_side : Line, ncp=None, **kwargs):
        """
        Alternate constructor for Bezier based on a target side 
        - used for fitting a Bezier curve to data points

        Parameters for fitting can be set via class variables 
            _le_weight, _le_weight_distance and _le_tangent_vertical

        Args:
            target_side: Line object representing the target side to fit
            ncp: number of control points for the Bezier curve
        """

        ncp = ncp if ncp is not None else cls.NCP_DEFAULT

        cp = Bezier.fit_curve(
                    target_side.x, target_side.y,
                    ncp = ncp,
                    le_tangent_vertical=cls._le_tangent_vertical,
                    le_weight=cls._le_weight,
                    le_weight_distance=cls._le_weight_distance )
        
        instance = cls(cp, **kwargs)

        # deviation to target side 
        instance.set_target_deviation_from (target_side)

        return instance

    @override
    @property
    def curve(self) -> Bezier:
        """ returns the bezier curve object of self"""
        return self._curve

    @property
    def bezier(self) -> Bezier:
        """ returns the bezier object of self"""
        return self.curve

    # ------------------

    @override
    def re_fit_curve (self, target_side : Line = None, ncp = None): 
        """ re-fit the Bezier curve to the target coordinates - used after control point changes to update curve"""

        if ncp is None:
            ncp = self.ncp

        if target_side is None:
            if self._target_deviation is not None:
                target_side = self.target_deviation
            else:
                raise ValueError ("No target side provided for re-fitting the curve")

        # re-fit curve to target coordinates with current settings for fitting
        cp = Bezier.fit_curve(
                target_side.x, target_side.y,
                ncp = ncp,
                le_tangent_vertical=self._le_tangent_vertical,
                le_weight=self._le_weight,
                le_weight_distance=self._le_weight_distance )

        # update control points of self - this update B-Spline
        self.set_controlPoints(cp)


    def add_controlPoint (self, index, point : JPoint | tuple):
        """ add a new controlPOint at index """

        if isinstance (point, JPoint):
            new_xy = (point.x, point.y)
        else: 
            new_xy = point 

        if self.bezier.ncp < 10:
            cpoints = self.bezier.cpoints 
            cpoints.insert (index, new_xy)
            self.bezier.set_cpoints (cpoints) 



    def check_new_controlPoint_at (self, x, y) -> tuple [int, JPoint]: 
        """ 
        Checks a new Bezier control point at x,y - taking care of order of points. 
        Returns index, where it would be inserted or None if not successful
            and a JPoint with x,y coordinates after checks 
        """

        cpx = self.bezier.cpoints_x

        # never go beyond p0 and p-1
        if x <= cpx[0] or x >= cpx[-1]: return None, None

        # find index to insert - never before point 1
        for i_insert, pxi in enumerate (cpx):
            if i_insert > 1:                        # do not insert before p0 and p1 
                if pxi > x: 
                    break 

        cpoints = deepcopy(self.bezier.cpoints) 
        cpoints.insert (i_insert, (x, y)) 

        # check if distance to neighbour is ok 
        px_new, py_new = zip(*cpoints)
        dx_right = abs (x - px_new[i_insert+1])
        dx_left  = abs (x - px_new[i_insert-1])
        if (dx_right < 0.01) or (dx_left < 0.01): 
           return None, None

        return i_insert, JPoint (x,y) 
    

    def delete_controlPoint_at (self, index): 
        """ delete a  Bezier control point at index - point 0,1 and n-1 are not deleted 
        Returns index if successful - or None"""

        cpoints =  deepcopy(self.bezier.cpoints) 

        # never delete point 0, 1 and -1
        noDelete = [0,1, len(cpoints)-1]

        if not index in noDelete:
            del cpoints [index]
            # update Bezier now, so redraw wil use the new curve 
            self.bezier.set_cpoints (cpoints )
            return index
        else: 
            return None    

# -----------------------------------------------------------------------------
#  Geometry  
# -----------------------------------------------------------------------------

class Geometry_Bezier (Geometry_Curve): 
    """ 
    Geometry based on two Bezier curves for upper and lower side
    """
    
    isBezier        = True
    isCurve         = True
    description     = "based on 2 Bezier curves"

    side_class      = Side_Airfoil_Bezier

    CURVE_NAME      = "Bezier"                    
    MOD_CURVE       = CURVE_NAME                 # modification string overritten from Geometry


    @override
    @property
    def upper(self) -> 'Side_Airfoil_Bezier' : 
        """upper side as Side_Airfoil_Bezier object"""
        if self._upper is None: 
            # default side
            cpx = [   0,  0.0, 0.33,  1]
            cpy = [   0, 0.06, 0.12,  0]    
            self._upper = self.side_class (cpx, cpy, linetype=Line.Type.UPPER)
        return self._upper 


    @override
    @property
    def lower(self) -> 'Side_Airfoil_Bezier' : 
        """lower side as Side_Airfoil_Bezier object"""
        if self._lower is None: 
            # default side 
            cpx = [   0,   0.0,  0.25,   1]
            cpy = [   0, -0.04, -0.07,   0]  
            self._lower = self.side_class (cpx, cpy, linetype=Line.Type.LOWER)

        return self._lower 




