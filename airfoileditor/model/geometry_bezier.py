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

from .geometry      import Line
from .geometry_curve        import (Side_Airfoil_Curve, Geometry_Curve,
                                    Deviation_Line)
from .geometry      import Panelling

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


# -----------------------------------------------------------------------------
#  Panel Distribution  
# -----------------------------------------------------------------------------

class Panelling_Bezier (Panelling):
    """
    Helper class which represents the target panel distribution of a Bezier based airfoil.
    Stores parameters and handles serialization.
    """ 

    @classmethod    
    def to_dict (cls, d:dict) :
        """ save current values of panelling parameters to dict"""

        # save panelling values 
        if cls._nPanels != cls.N_PANELS_DEFAULT:
            d["bezier_nPanels"] = cls._nPanels
        else: 
            d.pop ("bezier_nPanels", None)

        if cls._le_bunch != cls.LE_BUNCH_DEFAULT:
            d["bezier_le_bunch"] = cls._le_bunch
        else:
            d.pop ("bezier_le_bunch", None) 

        if cls._te_bunch != cls.TE_BUNCH_DEFAULT:
            d["bezier_te_bunch"] = cls._te_bunch
        else:
            d.pop ("bezier_te_bunch", None)


    @classmethod
    def from_dict (cls, d:dict) :
        """ load panelling parameters from dict and set them as class variables"""

        # load panelling values 
        if "bezier_nPanels" in d:
            cls._nPanels = d["bezier_nPanels"]
        if "bezier_le_bunch" in d:
            cls._le_bunch = d["bezier_le_bunch"]
        if "bezier_te_bunch" in d:
            cls._te_bunch = d["bezier_te_bunch"]


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
    NCP_BOUNDS     = (4, 8)             # reasonable range for number of control points for fitting


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

        # Auto-detect side type from control points if not already set
        # and initialize _nPanels with default value
        if self.type is None:
            # Auto-detect: positive y → UPPER, negative y → LOWER
            cpy_vals = self._curve.cpoints_y
            self._linetype = Line.Type.UPPER if cpy_vals[1] > 0 else Line.Type.LOWER
        
        # Initialize nPanels to default per-side value based on type
        self._nPanels = Panelling.nPanels_for(self.type)

        # lazy filling Bezier cached values for x,y
        if not self._curve.has_u:
            self._curve.eval(self.u)

        # for fitting - store current deviation to target
        self._target_deviation : Deviation_Line = None



    @staticmethod
    def _get_initial_control_points(x_data, y_data, ncp, le_curvature=None):
        """
        Create initial Bezier control points from airfoil side coordinates.
        
        Creates control points by:
        - Distributing x positions uniformly
        - Taking y values from closest target points
        - Computing cp[1].y from LE curvature using analytical formula
        - Applying empirical y-scaling factors for better fit
        
        Based on the Fortran implementation from Xoptfoil2.

        Args:
            x_data: array of x coordinates from target side
            y_data: array of y coordinates from target side
            ncp: number of control points for the Bezier curve
            le_curvature: leading edge curvature (if None, estimated from data)

        Returns:
            list of (x, y) tuples representing control points
        """
        if ncp < 4:
            raise ValueError('Initial Bezier: ncp must be >= 4')
        
        # Get LE curvature if not provided
        if le_curvature is None:
            # Estimate from second point (crude approximation)
            le_curvature = 2.0 * abs(y_data[1]) / (x_data[1]**2) if x_data[1] > 0 else 100.0
        
        if abs(le_curvature) < 10:
            raise ValueError(f'Initial Bezier: le_curvature {le_curvature:.1f} is too small (< 10)')
        
        # Determine if bottom side
        is_bottom = y_data[1] < 0.0
        
        # Initialize control points
        px = np.zeros(ncp)
        py = np.zeros(ncp)
        
        # Fix LE and TE control points
        px[0] = 0.0         # LE x
        py[0] = 0.0         # LE y
        px[-1] = 1.0        # TE x
        py[-1] = y_data[-1] # TE y (gap)
        
        # Distribute intermediate x control points and get y from target
        np_between = ncp - 3
        
        if np_between == 1:
            dx = 0.35
        else:
            dx = 1.0 / (np_between + 1)
        
        xi = 0.0
        for ib in range(np_between):
            icp = 2 + ib  # Control point index (starting at 2, after LE tangent point)
            xi = xi + dx
            i = find_closest_index(x_data, xi)
            px[icp] = x_data[i]
            py[icp] = y_data[i]
        
        # Calculate py[1] (LE tangent point y) from LE curvature using analytical formula
        # |py[1]| = sqrt((ncp-2) * px[2] / ((ncp-1) * le_curv))
        py[1] = np.sqrt((ncp - 2) * px[2] / ((ncp - 1) * abs(le_curvature)))
        if is_bottom:
            py[1] = -py[1]
        py[1] = np.clip(py[1], -0.2, 0.2)
        
        # Apply empirical y-scaling factors for better fit
        # These factors help compensate for the global nature of Bezier curves
        for icp in range(2, ncp - 1):
            if ncp == 6:
                y_fac = 1.2
            elif ncp == 5:
                y_fac = 1.3
            elif ncp == 4:
                y_fac = 1.6
            else:
                y_fac = 1.15
            
            # Extra scaling for first interior point
            if icp == 2:
                y_fac = y_fac * 1.2
            
            py[icp] = py[icp] * y_fac
        
        return list(zip(px, py))


    @classmethod
    def on_side (cls, target_side : Line, le_curvature : float=200, ncp=None,  **kwargs):
        """
        Simple alternate constructor for Bezier based on direct control point placement.
        
        This is simpler than fit_curve() but provides a good starting point.
        Based on the Fortran implementation from Xoptfoil2.

        Args:
            target_side: Line object representing the target side
            le_curvature: leading edge curvature
            ncp: number of control points for the Bezier curve
        """

        ncp = ncp if ncp is not None else cls.NCP_DEFAULT
        
        # Get initial control points
        cp = cls._get_initial_control_points(
            target_side.x, target_side.y, ncp, le_curvature)
        
        # Create instance with control points
        instance = cls(cp, **kwargs)
        
        # Set target deviation
        instance.set_target_deviation_from(target_side)
        
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


    @override
    def _get_u (self, nPanels_per_side: int, curve: Bezier, le_bunch: float, te_bunch: float) -> np.ndarray:
        """ 
        Returns numpy array of u having arc-length based cosine distribution for Bezier curve.
            - running from 0..1
            - having nPanels+1 points
        """
        nPoints = nPanels_per_side + 1

        # Get cosine distribution in arc-length space
        u_cos = Panelling._cosine_distribution(nPoints, le_bunch, te_bunch)
        
        # Map to curve parameter space via arc-length inversion
        return self._u_of_arc_fractions(curve, u_cos)
    
    
    # ------------------

    @override
    def re_fit_curve (self, target_side : Line, le_curvature : float = None, ncp = None): 
        """ re-fit the Bezier curve to the target coordinates - used after control point changes to update curve"""

        if ncp is None:
            ncp = self.ncp
        
        # Get initial control points using simple direct placement
        cp = self._get_initial_control_points(
            target_side.x, target_side.y, ncp, le_curvature)

        # update control points of self
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


    @override
    @property 
    def panelling (self) -> Panelling_Bezier:
        """ returns the target panel distribution / helper """
        if self._panelling is None:
            self._panelling = Panelling_Bezier()  
        return self._panelling

