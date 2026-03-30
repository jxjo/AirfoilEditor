#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Geometry of a curve based airfoil using Bezier or B-Spline curves  

    Implements a kind of 'strategy pattern' for the different approaches how 
    the geometry of an airfoil is determined and modified:

"""

import numpy as np
from typing                 import override
from timeit                 import default_timer as timer

from ..base.math_util       import * 
from ..base.spline          import Bezier, BSpline

from .airfoil_geometry      import (Geometry, Line, Panelling_Abstract, Curvature_Abstract)

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# -----------------------------------------------------------------------------
#  Panel Distribution  
# -----------------------------------------------------------------------------

class Panelling_Curve (Panelling_Abstract):
    """
    Helper class which represents the target panel distribution of a curve based airfoil 

    Calculates new panel distribution u for an airfoil side (Bezier or B-Spline curve)  
    """ 

    @override
    def _get_u (self, nPanels_per_side, curve=None) -> np.ndarray:
        """ 
        returns numpy array of u having an adapted panel distribution for one curve based side  
            - running from 0..1
            - having nPanels+1 points
            - when 'curve' is provided, applies cosine distribution in arc-length space
              (decouples point spacing from curve curvature, same concept as cubic spline)
        """

        # must be implemented in the specific curve based panelling class (Bezier or B-Spline)
        raise NotImplementedError


    @staticmethod
    def _u_of_arc_fractions (curve, arc_fractions: np.ndarray) -> np.ndarray:
        """
        Maps target arc-length fractions [0,1] back to curve parameter u [0,1].

        Samples the curve densely with uniform u, computes cumulative arc length,
        then uses linear interpolation to invert the arc-length → u mapping.
        This allows any desired distribution in arc-length space to be expressed
        as the corresponding curve parameter values.
        """
        u_dense = np.linspace(0.0, 1.0, 1000)
        x_d, y_d = curve.eval(u_dense)
        ds = np.sqrt(np.diff(x_d)**2 + np.diff(y_d)**2)
        s  = np.concatenate([[0.0], np.cumsum(ds)])
        s /= s[-1]                                      # normalize to 0..1
        u = np.interp(arc_fractions, s, u_dense)
        u[0]  = 0.0                                     # ensure exact endpoints
        u[-1] = 1.0
        return u


# -----------------------------------------------------------------------------
#  Curvature  
# -----------------------------------------------------------------------------

class Curvature_of_Curve (Curvature_Abstract):
    """
    Curvature of curve based geometry - is build from curvature of upper and lower side 
    """

    def __init__ (self,  upper : 'Side_Airfoil_Curve' , lower : 'Side_Airfoil_Curve'):
        super().__init__()

        start = timer()

        self._upper_side = upper
        self._lower_side = lower

        upper_curv = upper.curvature ()
        lower_curv = lower.curvature ()

        self._values = np.concatenate ((-np.flip(upper_curv.y), lower_curv.y[1:]))  
        self._upper  = Line (upper.x, - upper_curv.y, linetype=Line.Type.UPPER)
        self._lower  = Line (lower.x,   lower_curv.y, linetype=Line.Type.LOWER)

        self._iLe    = len (upper.x) - 1

        # for curvature comb
        self._upper_dx, self._upper_dy = upper.curve.eval (upper.u, der=1)
        self._lower_dx, self._lower_dy = lower.curve.eval (lower.u, der=1)

        logger.debug (f"{self} curvature init {timer() - start:.4f}s")


    @override
    @property
    def at_le (self) -> float: 
        """ max value of curvature at LE"""

        curv = max (self.upper.y[0], self.lower.y[0])
        return float(curv)



# -----------------------------------------------------------------------------
#  Single Side of Airfoil Geometry - Curve based  
# -----------------------------------------------------------------------------

class Side_Airfoil_Curve (Line): 
    """ 
    1D line of an airfoil like upper, lower side based on a curve with x 0..1
    """

    isCurve        = True
    NCP_DEFAULT    = None                           # default number of control points for curve
    NCP_BOUNDS     = (None, None)                   # reasonable range for number of control points for fitting

    def __init__ (self, *args, **kwargs):
        """
        1D line of an airfoil like upper, lower side based on a curve with x 0..1

        Args:
            cpx_or_cp, cpy : array of control point coordinates 
            nPoints : number of points 
             
        """
        super().__init__(*args, **kwargs)


        self._curve = None                          # curve object of self (Bezier or B-Spline)
        self._u = None                              # panel distribution of self - equals curve parameter u of Bezier or B-Spline
        self._target_deviation = None               # deviation to target side for fitting - will be


    @classmethod
    def on_side (cls):
        """
        Alternate constructor for curve based on a target side 
        - used for fitting a curve to data points


        Args:
            target_side: Line object representing the target side to fit
            ncp: number of control points for the Bezier curve
        """
        # has to be implemented in the specific curve based side class (Bezier or B-Spline) 
        raise NotImplementedError


    @property
    def u (self ) -> list [float]:
        """ Bezier panel distribution equals curve parameter u of Bezier"""
        # has to be implemented in the specific curve based side class (Bezier or B-Spline)
        raise NotImplementedError    


    def set_panel_distribution  (self, u_new : int ):
        """ set new Bezier panel distribution"""
        self._u = u_new


    @property
    def curve(self) -> Bezier | BSpline:
        """ returns the bezier object of self"""

        return self._curve 


    @property
    def controlPoints (self) -> list[tuple]: 
        """ bezier control points as xy"""
        return self.curve.cpoints
    
    def set_controlPoints(self, cpx_or_cp, cpy=None):
        """ set the bezier control points"""
        self.curve.set_cpoints (cpx_or_cp, cpy)
        self.reset_target_deviation ()

    @property
    def controlPoints_as_jpoints (self) -> list[JPoint]: 
        """ bezier control points as JPoints"""
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


    @property
    def ncp (self): 
        """ number of bezier control points """
        return self.curve.ncp


    @property
    def x (self):
        # overloaded curve caches values
        return self.curve.eval(self.u)[0]
    
    @property
    def y (self): 
        # overloaded curve caches values
        return self.curve.eval(self.u)[1]

    def curvature (self) -> Line: 
        """returns a Line with curvature in y 
        !! as side is going from 0..1 the upper side has negative value 
        !! compared to curvature of airfoil which is 1..0..1
        """

        return Line (self.x, self.curve.curvature(self.u), name='curvature')
   

    def yFn (self,x):
        """ returns evaluated y values based on a x-value - in high precision
        """
        logger.debug (f"{self} eval y on x={x}")
        return self.curve.eval_y_on_x (x, fast=False)


    @property
    def target_deviation (self) -> 'Deviation_Line':
        """ returns the deviation to the target side for fitting """
        return self._target_deviation

    def set_target_deviation_from (self, target : Line):
        """ set a new target deviation of fitting """

        self._target_deviation = Deviation_Line (target, lambda: self.curve, u=self.u)


    def reset_target_deviation (self):
        """ reset the calculated deviation to target side - will be re-calculated on demand"""
        if self._target_deviation is not None:
            self._target_deviation.calc_deviation ()


    # ------------------


    def re_fit_curve (self, *args, **kwargs): 
        """ re-fit the Bezier curve to the target coordinates - used after control point changes to update curve"""

        # has to be implemented in the specific curve based side class (Bezier or B-Spline)
        raise NotImplementedError


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
        """ returns y value of the last bezier control point which is half the te gap"""
        return self.curve.cpoints_y[-1]
    
    def set_te_gap (self, y): 
        """ set te Bezier control point to y to change te gap """
        cpx = self.curve.cpoints_x
        self.curve.set_cpoint (-1, cpx[-1], y) 


# -----------------------------------------------------------------------------
#  Deviation Line of a Side_Curve to a target x,y line  
# -----------------------------------------------------------------------------


class Deviation_Line (Line):
    """ 
    Line representing the deviation of a geometry line to a target line 
    """

    def __init__ (self, target_line : Line, 
                  curve_fn : callable,
                  u : np.ndarray = None,
                  **kwargs):
        """

        Args:
            target_line:    target line which should be compared
            side_curve:     the curve based side which should be compared to target line
            u:              u values for eval_fn - if eval_fn is given, u is needed
        """

        super().__init__ (np.copy(target_line.x), np.copy(target_line.y), **kwargs)

        # sanity 
        if not isinstance (target_line, Line):
            raise ValueError ("target_line must be a Line object")
        if not callable (curve_fn) :
            raise ValueError ("curve_fn must be a callable function which returns the Bezier or B-Spline ")
        if not isinstance (curve_fn(), (Bezier, BSpline)) :
            raise ValueError ("curve_fn must return a Bezier or BSpline object")

        self._curve_fn = curve_fn           
        self._fast = False 

        # increase u density for fast interpolation if eval_fn is given

        if u is not None:
            u_mid = (u[:-1] + u[1:]) / 2                        # midpoints between consecutive u values
            self._u_dense = np.sort(np.concatenate([u, u_mid]))        

        # calc deviation to target line 

        self._dy   = np.zeros (len(self.x))

        self.calc_deviation (ensure_fast=True)                  # ensure fast for initial calculation 


    def set_fast (self, fast : bool):
        """ set fast mode for deviation calculation and re-calc"""

        if fast and fast != self._fast:
            self._fast = fast 
            self.calc_deviation ()


    def calc_deviation (self, ensure_fast=False):
        """ calculates the deviation to target line based on given eval function or eval_y_on_x_fn"""


        curve : Bezier | BSpline = self._curve_fn()

        if self._fast or ensure_fast:

            x_side,y_side = curve.eval (self._u_dense)
            y_cur = np.interp(self.x, x_side, y_side)         # fast numpy interpolation
            self._dy  = y_cur - self.y

        else:

            self._dy   = np.zeros (len(self.x))
            for i, xi in enumerate(self.x) :
                self._dy[i] = self.y[i] - curve.eval_y_on_x (xi, fast=False, epsilon=1e-7)


    @property
    def dy (self) -> np.ndarray:
        """ y deviation at x of target line"""
        return self._dy


    def norm2 (self) -> float:
        """returns norm2 of deviation to target line"""
        return np.linalg.norm (np.abs(self._dy)) 


    def rms (self) -> float:
        """returns root mean square of deviation to target line"""
        return np.sqrt (np.mean (self._dy ** 2)) 


    def max_dy (self) -> tuple[float, float]:
        """returns x and max of absolute deviation to target line"""
        i_max = np.argmax (np.abs(self._dy))
        return self.x[i_max], np.abs(self._dy[i_max])
    

    def mean_abs (self) -> float:
        """returns mean of absolute deviation to target line"""
        return np.mean (np.abs(self._dy))




# -----------------------------------------------------------------------------
#  Geometry  
# -----------------------------------------------------------------------------

class Geometry_Curve (Geometry): 
    """ 
    Superclass for geometry based on two Bezier or B-Spline curves for upper and lower side
    """
    
    isBasic         = False 
    isBezier        = True
    isBSpline       = False
    isCurve         = True
    description     = "based on 2 Bezier or B-Spline curves"

    side_class      = Side_Airfoil_Curve
    line_class      = Line

    CURVE_NAME      = "Curve"                    # curve name - to override
    MOD_CURVE       = CURVE_NAME                 # modification string overritten from Geometry


    def __init__ (self, **kwargs):
        """new Geometry based on two Bezier or B-Spline curves for upper and lower side """
        super().__init__(None, None, **kwargs)        

        self._upper : Side_Airfoil_Curve     = None       # upper side as Side_Airfoil_Curve object
        self._lower : Side_Airfoil_Curve     = None       # lower side as Side_Airfoil_Curve object


    def _reset_lines (self):
        """ reinit the dependand lines of self""" 

        # overloaded Bezier do not reset upper and lower as they define the geometry
        if self._upper is not None:
            self._upper._highpoint = None           # but highpoints must be reset
        if self._lower is not None:
            self._lower._highpoint = None 
        self._thickness  = None                     
        self._camber     = None                    
        self._curvature  = None                


    @override
    def _isNormalized (self):
        """ true if LE is at 0,0 and TE is symmetrical at x=1"""
        # Curve is always normalized
        return True

    @override
    @property
    def isSymmetrical (self) -> bool:
        """ true if lower = - upper"""
        # overlaoded - for Bezier check control points 
        if self.upper.curve.cpoints_x == self.lower.curve.cpoints_x: 
            if self.upper.curve.cpoints_y == [-y for y in self.lower.curve.cpoints_y]:
                return True 
        return False 
    
    @override
    @property
    def upper(self) -> Side_Airfoil_Curve: 
        """upper side as Side_Airfoil_Curve object"""
        if self._upper is None: 
            raise ValueError ("Upper side not defined - create new side with set_newSide_for or set_side")
        return self._upper 


    @override
    def set_upper (self, side : Side_Airfoil_Curve, mod_info : str = None):
        """ set new upper side to upper - update geometry"""
        self._upper = side
        self._reset_lines()

        if mod_info:
            mod = self.MOD_CURVE + " " + side.name
            self.modification_dict[mod] = mod_info


    @override
    @property
    def lower(self) -> Side_Airfoil_Curve : 
        """lower side as Side_Airfoil_Curve object"""

        if self._lower is None: 
            raise ValueError ("Lower side not defined - create new side with set_newSide_for or set_side")
        return self._lower 

    @override
    def set_lower (self, side : Side_Airfoil_Curve, mod_info : str = None):
        """ set new lower side to lower - update geometry"""
        self._lower = side
        self._reset_lines()

        if mod_info:
            mod = self.MOD_CURVE + " " + side.name 
            self.modification_dict[mod] = mod_info


    def set_newSide_for (self, line_type: Line.Type, cpx_or_cp,cpy=None): 
        """creates either a new upper or lower side in self """

        if cpx_or_cp is not None:
            if line_type == Line.Type.UPPER:
                self._upper = self.side_class (cpx_or_cp, cpy, linetype=line_type)
            elif line_type == Line.Type.LOWER:
                self._lower = self.side_class (cpx_or_cp, cpy, linetype=line_type)
            self._reset_lines()


    def set_side (self, aSide : Side_Airfoil_Curve): 
        """ set new side to aSide - update geometry"""

        if aSide.isUpper: 
            self._upper = aSide
        elif aSide.isLower:
            self._lower = aSide

        self._reset_lines()


    def finished_change_of (self, side : Side_Airfoil_Curve, mod_info : str = 'changed'):
        """ confirm Bezier changes for aSide - update geometry"""

        self._reset()

        side.reset_target_deviation()

        # ensure TE is symmetrical when upper side TE point changed
        if side.isUpper:
            self.lower.set_te_gap (- side.te_gap)

        mod = self.MOD_CURVE + " " + side.name
        self._changed (mod, mod_info)


    def set_ncp_of (self, side : Side_Airfoil_Curve, ncp : int):
        """ set new no bezier control points for side with fit to target_side - update geometry"""

        ncp = np.clip (ncp, side.NCP_BOUNDS[0], side.NCP_BOUNDS[1])  # limit number of control points to reasonable range

        if ncp != side.ncp:
            # re-fit curve to current target coordinates or to self if no target coordinates defined 
            target = side.target_deviation if side.target_deviation is not None else Line (side.x, side.y)
            side.re_fit_curve ( target_side=target, ncp=ncp)   

            self._reset()

            mod = self.MOD_CURVE + " " + side.name
            self._changed (mod, f"nCP={ncp}")


    @override
    @property
    def x (self):
        # take from the two sides
        return np.concatenate ((np.flip(self.upper.x), self.lower.x[1:]))

    @override
    @property
    def y (self):
        # take from the two sides
        return np.concatenate ((np.flip(self.upper.y), self.lower.y[1:]))
    
    @override
    @property
    def nPoints (self): 
        """ number of coordinate points"""
        return len (self.upper.x) + len (self.lower.x) - 1

    @override
    @property
    def le (self) -> tuple: 
        """ coordinates of le - Curve always 0,0 """
        return 0.0, 0.0     
    
    @override
    @property
    def le_real (self) -> tuple: 
        """ coordinates of le defined by a virtual curve- - Curve always 0,0 """
        return self.le


    @override    
    @property
    def te_gap (self) -> float: 
        """ trailing edge gap in y"""
        #overridden to get data from Bezier curves
        return  round (float (self.upper.te_gap - self.lower.te_gap),7)

    def set_maxThick (self, newY): 
        raise NotImplementedError

    def set_maxThickX (self,newX): 
        raise NotImplementedError

    def set_maxCamb (self, newY): 
        raise NotImplementedError

    def set_maxCambX (self,newX): 
        raise NotImplementedError

    @override
    def set_te_gap (self, newGap): 
        """ set trailing edge gap to new value which is in y"""
        #override to directly manipulate Bezier
        newGap = max(0.0, newGap)
        newGap = min(0.1, newGap)

        self.upper.set_te_gap (  newGap / 2)
        self.lower.set_te_gap (- newGap / 2)

        self._reset () 
        self._changed (Geometry.MOD_TE_GAP, round(self.te_gap * 100, 7))   # finalize (parent) airfoil 


    @override
    @property
    def curvature (self) -> Curvature_of_Curve: 
        " return the curvature object"
        if self._curvature is None: 
            self._curvature = Curvature_of_Curve (self.upper, self.lower)  
        return self._curvature 


    @override
    @property 
    def panelling (self) -> Panelling_Curve:
        """ returns the target panel distribution / helper """
        raise NotImplementedError    # has to be implemented in Bezier or B-Spline
    

    def repanel (self,  nPanels : int = None, just_finalize = False):
        """
        Repanel self with a new cosinus distribution.

        If no new panel numbers are defined, the current numbers for upper and lower side remain. 
        """

        if not just_finalize:
            self._repanel (nPanels)

        else: 
            # save the actual panelling options as class variables
            self._panelling.save() 

        # reset chached values
        self._reset_lines()
        self._changed (Geometry.MOD_REPANEL)



    def _repanel (self, nPanels : int = None, **kwargs):
        """ 
        Inner repanel without change handling
        """

        nPanels   = nPanels if nPanels is not None else self.panelling.nPanels
        nPan_upper = self.panelling.nPanels_upper (nPanels)
        nPan_lower = self.panelling.nPanels_lower (nPanels)

        logger.debug (f"{self.panelling} _repanel {nPan_upper} {nPan_lower}")

        self.upper.set_panel_distribution (self.panelling._get_u (nPan_upper, curve=self.upper.curve))
        self.lower.set_panel_distribution (self.panelling._get_u (nPan_lower, curve=self.lower.curve))

        return True



    # ------------------ private ---------------------------


    def upper_new_x (self, new_x) -> np.ndarray: 
        """
        returns y coordinates for new_x
        Using bezier interpolation  
        """
        # evaluate the corresponding y-values on upper side 
        upper_y = np.zeros (len(new_x))
 
        for i, x in enumerate (new_x):
            upper_y[i] = self.upper.curve.eval_y_on_x (x, fast=True)  

        upper_y = np.round(upper_y, 10)

        return upper_y
        

    def lower_new_x (self, new_x)  -> np.ndarray: 
        """
        returns y coordinates for new_x
        Using bezier interpolation  
        """
        # evaluate the corresponding y-values on lower side 
        lower_y = np.zeros (len(new_x))
 
        # !! bezier must be evaluated with u to have x,y !! 
        for i, x in enumerate (new_x):

            # first and last point from current lower to avoid numerical issues 
            if i == 0: 
                lower_y[i] = self.lower.y[0]
            elif i == (len(new_x) -1):
                lower_y[i] = self.lower.y[-1]
            else:
                lower_y[i] = self.lower.curve.eval_y_on_x (x, fast=True)  

        lower_y = np.round(lower_y, 10)

        return lower_y

