#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Geometry of a curve based airfoil using Bezier or B-Spline curves  

    Implements a kind of 'strategy pattern' for the different approaches how 
    the geometry of an airfoil is determined and modified:

"""

import numpy as np
from typing                 import override
from enum                   import StrEnum
from timeit                 import default_timer as timer

from ..base.math_util       import * 
from ..base.common_utils    import clip
from ..base.cst             import CST
from ..base.spline          import Bezier, BSpline

from .geometry      import (Geometry, Line, Paneling, Curvature_Abstract)

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


# enum for fitting leading edge curvature - free, fixed or c2 continuity

class LE_Mode(StrEnum):
    FREE = "free"
    C2 = "c2"
    FIXED = "fixed"

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

    isCurve         = True

    NCP_DEFAULT     = None          # to be defined in subclass 


    def __init__ (self, linetype : Line.Type|None = None, name : str|None = None):
        """
        1D line of an airfoil like upper, lower side based on a curve with x 0..1

        The actual shape is defined by the curve (control points, weights, ...) set up
        by the concrete subclass - no x,y coordinates are needed here.
        """
        super().__init__(None, None, linetype=linetype, name=name)


        self._curve = None                          # curve object of self (Bezier, B-Spline or CST)
        
        # Panel distribution state - owned by side
        self._nPanels = None                        # per-side number of panels
        self._le_bunch = Paneling.LE_BUNCH_DEFAULT
        self._te_bunch = Paneling.TE_BUNCH_DEFAULT
        self._u = None                              # cached panel distribution
        self._u_state_key = None                    # curve state key when u was calculated
        
        # for fitting - store current deviation to target
        self._target_deviation : Deviation_Line = None
        self._is_matched       = False              # true if side is finally matched to target

        # baseline control points during interactive moving updates
        self._moving_cPoints : list[tuple] | None = None


    def set_paneling(self, nPanels: int, le_bunch: float = None, te_bunch: float = None):
        """
        Set panel distribution parameters for this side.
        Called by geometry when repaneling, pushes new parameters from geometry to side.
        
        Args:
            nPanels: Number of panels for this side (per-side count, not total)
            le_bunch: Leading edge bunching factor (optional, keeps current if None)
            te_bunch: Trailing edge bunching factor (optional, keeps current if None)
        """
        self._nPanels = nPanels
        if le_bunch is not None:
            self._le_bunch = le_bunch
        if te_bunch is not None:
            self._te_bunch = te_bunch


    @property
    def u (self ) -> list [float]:
        """ 
        Panel distribution as curve parameter u values.
        Computed on demand with automatic invalidation on curve state or paneling parameter changes.
        """
        if self._nPanels is None:
            raise ValueError(f"{self}: nPanels not set - call set_paneling first")
        
        # Check if recalculation needed
        if self._u is None or self._u_state_key != self._curve_state_key():
            self._u = self._get_u(self._nPanels, self.curve, self._le_bunch, self._te_bunch)
            self._u_state_key = self._curve_state_key()
            
        return self._u


    def _curve_state_key(self) -> tuple:
        """
        Returns a hashable key representing the current curve shape and paneling parameters,
        used to invalidate the cached 'u' panel distribution.
        Must be implemented in subclass (e.g. control points for Bezier/BSpline, weights for CST).
        """
        raise NotImplementedError


    def _get_u (self, nPanels_per_side: int, curve, le_bunch: float, te_bunch: float) -> np.ndarray:
        """ 
        Returns numpy array of u having an adapted panel distribution for one curve based side.
            - running from 0..1
            - having nPanels+1 points
            - applies cosine distribution in arc-length space
        """
        nPoints = nPanels_per_side + 1

        # Get cosine distribution in arc-length space
        u_cos = Paneling._cosine_distribution(nPoints, le_bunch, te_bunch)

        # Map to curve parameter space via arc-length inversion
        return self._u_of_arc_fractions(curve, u_cos)


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
        x_d, y_d = curve.eval (u_dense,update_cache=False)  # get dense points on curve
        ds = np.sqrt(np.diff(x_d)**2 + np.diff(y_d)**2)
        s  = np.concatenate([[0.0], np.cumsum(ds)])
        s /= s[-1]                                      # normalize to 0..1
        u = np.interp(arc_fractions, s, u_dense)
        u[0]  = 0.0                                     # ensure exact endpoints
        u[-1] = 1.0
        return u    


    @property
    def curve(self) -> Bezier | BSpline | CST:
        """ returns the curve object of self (Bezier, B-Spline or CST)"""

        return self._curve 

    @property
    def ncp (self) -> int:
        """ returns the number of control points (or weights for CST) of the curve"""

        return self.curve.ncp


    @property
    def cPoints (self) -> list[tuple]: 
        """ curve control points as xy"""
        return self.curve.cpoints
    
    def set_cPoints(self, cpx_or_cp=None, cpy=None, moving=False):
        """ set the curve control points"""

        # Decision for move-baseline usage is owned here:
        # - while moving: capture once, then always restore baseline first
        # - final apply after moving: restore baseline once if it exists
        if moving or self._moving_cPoints is not None:
            if self._moving_cPoints is None:
                self._moving_cPoints = list(self.cPoints)
            else:
                self.curve.set_cpoints (self._moving_cPoints)

        if cpx_or_cp is not None:
            self.curve.set_cpoints (cpx_or_cp, cpy)

        if not moving:
            self._moving_cPoints = None

        self.reset_target_deviation ()


    @property
    def cPoints_as_jpoints (self) -> list[JPoint]: 
        """ control points as JPoints (which include bounds)"""

        raise NotImplementedError("cPoints_as_jpoints must be implemented in subclass")

    def set_cPoints_from_jpoints(self, jpoints: list[JPoint], moving=False):
        """ set the curve control points from JPoints"""

        cPoints = [(jp.x, jp.y) for jp in jpoints]

        self.set_cPoints(cPoints, moving=moving)


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

        if isinstance(target, Line):
            self._target_deviation = Deviation_Line (target, lambda: self.curve, u=self.u)
        else:
            if target is not None:
                logger.warning (f"{self} set_target_deviation_from: target is not a Line - ignoring")
            self._target_deviation = None


    def reset_target_deviation (self):
        """ reset the calculated deviation to target side - will be re-calculated on demand"""
        if self._target_deviation is not None:
            self._target_deviation.calc_deviation ()

    @property
    def is_matched (self) -> bool:
        """ true if side is finally matched to target"""
        return self._is_matched
    
    def set_matched (self, matched : bool):
        """ set matched to target - true if side is finally matched to target"""
        self._is_matched = matched


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
        if not isinstance (curve_fn(), (Bezier, BSpline, CST)) :
            raise ValueError ("curve_fn must return a Bezier, BSpline or CST object")

        self._curve_fn = curve_fn           
        self._fast = False 

        # increase u density for fast interpolation if eval_fn is given

        if u is not None:
            u_mid = (u[:-1] + u[1:]) / 2                        # midpoints between consecutive u values
            self._u_dense = np.empty(len(u) + len(u_mid))
            self._u_dense[0::2] = u
            self._u_dense[1::2] = u_mid        

            # 10 extra midpoints between the first 11 points of u_dense (near LE)
            # u_extra = (self._u_dense[:10] + self._u_dense[1:11]) / 2
            # self._u_dense = np.sort(np.concatenate([self._u_dense, u_extra]))


        # calc deviation to target line 

        self._dy   = np.zeros (len(self.x))

        self.calc_deviation (ensure_fast=True)                  # ensure fast for initial calculation 


    def set_fast (self, fast : bool):
        """ set fast mode for deviation calculation and re-calc"""

        if fast != self._fast:
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
    isBezier        = False
    isBSpline       = False
    isCurve         = True

    description     = "based on 2 Bezier or B-Spline curves"

    side_class      = Side_Airfoil_Curve
    line_class      = Line

    CURVE_NAME      = "Curve"                   # curve name - to override
    MOD_CURVE       = CURVE_NAME                # modification string overritten from Geometry

    LE_MODE_DEFAULT = LE_Mode.FIXED             # default leading-edge mode for fit: le_curvature constraint


    def __init__ (self, **kwargs):
        """new Geometry based on two Bezier or B-Spline curves for upper and lower side """
        super().__init__(None, None, **kwargs)        

        self._upper : Side_Airfoil_Curve     = None       # upper side as Side_Airfoil_Curve object
        self._lower : Side_Airfoil_Curve     = None       # lower side as Side_Airfoil_Curve object

    def _reset (self):
        """ reinit the dependand lines of self""" 

        # overloaded Bezier do not reset upper and lower as they define the geometry
        if self._upper is not None:
            self._upper._highpoint = None           # but highpoints must be reset
        if self._lower is not None:
            self._lower._highpoint = None 
        self._thickness  = None                     
        self._camber     = None                    
        self._curvature  = None                


    @property
    def description_long (self) -> str:
        """ description of geometry for info and tooltip"""
        return f"{self.__class__.description}  (#CP {self.upper.ncp}, {self.lower.ncp})"


    @override
    def _isNormalized (self):
        """ true if LE is at 0,0 and TE is symmetrical at x=1"""
        # Curve is always normalized
        if (self.upper.curve.cpoints_x[0] == 0.0 and
            self.upper.curve.cpoints_y[0] == 0.0 and
            self.lower.curve.cpoints_x[0] == 0.0 and
            self.lower.curve.cpoints_y[0] == 0.0 and
            self.upper.curve.cpoints_x[-1] == 1.0 and
            self.lower.curve.cpoints_x[-1] == 1.0 and
            self.upper.curve.cpoints_y[-1] == -self.lower.curve.cpoints_y[-1]):
            return True
        else:
            raise ValueError(f"{self} curves are not normalized This may not happen")

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
    def set_upper (self, side : Side_Airfoil_Curve):
        """ set new upper side to upper - update geometry"""
        self._upper = side
        self._reset()

        mod_info = "initial fit"
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
    def set_lower (self, side : Side_Airfoil_Curve):
        """ set new lower side to lower - update geometry"""
        self._lower = side
        self._reset()

        mod_info = "initial fit"
        mod = self.MOD_CURVE + " " + side.name 
        self.modification_dict[mod] = mod_info


    def set_newSide_for (self, line_type: Line.Type, cpx_or_cp,cpy=None): 
        """creates either a new upper or lower side in self """

        if cpx_or_cp is not None:
            if line_type == Line.Type.UPPER:
                self._upper = self.side_class (cpx_or_cp, cpy, linetype=line_type)
            elif line_type == Line.Type.LOWER:
                self._lower = self.side_class (cpx_or_cp, cpy, linetype=line_type)
            self._reset()


    def set_side (self, aSide : Side_Airfoil_Curve): 
        """ set new side to aSide - update geometry"""

        if aSide.isUpper: 
            self._upper = aSide
        elif aSide.isLower:
            self._lower = aSide

        self._reset()


    def set_cPoints_from_jpoints_for (self, line_type : Line.Type, jpoints: list[JPoint], moving=False):
        """ set new curve control points from JPoints for upper or lower side - update geometry"""

        if line_type == Line.Type.UPPER:
            side = self._upper
        elif line_type == Line.Type.LOWER:
            side = self._lower

        side.set_cPoints_from_jpoints (jpoints, moving=moving)

        self.finished_change_of (side, moving=moving)


    def finished_change_of (self, side : Side_Airfoil_Curve, matched = False, moving=False):
        """ confirm Bezier changes for aSide - update geometry"""

        if matched:
            side.set_matched (True)
            mod_info = "matched"
        else:
            side.set_matched (False)
            mod_info = "changed"

        self._reset()

        side.reset_target_deviation()

        # ensure TE is symmetrical when upper side TE point changed
        if side.isUpper:
            self.lower.set_te_gap (side.te_gap)

        mod = self.MOD_CURVE + " " + side.name
        self._changed (mod, mod_info, moving=moving)


    @override
    def set_curve_parms_and_fit (self, side : Side_Airfoil_Curve, ncp : int,
                        target_side : Line,
                        le_curvature : float,
                        le_mode : LE_Mode = LE_Mode.FIXED,
                        moving : bool = False):
        """ set new no curve control points (or weights)for side with fit to target_side - update geometry"""
        # must be implemented in Bezier, B-Spline or CST subclass
        raise NotImplementedError


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

    def set_maxThick (self, newY): 
        raise NotImplementedError

    def set_maxThickX (self,newX): 
        raise NotImplementedError

    def set_maxCamb (self, newY): 
        raise NotImplementedError

    def set_maxCambX (self,newX): 
        raise NotImplementedError

    @override
    def set_te_gap (self, new_gap : float, xBlend = None, moving=False):
        """ set te gap - must be / will be normalized .

        Args: 
            new_gap:   in y-coordinates - typically 0.01 or so 
            xBlend:   the blending range from trailing edge 0..1
        """

        xBlend_change = False
        if xBlend is not None:
            xBlend = clip (xBlend, 0.1, 1.0)
            xBlend_change =  self.te_gap_xBlend != xBlend
            self._te_gap_xBlend = xBlend


        new_gap = clip (new_gap, 0.0, 0.1)

        if self.te_gap == new_gap and not xBlend_change:
            return

        self.upper.set_te_gap (new_gap * 0.5, self.te_gap_xBlend, moving=moving)
        self.lower.set_te_gap (new_gap * 0.5, self.te_gap_xBlend, moving=moving)

        self._changed (Geometry.MOD_TE_GAP, round(self.te_gap * 100, 2), moving=moving)   # finalize (parent) airfoil 



    @override
    @property
    def curvature (self) -> Curvature_of_Curve: 
        " return the curvature object"
        if self._curvature is None: 
            self._curvature = Curvature_of_Curve (self.upper, self.lower)  
        return self._curvature 


    @override
    @property 
    def paneling (self) -> Paneling:
        """ returns the target panel distribution / helper """
        raise NotImplementedError    # has to be implemented in Bezier or B-Spline
    

    def repanel (self,  nPanels : int = None, moving = False):
        """
        Repanel self with a new cosinus distribution.

        If no new panel numbers are defined, the current numbers for upper and lower side remain. 
        """

        self._repanel (nPanels)

        if not moving: 
            # save the actual paneling options as class variables
            self.paneling.save() 

        self._changed (Geometry.MOD_REPANEL, moving=moving)



    def _repanel (self, nPanels : int = None, **kwargs):
        """ 
        Inner repanel without change handling
        """

        nPanels   = nPanels if nPanels is not None else self.paneling.nPanels
        logger.debug (f"{self} _repanel {nPanels}")

        # Calculate per-side panel counts
        nPanels_upper = Paneling.nPanels_for(Line.Type.UPPER, nPanels)
        nPanels_lower = Paneling.nPanels_for(Line.Type.LOWER, nPanels)
        
        # Update paneling parameters on both sides
        # Pass bunching parameters from geometry's paneling settings
        self.upper.set_paneling(nPanels_upper, self.paneling.le_bunch, self.paneling.te_bunch)
        self.lower.set_paneling(nPanels_lower, self.paneling.le_bunch, self.paneling.te_bunch)

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

