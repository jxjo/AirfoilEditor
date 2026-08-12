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

from .geometry      import Geometry, Line
from .geometry_curve        import Geometry_Curve, Side_Airfoil_Curve
from .geometry      import Panelling

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# -----------------------------------------------------------------------------
#  Panel Distribution  
# -----------------------------------------------------------------------------

class Panelling_BSpline (Panelling):
    """
    Helper class which represents the target panel distribution of a B-Spline based airfoil.
    Stores parameters and handles serialization.
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


# -----------------------------------------------------------------------------
#  Single Side of Airfoil Geometry - B-Spline based  
# -----------------------------------------------------------------------------

class Side_Airfoil_BSpline (Side_Airfoil_Curve): 
    """ 
    1D line of an airfoil like upper, lower side based on a B-Spline curve with x 0..1
    """

    isBSpline       = True

    _le_exponent    = 0.5               # fitting: exponent for leading edge clustering of control points 
    _te_exponent    = 1.0               # fitting: exponent for trailing edge clustering of control points

    NCP_DEFAULT     = 6                 # default number of control points for B-Spline curve
    NCP_BOUNDS      = (6,10)            # allowed range for number of control points for B-Spline curve 
    NCP_AUTO_RANGE  = (6,10)            # range for automatic ncp selection match result

    DEGREE          = 4                 # degree of B-Spline curve - currently fixed to 4 


    def __init__ (self, cpx_or_cp, cpy=None, knots=None, degree=None, **kwargs):
        """
        1D line of an airfoil like upper, lower side based on a B-Spline curve with x 0..1
        
        Args:
            cpx, cpy: Control point coordinates of the B-Spline
            knots: optional knot vector for the B-Spline curve
        """
        super().__init__(**kwargs)

        if cpx_or_cp is None:
            raise ValueError ("B-Spline points missing")
        
        if degree is None: 
            degree = Side_Airfoil_BSpline.DEGREE

        self._curve = BSpline(cpx_or_cp, cpy, degree=degree, knots=knots)  

        # Auto-detect side type from control points if not already set
        # and initialize _nPanels with default value
        if self.type is None:
            # Auto-detect: positive y → UPPER, negative y → LOWER
            cpy_vals = self._curve.cpoints_y
            self._linetype = Line.Type.UPPER if cpy_vals[1] > 0 else Line.Type.LOWER
        
        # Initialize nPanels to default per-side value based on type
        self._nPanels = Panelling.nPanels_for(self.type)

        # lazy filling B-Spline cached values for x,y
        if not self._curve.has_u:
            self._curve.eval(self.u)


    @classmethod
    def on_side (cls, target_side : Line, le_curvature : float=200, ncp=None,  **kwargs):
        """
        Alternate constructor for a B-Spline curve based on a target side 
        - used for fitting a curve to data points

        Args:
            target_side: Line object representing the target side to fit
            le_curvature: target leading edge curvature for initial control point placement
            ncp: number of control points for the B-Spline curve
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
        degree  = fromDict(dataDict, "degree", None)

        return cls (cpx, cpy, knots=knots, linetype=linetype, degree=degree)


    @staticmethod
    def _get_initial_control_points(x_data, y_data, ncp : int, le_curvature : float):
        """
        Create initial B-Spline control points from airfoil side coordinates.
        
        Creates control points by:
        - Distributing x positions uniformly
        - Taking y values from closest target points
        - Computing cp[1].y from LE curvature using analytical formula
        - Applying empirical y-scaling factors for better fit
        
        Based on the Fortran implementation from Xoptfoil2.

        Args:
            x_data: array of x coordinates from target side
            y_data: array of y coordinates from target side
            ncp: number of control points for the B-Spline curve
            le_curvature: leading edge curvature (if None, estimated from data)

        Returns:
            list of (x, y) tuples representing control points
        """
        if ncp < 5:
            raise ValueError('Initial B-Spline: ncp must be >= 5')
        
        # Get LE curvature if not provided
        if le_curvature is None:
            # Estimate from second point (crude approximation)
            le_curvature = 2.0 * abs(y_data[1]) / (x_data[1]**2) if x_data[1] > 0 else 100.0
        
        if abs(le_curvature) < 10:
            raise ValueError(f'Initial B-Spline: le_curvature {le_curvature:.1f} is too small (< 10)')

        # Use optimized least-squares fit for best RMS
        cp = BSpline.fit_curve(
                x_data, y_data,
                degree=Side_Airfoil_BSpline.DEGREE,
                ncp = ncp,
                le_exponent=Side_Airfoil_BSpline._le_exponent, 
                te_exponent=Side_Airfoil_BSpline._te_exponent)

        # do disturb cp2 to cp-2 a little to give nelder_mead a better starting point for the global fit 

        # for icp in range(2, ncp - 1):
        #     fac = 1.05
        #     cp [icp] = (cp[icp][0] * fac, cp[icp][1] * fac)

        # Fix cp[1].y analytically from LE curvature to ensure correct leading edge
        if le_curvature is not None:
            px, py = zip(*cp)
            px = list(px)
            py = list(py)
            
            # Determine if bottom side
            is_bottom = py[1] < 0.0
            
            # Calculate py[1] from LE curvature using analytical formula
            py[1] = BSpline.cp_y1_from_curvature(le_curvature, px[2], 
                                                  degree=Side_Airfoil_BSpline.DEGREE, ncp=ncp)
            if is_bottom:
                py[1] = -py[1]
            py[1] = np.clip(py[1], -0.2, 0.2)
            
            cp = list(zip(px, py))

        # # Determine if bottom side
        # is_bottom = y_data[1] < 0.0
        
        # # Initialize control points
        # px = np.zeros(ncp)
        # py = np.zeros(ncp)
        
        # # Fix LE and TE control points
        # px[0] = 0.0         # LE x
        # py[0] = 0.0         # LE y
        # px[-1] = 1.0        # TE x
        # py[-1] = y_data[-1] # TE y (gap)
        
        # # Distribute intermediate x control points and get y from target
        # np_between = ncp - 3
        
        # if np_between == 1:
        #     dx = 0.35
        # else:
        #     dx = 1.0 / (np_between + 1)
        
        # xi = 0.0
        # for ib in range(np_between):
        #     icp = 2 + ib  # Control point index (starting at 2, after LE tangent point)
        #     xi = xi + dx
        #     i = find_closest_index(x_data, xi)
        #     px[icp] = x_data[i]
        #     py[icp] = y_data[i]

        # # Move px[2] forward for better initial fit towards LE
        # if ncp >= 5:
        #     px[2] = px[2] * 0.5

        # # Calculate py[1] (LE tangent point y) from LE curvature using analytical formula
        # py[1] = BSpline.cp_y1_from_curvature(le_curvature, px[2], degree=degree, ncp=ncp)    # negative for lower side
        # if is_bottom:
        #     py[1] = -py[1]
        # py[1] = np.clip(py[1], -0.2, 0.2)
        
        # # Apply empirical y-scaling factors for better fit
        # # These factors help compensate for the global nature of B-Spline curves
        # for icp in range(2, ncp - 1):
        #     if ncp == 6:
        #         y_fac = 1.2
        #     elif ncp == 5:
        #         y_fac = 1.5
        #     elif ncp <= 8:
        #         y_fac = 1.15  # Moderate scaling for 7-8 control points
        #     else:
        #         y_fac = 1.25  # Higher scaling for 9-10 control points - more global influence
            
        #     # Extra scaling for first interior point
        #     if icp == 2:
        #         y_fac = y_fac * 1.1
            
        #     py[icp] = py[icp] * y_fac

        # cp = list(zip(px, py))

        return cp


    def _as_dict (self):
        """ returns a data dict with the parameters of self """

        d = {}
        toDict (d, "px",        list(self.bspline.cpoints_x))                  
        toDict (d, "py",        list(self.bspline.cpoints_y)) 
        toDict (d, "knots",     list(self.bspline.knots()))
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
    def _get_u (self, nPanels_per_side: int, curve: BSpline, le_bunch: float, te_bunch: float) -> np.ndarray:
        """ 
        Returns numpy array of u having arc-length based cosine distribution for B-Spline curve.
            - running from 0..1
            - having nPanels+1 points
        """
        nPoints = nPanels_per_side + 1

        # Get cosine distribution in arc-length space
        u_cos = Panelling._cosine_distribution(nPoints, le_bunch, te_bunch)
        
        # Map to curve parameter space via arc-length inversion
        return self._u_of_arc_fractions(curve, u_cos)


    def _curve_state_key (self) -> tuple:
        """ hashable key of current control points + panelling params, for u cache invalidation"""
        return hash((
            tuple(float(v) for cp in self.curve.cpoints for v in cp),
            self._nPanels,
            self._le_bunch,
            self._te_bunch
        ))



    @property
    def controlPoints_as_jpoints (self) -> list[JPoint]: 
        """ B-Spline control points as JPoints"""
        jpoints = []
        nPoints = self.ncp

        for i in range(nPoints):

            jpoint = JPoint (self.controlPoints[i])              # xy tuple 

            if self.isUpper:
                y_lim = (0,1)
            else:
                y_lim = (-1,0) 

            if i == 0 :                                         # first fixed 
                jpoint.set_fixed (True)
            elif i == (nPoints-1):                              # te vertical move
                if self.isUpper: 
                    jpoint.set_x_limits ((1,1))
                    jpoint.set_y_limits (y_lim)
                else: 
                    jpoint.set_fixed (True)
            elif i == 1 :                                       # le tangent vertical move
                jpoint.set_x_limits ((0,0))
                jpoint.set_y_limits (y_lim)
            else:       
                jpoint.set_x_limits ((0,1))

            jpoints.append(jpoint)

        return jpoints 


    def re_fit_curve (self, target_side : Line, le_curvature : float = None, ncp = None): 
        """ re-fit the B-Spline curve to the target coordinates - used after control point changes to update curve"""

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

        if self.curve.ncp < 10:
            cpoints = self.curve.cpoints 
            cpoints.insert (index, new_xy)
            self.curve.set_cpoints (cpoints) 


    def move_controlPoint_to (self, index, x, y): 
        """ move curve control point to x,y - taking care of order of points. 
        If x OR y is None, the coordinate is not changed

        Returns x, y of new (corrected) position """

        cpx = self.curve.cpoints_x
        cpy = self.curve.cpoints_y

        if x is None: x = cpx[index]
        if y is None: y = cpy[index]
        if index == 0:                          # fixed
            x, y = 0.0, 0.0 
        elif index == 1:                        # only vertical move
            x = 0.0 
            if cpy[index] > 0: 
                y = max (y,  0.006)             # LE not too sharp
            else: 
                y = min (y, -0.006)
        elif index == len(cpx) - 1:              # do not move TE gap   
            x = 1.0 
            y = cpy[index]                       
        else:                      
            x = max (x, 0.01)       
            x = min (x, 0.99)

        self.curve.set_cpoint (index, x,y)

        return x, y 


    @property
    def te_gap (self):
        """ returns signed y value of the last B-Spline control point which is half the te gap"""
        return self.curve.cpoints_y[-1]

    def set_te_gap(self, te_gap: float, xBlend: float = None):
        """
        Apply a trailing-edge gap to this side. Sign of the gap is applied based on the side type (upper/lower). 
        The gap is blended over a specified range from the trailing edge.

        Args:
            te_gap: ! half of the airfoil trailing-edge gap !
            xBlend: blending range from trailing edge, 0.0..1.0
        """

        # sign sanity
        if self.type == Line.Type.UPPER:
            dgap = -(abs(self.te_gap) - abs(te_gap))
        elif self.type == Line.Type.LOWER:
            dgap = abs(self.te_gap) - abs(te_gap)

        if dgap == 0.0:
            return  # No change needed

        if xBlend is None:
            xBlend = Geometry.TE_GAP_XBLEND

        control_points = self.controlPoints
        ncp = len(control_points)

        x = np.array([p[0] for p in control_points])
        y = np.array([p[1] for p in control_points], copy=True)

        if xBlend == 0.0:
            y[-1] = y[-1] + dgap
            self.controlPoints = list(zip(x, y))
            return

        # Convert trailing-edge blend length in x-space to a curve parameter start.
        x_start = 1.0 - xBlend
        u_start = self.curve.eval_u_on_x(x_start, fast=False)

        for i in range(ncp):
            # Approximate each control point position with a normalized index parameter.
            u = i / (ncp - 1)

            if u <= u_start:
                tfac = 0.0
            else:
                ub = (u - u_start) / (1.0 - u_start)
                # Smoothstep-5 ramp for C2-continuous TE blending.
                tfac = ub**3 * (ub * (ub * 6.0 - 15.0) + 10.0)

            y[i] += dgap * tfac

        self.set_controlPoints(list(zip(x, y)))    



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


    @override
    def set_curve_parms_and_fit (self, side : Side_Airfoil_BSpline, ncp : int,
                        target_side : Line,
                        le_curvature : float,
                        moving : bool = False):
        """ set new no B-Spline control points for side with fit to target_side - update geometry"""

        ncp = np.clip (ncp, side.NCP_BOUNDS[0], side.NCP_BOUNDS[1])  # limit number of control points to reasonable range

        if ncp != side.ncp:
            
            # re-fit curve to current target coordinates or to self if no target coordinates defined 
            side.re_fit_curve ( target_side=target_side, ncp=ncp, le_curvature=le_curvature)   

            self._reset()

            if not moving:
                mod = self.MOD_CURVE + " " + side.name
                self._changed (mod, f"#Ctrl Points={ncp}")

