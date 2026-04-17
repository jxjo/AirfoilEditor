#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Geometry of an Airfoil  

    Implements a kind of 'strategy pattern' for the different approaches how 
    the geometry of an airfoil is determined and modified:

    - Basic     linear interpolation of surface
    - Spline    cubic spline interpolation (in geometry_spline module)
    - Bezier    Bezier based representation of outline (in geometry_bezier module)
    - BSpline   B-Spline based representation (in geometry_bspline module)

    A single side of the airfoil or other lines like 'camber' or 'thickness' distribution 
    is represented in a similar way with subclasses

    - Basic     linear interpolation of line
    - Spline    splined representation (in geometry_spline module)
    - Bezier    Bezier based representation (in geometry_bezier module) 
    - BSpline   B-Spline based representation (in geometry_bspline module)

    The Curvature holds the curvature of the geometry spline 



    Class hierarchy overview  

        Geometry                                    - basic with linear interpolation 
            |-- Geometry_Splined                    - splined (in geometry_spline)
            |-- Geometry_Bezier                     - Bezier based (in geometry_bezier)
            |-- Geometry_BSpline                    - B-Spline based (in geometry_bspline)

        Curvature_Abstract    
            |-- Curvature_of_xy                     - based on x,y coordinates
            |-- Curvature_of_Spline                 - based on existing spline (in geometry_spline)
            |-- Curvature_of_Curve                  - based on Bezier/B-Spline geo upper and lower side 

        Side_Airfoil (Line)                         - basic with linear interpolation
            |-- Side_Airfoil_Splined                - splined (in geometry_spline)
            |-- Side_Airfoil_Curve                  - Base class for Bezier and B-Spline based side            
                |-- Side_Airfoil_Bezier             - Bezier based (in geometry_bezier)
                |-- Side_Airfoil_BSpline            - B-Spline based (in geometry_bspline)
                                
                                                    
    Object model - example                          

        airfoil                                     - an airfoils 
            |-- geo : Geometry                      - geometry strategy (basic) 
                    |-- upper  : Side_Airfoil       - upper surface
                    |-- camber : Side_Airfoil       - camber line       
                    |-- Curvature                   - curvature of the geometry spline
                        |-- upper : Side_Airfoil    - curvature of upper surface
                        |-- lower : Side_Airfoil    - curvature of lower surface
                    
                    """

import numpy as np
from timeit                 import default_timer as timer
from enum                   import Enum
from typing                 import override
from math                   import isclose

from ..base.common_utils    import clip, Parameters
from ..base.math_util       import * 
from ..base.spline          import Spline1D, Spline2D

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


class GeometryException(Exception):
    """ raised when geometry calculation failed """
    pass



# -----------------------------------------------------------------------------
#  Panel Distribution  
# -----------------------------------------------------------------------------


class Panelling:
    """
    Abstract helper class which represents the target panel distribution of an airfoil 

    The class variables are the default values used for repaneling 
    """ 

    LE_BUNCH_DEFAULT = 0.84
    TE_BUNCH_DEFAULT = 0.7
    N_PANELS_DEFAULT  = 160
    
    _le_bunch = LE_BUNCH_DEFAULT
    _te_bunch = TE_BUNCH_DEFAULT 
    _nPanels  = N_PANELS_DEFAULT

    def __init__ (self, nPanels : int|None = None,
                        le_bunch : float | None = None,
                        te_bunch : float | None = None):
        
        self._nPanels  = nPanels if nPanels else self._nPanels
        self._le_bunch = le_bunch if le_bunch is not None else self._le_bunch
        self._te_bunch = te_bunch if te_bunch is not None else self._te_bunch
 

    @override
    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        return f"<{type(self).__name__}>"
    

    @property 
    def nPanels (self) -> int: 
        """ number of panels of the airfoil"""
        return self._nPanels

    def set_nPanels (self, newVal): 
        """ set new target number of panels"""
        newVal = max (40,  newVal)
        newVal = min (500, newVal) 
        self._nPanels = int (newVal)


    def nPanels_default_of (self, linetype) -> int: 
        """ number of panels for UPPER/LOWER"""
        return Panelling.nPanels_for(linetype, self.nPanels)


    @staticmethod
    def nPanels_for(linetype, total_nPanels: int = None) -> int:
        """
        Returns per-side panel count for given linetype from total panel count.
        
        Args:
            linetype: Line.Type.UPPER or Line.Type.LOWER
            total_nPanels: Total number of panels (upper + lower), defaults to N_PANELS_DEFAULT
            
        Returns:
            Per-side panel count
        """
        if total_nPanels is None:
            total_nPanels = Panelling.N_PANELS_DEFAULT
        
        if total_nPanels % 2 == 0:
            return int(total_nPanels / 2)
        else:
            # Odd total: upper gets one more panel
            if linetype == Line.Type.UPPER:
                return int(total_nPanels / 2) + 1
            else:
                return int(total_nPanels / 2)


    @property 
    def le_bunch (self) -> float:
        return self._le_bunch 
    
    def set_le_bunch (self, newVal): 
        """ set target leading edge bunch of panels """
        self._le_bunch = newVal
 

    @property 
    def te_bunch (self) -> float:
        return self._te_bunch 

    def set_te_bunch (self, newVal): 
        """ set target trailing edge bunch of panels"""
        self._te_bunch = newVal
 

    def save (self):
        """ save current parms to class variables"""

        self.__class__._nPanels  = self.nPanels
        self.__class__._le_bunch = self.le_bunch
        self.__class__._te_bunch = self.te_bunch


    @staticmethod
    def _cosine_distribution (nPoints: int,
                               le_bunch: float,
                               te_bunch: float) -> np.ndarray:
        """
        Returns a cosine-based distribution array of length nPoints over [0, 1].

        Bunching near LE is controlled by le_bunch, bunching near TE by te_bunch.
        Used by Panelling_Spline directly as u, and by curve-based pannelling
        (Bezier, B-Spline) as arc-length fractions that are subsequently mapped
        to curve parameter u via arc-length inversion.
        """

        ufacStart = 0.1 - le_bunch * 0.1            # 0.1 (no bunch) ... 0.0 (max LE bunch)
        ufacStart = np.clip(ufacStart, 0.0, 0.5)
        ufacEnd   = 0.65

        beta = np.linspace(ufacStart, ufacEnd, nPoints) * np.pi
        u    = (1.0 - np.cos(beta)) * 0.5
        u    = u - u[0]                              # shift so first point is exactly 0
        u    = u / u[-1]                             # normalize to 0..1

        if te_bunch > 0:
            te_exponent = 1.0 + te_bunch * 0.15     # 1.0 (no bunch) ... ~1.15 (max)
            u = 1.0 - (1.0 - u) ** te_exponent

        u[0]  = 0.0
        u[-1] = 1.0
        return u


    def _get_u (self, nPanels_per_side) -> np.ndarray:
        """ 
        returns numpy array of u for one side 
            - running from 0..1
            - having nPanels+1 points 
        """

        # to be overridden 
        pass


# -----------------------------------------------------------------------------
#  Curvature  
# -----------------------------------------------------------------------------


class Curvature_Abstract:
    """
    Abstract Curvature of geometry having curvature of upper and lower side as Line 
    """

    def __init__ (self):

        self._spline : Spline2D = None                  # helper spline for curvature evaluation
        self._values        = None

        self._upper         = None                  # upper side curvature as Side_Airfoil
        self._lower         = None                  # lower side curvature as Side_Airfoil
        self._iLe           = None                  # index of le in curvature array
        self._flap_kink_xu_xl  = None               # x position of a curvature flap kink upper, lower

        # for curvature comb
        self._upper_side    = None
        self._lower_side    = None
        self._upper_dx      = None
        self._upper_dy      = None
        self._lower_dx      = None
        self._lower_dy      = None


    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        return f"<{type(self).__name__}>"


    @property
    def upper (self) -> 'Line': 
        " return Side_Airfoil with curvature on the upper side"
        return self._upper 

    @property
    def lower (self) -> 'Line': 
        " return Side_Airfoil with curvature on the lower side"
        return self._lower 
    

    def side(self, sidetype) -> 'Line': 
        """return Side_Airfoil with curvature for 'side_name' - where x 0..1"""
        if sidetype == Line.Type.UPPER: 
            return self.upper
        elif sidetype == Line.Type.LOWER:
            return self.lower
        else: 
            return None

    @property
    def values (self): 
        " return the curvature at knots 0..npoints"   

        if self._values is None: 
            raise GeometryException ("Curvature of xy not initialized")
        return self._values


    def as_curvature_comb (self):
        """Returns coordinates for curvature comb visualization.
        
        A curvature comb displays lines perpendicular to the airfoil surface 
        with lengths proportional to the local curvature value. 

        The comb is built from upper and lower side with double LE point
        to visualize C2 discontinuity at LE if present.
        
        Returns:
            - x (ndarray): Base coordinates on the airfoil surface (x-values).
            - y (ndarray): Base coordinates on the airfoil surface (y-values).
            - xe (ndarray): End coordinates of the perpendicular comb lines (x-values).
            - ye (ndarray): End coordinates of the perpendicular comb lines (y-values).
            - vals (ndarray): Curvature values at the base coordinates.
        """
        # build from upper and lower side with double LE point
        vals = np.concatenate ((np.flip(self.upper.y), self.lower.y))
        x    = np.concatenate ((np.flip(self._upper_side.x), self._lower_side.x))
        y    = np.concatenate ((np.flip(self._upper_side.y), self._lower_side.y))

        # Calculate normal vector perpendicular to surface tangent
        nx =  np.concatenate ((-np.flip(self._upper_dy), self._lower_dy))
        ny = -np.concatenate ((-np.flip(self._upper_dx), self._lower_dx))

        # Normalize to unit length
        nn = np.sqrt(nx**2 + ny**2)
        nx /= nn
        ny /= nn

        # Scale factor based on maximum curvature magnitude
        # curvature_vals = np.sqrt(np.abs(vals)) * np.sign(vals) * 0.01
        # curvature_vals = np.abs(vals) * 0.001

        # Scale factor based on maximum curvature magnitude
        # Linear scale with soft saturation via tanh:
        # - linear behavior for small curvature (tanh(x) ≈ x for small x)
        # - saturates for high curvature at LE without distorting the comb shape between knots
        scale = 0.25                                # max display length in chord units
        norm  = 500.0                               # curvature value that maps to ~76% of scale
        curvature_vals = np.tanh(vals / norm) * scale * np.sign(vals)

        # Calculate comb line endpoints along normal direction
        xe = x + nx * curvature_vals
        ye = y + ny * curvature_vals

        return x, y, xe, ye, vals


    @property
    def iLe (self) -> int: 
        """ index of le in curvature array """
        return self._iLe

    @property
    def max (self) -> float: 
        """ max value of curvature"""
        max = np.amax(np.abs(self.values))
        return float(max)


    @property
    def at_le (self) -> float: 
        """ max value of curvature at LE"""
        return float(self.values [self.iLe])

    @property
    def at_upper_te (self) -> float: 
        """ value of curvature at upper TE  """
        return float(self.upper.y[-1])

    @property
    def max_te (self) -> float:
        """ max value at upper or lower side """
        return max (abs(self.at_upper_te), abs(self.at_lower_te))

    @property
    def at_lower_te (self) -> float: 
        """ value of curvature at lower TE  """
        return float(self.lower.y[-1])

    @property
    def has_flap_kink (self) -> bool:
        """ True if curvature has (probably) flap kink (peek on upper and lower side)"""

        return self.flap_kink_at is not None

    @property
    def flap_kink_xu_xl (self) -> tuple[float, float] | None:
        """ x position of a flap kink on upper and lower side or None"""

        if self.has_flap_kink:
            return self._flap_kink_xu_xl
        else:
            return None


    @property
    def flap_kink_at (self) -> float:
        """ x position (mean value of upper and lower) of a flap kink or None"""

        if self._flap_kink_xu_xl is None: 
            xu_xl = self._find_flap_kink()
            self._flap_kink_xu_xl = xu_xl if xu_xl else 0       # mark as calculated

        if self._flap_kink_xu_xl:
            x = (self._flap_kink_xu_xl[0] + self._flap_kink_xu_xl[1]) / 2
        else:
            x = None

        return x  


    def _find_flap_kink (self) -> tuple[float, float] | None:
        """ 
        check for a flap kink which leads to a peak of curvature at upper
        and opposite lower side. 
        Returns x value of the kink on upper and on lower side if they are close enough,
             otherwise None
        """

        wx = 0.03                       # max width of a needle
        threshold = 1.0                 # min curvature of a needle - to be a flap kink - should be high to avoid false positives

        # get curvature needles on upper and lower side using high threshold  

        needles_upper = self.upper.needles (xStart=0.3, xEnd=0.9, threshold=threshold, wx=wx)

        if len(needles_upper) > 0:
            needles_lower = self.lower.needles (xStart=0.3, xEnd=0.9, threshold=-threshold, wx=wx)
            if len(needles_lower) == 0:
                return None
        else: 
            return None    

        # get largest needle

        upper_y_max = 0
        upper_x_max = None
        for needle in needles_upper: 
            y = abs (needle[1])
            if y > upper_y_max:
                upper_x_max = needle[0]
                upper_y_max = y

        # get largest needle
        
        lower_y_max = 0
        lower_x_max = None
        for needle in needles_lower: 
            y = abs (needle[1])
            if y > lower_y_max:
                lower_x_max = needle[0]
                lower_y_max = y

        if isclose (upper_x_max, lower_x_max, abs_tol=0.015):
            # print ("upper ", upper_x_max, upper_y_max)
            # print ("lower ", lower_x_max, lower_y_max)
            return upper_x_max, lower_x_max
        else:
            return None
        

    @property
    def isReflexed (self) -> bool:
        """ True if there is just one reversal on upper side"""

        nReverse_upper = self.upper.nreversals (x_start=0.5, x_end=0.95)
        nReverse_lower = self.lower.nreversals (x_start=0.5, x_end=0.95)

        return nReverse_upper == 1 and nReverse_lower == 0


    @property
    def isRearLoaded (self) -> bool:
        """ True if there is just one reversal on lower side"""

        nReverse_upper = self.upper.nreversals (x_start=0.5, x_end=0.95)
        nReverse_lower = self.lower.nreversals (x_start=0.5, x_end=0.95)

        return nReverse_upper == 0 and nReverse_lower == 1



class Curvature_of_xy (Curvature_Abstract):
    """
    Curvature of (x,y) - using a new cubic spline for evaluation
    """

    def __init__ (self,  x : np.ndarray, y: np.ndarray):
        super().__init__()

        spline = Spline2D (x, y)

        # high res repanelling for curvature evaluation

        iLe  = int(np.argmin (x))
        # uLe  = spline.u[iLe]
        # u = Panelling_Spline(nPanels=400, le_bunch=0.98).new_u (spline.u, 0, uLe_target=uLe)

        # iLe = int(np.argmin(np.abs(u - uLe)))
        u = spline.u
        self._iLe    = iLe
        self._values = spline.curvature (u) 

        # split curvature spline in upper and lower 
        x, y    = spline.eval (u)

        self._upper = Line (np.flip(x[: iLe+1]), np.flip(self._values [: iLe+1]), 
                            linetype=Line.Type.UPPER )
        self._lower = Line (x[iLe: ], self._values [iLe: ],                       
                            linetype=Line.Type.LOWER )

        # for curvature comb
        self._upper_side = Line (np.flip(x[: iLe+1]), np.flip(y [: iLe+1]), linetype=Line.Type.UPPER )
        self._lower_side = Line (x[iLe: ], y [iLe: ], linetype=Line.Type.LOWER )

        dx, dy  = spline.eval (u, der=1)
        self._upper_dx = -np.flip(dx[: iLe+1])
        self._upper_dy = -np.flip(dy[: iLe+1])
        self._lower_dx = dx[iLe: ]
        self._lower_dy = dy[iLe: ]



# -----------------------------------------------------------------------------
#  Side of an Airfoil or other lines like camber, thickness distribution etc...
# -----------------------------------------------------------------------------


class Line: 
    """ 
    2D line of an airfoil like upper, lower side, camber line, curvature etc...
    with x 0..1

    Implements basic linear interpolation. 
    For higher precision use Side_Airfoil_Spline

    """

    class Type (Enum):
        """ enums for the different type of Lines """

        UPPER       = ('Upper','up')
        LOWER       = ('Lower','low')
        THICKNESS   = ('Thickness','t')
        CAMBER      = ('Camber','c')


    isCurve         = False
    isBezier        = False
    isBSpline       = False
    isHicksHenne    = False

    # --------------- static methods also for external use 

    @staticmethod
    def _reduce_target_points (target_line: 'Line') -> 'Line':
        """ 
        Returns a new target Line with a reduced number of points 
        to increase speed of deviation evaluation

        The reduction tries to get best points which represent an airfoil side 
        """
        # based on delta x
        # we do not take every coordinate point - define different areas of point intensity 
        x1  = 0.02 # 0.03                               # a le le curvature is master 
        dx1 = 0.020 # 0.025                              # now lower density at nose area
        x2  = 0.25 
        dx2 = 0.04
        x3  = 0.8                                       # no higher density at te
        dx3 = 0.03 # 0.03                               # to handle reflexed or rear loading

        targ_x = []
        targ_y = []
        x = x1
        while x < 1.0: 
            i = find_closest_index (target_line.x, x)
            targ_x.append(float(target_line.x[i]))
            targ_y.append(float(target_line.y[i]))
            if x > x3:
                x += dx3
            elif x > x2:                             
                x += dx2
            else: 
                x += dx1

        return Line(targ_x, targ_y)


    # ----------------------------------------------

    def __init__ (self, x,y, 
                  linetype : Type |None = None, 
                  name : str|None = None):

        self._x         = np.array(x)
        self._y         = np.array(y)
        self._type      = linetype 
        self._name      = name 
        self._threshold = 0.1                   # threshold for reversal detection 
        self._highpoint = None                  # the high Point of the line  
        self._max_spline = None                 # little helper spline to get maximum 


    @override
    def __repr__(self) -> str:
        name = self.name if self.name else type(self).__name__
        return f"<{name}>"


    @property
    def x (self): return self._x
    
    @property
    def y (self): return self._y
    def set_y (self, anArr): 
        self._y = anArr
    
    @property
    def type (self) -> Type:
        """ the linetype of self"""
        return self._type

    @property
    def name (self):       
        if self._name is None:
            return self._type.value[0] if self._type is not None else ''
        else: 
            return self._name
        
    def set_name (self,aName): 
        self._name = aName
    

    @property
    def threshold (self):   return self._threshold 
    def set_threshold (self, aVal): 
        self._threshold =aVal 

    @property
    def isNormalized (self) -> bool:
        """ true if x[0] == y[0] ==0.0 and x[-1] = 1.0 """
        return self.x[0] == 0.0 and self.y[0] == 0.0 and self.x[-1] == 1.0
    
    @property 
    def isUpper (self) -> bool:
        """ upper side? """
        return self.type == Line.Type.UPPER 

    @property 
    def isLower (self) -> bool:
        """ upper side? """
        return self.type == Line.Type.LOWER 

    @property
    def highpoint (self) -> JPoint:
        """
        Point repesentating the maximum y point value of self

        ! The accuracy of linear interpolation is about 1% compared to a spline or bezier
          based interpolation         
        """

        if self._highpoint is None: 

            xy = self._get_maximum()
            self._highpoint = JPoint (xy)

        return self._highpoint

    @property
    def max_xy (self) -> tuple:
        """ x,y of y coordinate with abs max y-value"""
        i_max = np.argmax(np.abs(self.y))
        return self.x[i_max], self.y[i_max] 


    @property
    def te (self) -> tuple:
        """ x,y of the last coordinate"""
        return self.x[-1], self.y[-1] 



    def reversals (self, x_start= 0.1, x_end=1.0, smooth=True, tolerance=0.02) -> np.ndarray:
        """ 
        returns the x positions of reversals (change of y sign) on self. 
        Smoothing with a moving average can be applied to avoid false positives.
        Take only y values > tolerance into account to avoid noise driven sign changes.
        """

        mask  = (self.x >= x_start) & (self.x <= x_end)
        curv_body  = self.y [mask]
        x_body     = self.x [mask]
   
        if smooth:
            # moving average to suppress noise-driven false sign changes
            n = max (5, len(curv_body) // 30)               # window ~ 3% of body points
            # mode='same' keeps array length identical to input → x_body stays in sync
            curv_body = np.convolve (curv_body, np.ones(n)/n, mode='same')
            # trim boundary artifacts where kernel didn't fully overlap
            curv_body = curv_body [n//2 : -n//2]
            x_body    = x_body    [n//2 : -n//2]            

        if tolerance > 0.0:
            mask      = np.abs(curv_body) > tolerance
            x_body    = x_body    [mask]
            curv_body = curv_body [mask]

        sign_change_indices = np.where (curv_body[:-1] * curv_body[1:] < 0)[0]
        sign_change_x       = x_body [sign_change_indices]         # x positions of sign changes
    
        return sign_change_x


    def nreversals (self, x_start= 0.1, x_end=1.0, smooth=True, tolerance=0.02) -> int:
        """ 
        returns the number of reversals (change of y sign) on self. 
        Smoothing with a moving average can be applied to avoid false positives.
        Take only y values > tolerance into account to avoid noise driven sign changes.
        """

        return len (self.reversals (x_start, x_end, smooth, tolerance))

    

    def needles (self, xStart= 0.1, xEnd=1.0, threshold=1.0, wx=0.0) -> list [tuple]:
        """ 
        returns a list of needles which are peaks beyond threshold with maximum width wx
        A needle is a tuple (x,y). Detection is between xStart and xEnd.
        
        Args:
            xStart: start x position for detection
            xEnd: end x position for detection  
            threshold: threshold value for peak detection (positive: peaks above, negative: peaks below)
            wx: maximum width in x for a needle (0.0 = single-point peaks only)
        """

        needles = []
        x = self.x
        y = self.y

        iToDetect = np.where ((x >= xStart) & (x <= xEnd))[0]

        if len(iToDetect) < 3: return needles

        # Determine if looking for positive or negative peaks
        looking_for_positive = threshold >= 0
        abs_threshold = abs(threshold)

        i = 0
        while i < len(iToDetect):
            idx = iToDetect[i]
            
            # Check for peak beyond threshold
            if looking_for_positive:
                peak_condition = y[idx] >= abs_threshold
            else:
                peak_condition = y[idx] <= -abs_threshold
            
            if peak_condition:
                # Find end of peak region
                j = i
                if looking_for_positive:
                    while j < len(iToDetect) and y[iToDetect[j]] >= abs_threshold:
                        j += 1
                else:
                    while j < len(iToDetect) and y[iToDetect[j]] <= -abs_threshold:
                        j += 1
                
                # Calculate peak width
                i_start = iToDetect[i]
                i_end = iToDetect[j-1]
                peak_width = x[i_end] - x[i_start]
                
                # Check if peak width is within limit
                if peak_width <= wx:
                    # Find maximum (or minimum for negative) in this region
                    peak_indices = iToDetect[i:j]
                    if looking_for_positive:
                        i_extreme = peak_indices[np.argmax(y[peak_indices])]
                    else:
                        i_extreme = peak_indices[np.argmin(y[peak_indices])]
                    
                    # For wx=0 (single point), verify neighbors are on opposite side of threshold
                    if wx == 0.0:
                        if i_extreme > 0 and i_extreme < len(y) - 1:
                            if looking_for_positive:
                                if y[i_extreme-1] < abs_threshold and y[i_extreme+1] < abs_threshold:
                                    needles.append((x[i_extreme], y[i_extreme]))
                            else:
                                if y[i_extreme-1] > -abs_threshold and y[i_extreme+1] > -abs_threshold:
                                    needles.append((x[i_extreme], y[i_extreme]))
                    else:
                        needles.append((x[i_extreme], y[i_extreme]))
                
                i = j
            else:
                i += 1
        
        return needles 
    

    def set_highpoint (self, target : tuple|JPoint) -> tuple: 
        """ 
        set / move the highpoint of self - returns new xy
        """

        if isinstance (target, JPoint):
            x_new = target.x
            y_new = target.y
        else: 
            x_new = target[0]
            y_new = target[1]


        # if e.g. camber is already = 0.0, a new camber line cannot be build
        # if np.max(self.y) == 0.0: return

        # optimize - no move if coordinate didn't change 

        x_isNew, y_isNew = self.highpoint.isNew (x_new, y_new)         

        if y_isNew:
            y_cur = self.highpoint.y
            y_new = self._move_max_y (y_cur, y_new)
            self.highpoint.set_y (y_new)

        if x_isNew:
            x_cur = self.highpoint.x
            x_new = self._move_max_x (x_cur, x_new)             # a little bit more complicated ...
            self.highpoint.set_x (x_new)

        # logger.debug (f"{self} - new highpoint xy: {self.highpoint.xy}")
        return (x_new, y_new)                           # final pos   



    def yFn (self,x):
        """ returns interpolated y values based on a x-value  """

        # find the index in self.x which is right before x
        jl = bisection (self.x, x)
        
        # now interpolate the y-value on lower side 
        if jl < (len(self.x) - 1):
            x1 = self.x[jl]
            x2 = self.x[jl+1]
            y1 = self.y[jl]
            y2 = self.y[jl+1]
            y = interpolate (x1, x2, y1, y2, x)
        else: 
            y = self.y[-1]
        return y


    def angle_in_range (self, x_min=0.95, x_max=1.0) -> float:
        """
        Computes the tangent angle (in degrees) of surface
        by fitting a straight line to the points in the x-range [x_min, x_max].
        """
        # Select points within the chosen x-range
        mask = (self.x >= x_min) & (self.x <= x_max)
        x_sel = self.x[mask]
        y_sel = self.y[mask]

        if len(x_sel) < 2:
            raise ValueError(f"{self} - Not enough points in the selected x-range.")

        # Linear regression: y = a*x + b
        a, b = np.polyfit(x_sel, y_sel, 1)

        # Tangent angle in degrees
        angle_rad = np.arctan(a)
        angle_deg = np.degrees(angle_rad)

        return angle_deg

    # ------------------ private ---------------------------


    def _get_maximum (self) -> tuple[float, float]: 
        """ 
        calculates and returns the x,y position of the maximum y value of self
            If self is symmetrical return (0.5,0)  
        """
        max_y = abs(np.max(self.y))
        min_y = abs(np.min(self.y))
        
        if max_y == 0.0 and min_y == 0.0:              # optimize symmetrical
            xmax = 0.5 
            ymax = 0.0 
        else: 
            if max_y > min_y:                          # upper side 
                imax = np.argmax(self.y)
            else:                                      # lower side
                imax = np.argmin(self.y)

            # build a little helper spline to find exact maximum
            if imax > 3 and imax < (len(self.x) -3 ): 

                istart = imax - 3
                iend   = imax + 3
                try: 
                    self._max_spline = Spline1D (self.x[istart:iend+1], self.y[istart:iend+1])
                except: 
                    pass

                # nelder mead search
                xstart = self.x[istart]
                xend   = self.x[iend]
                if max_y > min_y:                   # upper side 
                    xmax = findMax (self._yFn_max, self.x[imax], bounds=(xstart, xend))
                else:                               # lower side
                    xmax = findMin (self._yFn_max, self.x[imax], bounds=(xstart, xend))
                ymax = self._yFn_max (xmax)

                # print (f"delta x  {xmax - self.x[imax]:.5f}" )
                # print (f"delta y  {ymax - max_y:.5f}" )
            else:
                xmax = self.x[imax]
                ymax = self.y[imax]

            # limit decimals to a reasonable value
            xmax = round(xmax, 7)
            ymax = round(ymax, 7)
        return xmax, ymax


    def _yFn_max (self,x):
        """ spline interpolated y values based on a x-value based on little maximum helper spline
        """

        if self._max_spline is None: 
            raise ValueError ("Helper spline for maximum evaluation missing")
        return self._max_spline.eval (x)



    def _move_max_x (self, x_cur : float, x_new : float):
        """ 
        Moves the point of maximum to x_new.
        Returns new (limited) x_new  
        """

        # sanity check - only a certain range of move is possible 
        x_new = max (0.1, x_new)
        x_new = min (0.9, x_new)

        # from xfoil: 
        #    the assumption is that a smooth function (cubic, given by the old and 
        #    new highpoint locations) maps the range 0-1 for x/c
        #    into the range 0-1 for altered x/c distribution for the same y/c
        #    thickness or camber (ie. slide the points smoothly along the x axis)
         
        x = [self.x[0], x_cur, self.x[-1]]    
        y = [self.x[0], x_new, self.x[-1]]    
        mapSpl = Spline2D (x,y, boundary='natural')

        unew = np.linspace (0.0, 1.0, 50)
        xmap, ymap = mapSpl.eval(unew)

        mapSpl = Spline1D (xmap,ymap, boundary='natural')

        # finally re-map x-values to move high point 

        newX = np.zeros(len(self.x))
        for i, xi in enumerate (self.x):
            newX[i] = mapSpl.eval(xi)    
            # print (i, "%.8f" %(self.x[i] - newX[i]), newX[i])
        newX[0]  = self.x[0]                # ensure LE and TE not to change due to numeric issues
        newX[-1] = self.x[-1]

        # build a temp spline with the new x and the current y values 
        # 1D spline with arccos is needed to avoid oscillations at LE for thickness distribution with high curvature

        tmpSpl = Spline1D (newX, self._y, arccos=True) 
        newY = tmpSpl.eval(self._x)

        # ensure start and end is really, really the same (numerical issues) 
        newY[0] = self._y[0]
        newY[-1] = self._y[-1]
        self._y = newY 
        return x_new        


    def _move_max_y (self, y_cur : float, y_new : float):
        """ 
        Moves the point of maximum to y_new.
        Returns new (limited) y_new  
        """

        # sanity check - only a certain range of move is possible

        if y_cur == 0.0:
            y_new = 0.0      
        elif self.type == Line.Type.LOWER:             # range is negative
            y_new = max (-0.5, y_new)
            y_new = min (-0.005, y_new)
        else: 
            y_new = max (0.005, y_new)
            y_new = min (0.5, y_new)

        # the approach is quite simple: scale all y values by factor new/old

        self._y = self._y * (y_new / self.highpoint.y)

        return y_new 
           

    def _reset (self):
        """ reinit self if x,y has changed""" 
        self._maximum  = None                 # thickness distribution


# -----------------------------------------------------------------------------
#  Geometry Classes 
# -----------------------------------------------------------------------------


class Geometry (): 
    """ 
    Basic geometry strategy class - uses linear interpolation of points 

    no repanel 
    no curvature
    no move of high points of thickness and camber 

    """

    # possible modifications of airfoil geometry 

    MOD_NORMALIZE       = "normalized"
    MOD_REPANEL         = "repan"
    MOD_MAX_THICK       = "thickness"
    MOD_MAX_CAMB        = "camber"
    MOD_MAX_UPPER       = "upper"
    MOD_MAX_LOWER       = "lower"
    MOD_CURVE           = "Curve"                   # will be overritten by curve based geometry classes
    MOD_TE_GAP          = "te_gap"
    MOD_LE_RADIUS       = "le_radius"
    MOD_BLEND           = "blend"
    MOD_FLAP            = "flap"

    # default values of modifications

    TE_GAP_XBLEND       = 0.8                       # default x position from TE where te gap blending starts
    LE_RADIUS_XBLEND    = 0.1                       # default x position from LE where le radius blending ends

    EPSILON_LE_CLOSE    = 1e-6                      # max norm2 distance of le_real 

    # bad, good values for geometry quality

    LE_PANEL_ANGLE_TOO_BLUNT   = 175.0              # angle between first two panels at LE above too blunt
    PANEL_ANGLE_TOO_SHARP      = 150.0              # angle between two panels below too sharp

    isBasic         = True
    isSplined       = False 
    isBezier        = False
    isBSpline       = False
    isCurve         = False                         # either Bezier or B-Spline
    isHicksHenne    = False
    description     = "based on linear interpolation"

    side_class      = Line                          # class for upper and lower side - can be Line, Side_Airfoil_Splined, Bezier
    line_class      = Line                          # class for camber, thickness lines - can be Line or Side_Airfoil_Splined

    CURVE_NAME      = ""                            # curve name - to override

    def __init__ (self, 
                  x : np.ndarray, y: np.ndarray,
                  onChange = None):

        self._x_org = x                         # copy as numpy is used in geometry 
        self._y_org = y

        self._x = None   
        self._y = None

        self._callback_changed = onChange       # callback when self was changed (by user) 

        self._thickness : Line = None           # thickness distribution
        self._camber    : Line = None           # camber line
        self._upper     : Line = None           # upper side
        self._lower     : Line = None           # lower side

        self._curvature : Curvature_Abstract = None  # curvature object

        self._panelling = None                  # "paneller"  for spline or Bezier 

        self._modification_dict = {}            # dict of modifications made to self 


    @override
    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        return f"<{type(self).__name__}>"


    def _changed (self, aMod : str, 
                  val : float|str|None = None,
                  remove_empty = False):
        """ handle geometry changed 
            - save the modification made aMod with optional val
            - handle callbacks"""

        # store modification made - can be list or single mod 

        if remove_empty and (val is None or not (str(val))):
            self._modification_dict.pop (aMod, None)            # remove empty item
        else:                     
            self._modification_dict[aMod] = val

        # info Airfoil via callback  

        if callable(self._callback_changed):
            self._callback_changed ()
        else:
            logger.debug (f"{self} no change callback to airfoil defined")

    @property
    def modification_dict (self) -> list [tuple]:
        """returns a list of modifications as a dict of modifications"""
        return self._modification_dict

    @property
    def modifications_as_list (self) -> list [tuple]:
        """returns a list of modifications as string like 'repaneled 190'"""
        mods = []
        for aMod, val in self._modification_dict.items():
                val_str = f"{str(val)}" if val is not None else ''
                mods.append (f"{aMod} {val_str}" )
        return mods

    @property
    def modifications_as_label (self) -> str:
        """returns a short label string of all modifications  'norm_t8.1_cx40.3'"""
        mods = []

        # build list of relevant modifications (use short name) 
        for aMod, val in self._modification_dict.items():
                if aMod == Geometry.MOD_TE_GAP:
                    val = round(val,2) 
                elif isinstance (val, float): 
                    val = round(val,1)
                name_val = (aMod, val)
                if not (name_val in mods):                  # avoid duplicates 
                    mods.append ((aMod,val))

        # we got final list of tuples - build string
        label = ''
        for mod_entry in mods:
            val = mod_entry[1]
            val_str = f"{val}" if val is not None else ''
            label = label + '_' + mod_entry[0] + val_str

        return label


    @property
    def x (self): 
        return self._x_org if self._x is None else self._x
        
    @property
    def y (self):
        return self._y_org if self._y is None else self._y

    @property
    def xy (self):
        return self.x, self.y
    

    def _push_xy (self): 
        """ copy xy to _x,_y"""
        self._x = np.copy (self._x_org)
        self._y = np.copy (self._y_org)

 
    def _clear_xy (self): 
        """ clear working _x,_y"""
        self._x = None
        self._y = None 
        self._reset()
 

    def _set_xy (self, x, y):
        """ 
        final set of (valid) xy coordinates 
        - will remove temporary _x,_y
        - will remove lines, splines, """

        # ensure copy of x,y and being numpy 

        if x is not None and y is not None: 
            self._x_org     = np.asarray (x)
            self._y_org     = np.asarray (y)  

        self._x         = None
        self._y         = None 
        self._reset()


    @property
    def iLe (self) -> int: 
        """ the index of leading edge in x coordinate array"""
        return int(np.argmin (self.x))

    @property
    def isNormalized (self):
        """ true if LE is at 0,0 and TE is symmetrical at x=1"""
        return self._isNormalized()

    def _isNormalized (self):
        """ true if LE is at 0,0 and TE is symmetrical at x=1"""

        # LE at 0,0? 
        xle, yle = self.x[self.iLe], self.y[self.iLe]
        normalized =  xle == 0.0 and yle == 0.0

        # TE at 1? - numerical issues happen at the last deicmal (numpy -> python?)  
        xteUp,  yteUp  = self.x[ 0], round(self.y[ 0],10),
        xteLow, yteLow = self.x[-1], round(self.y[-1],10)
        if xteUp != 1.0 or xteLow != 1.0: 
            normalized = False 
        elif yteUp != - yteLow: 
            normalized = False        

        return normalized

    def _isNormalized_spline (self):
        """ true if coordinates AND spline is normalized"""
        # here just dummy 
        return self._isNormalized () 


    @property 
    def panelling (self) -> None:
        """ base - as self can't be paneled return None """
        return None


    @property
    def isLe_closeTo_le_real (self): 
        """ true if LE of x,y coordinates nearly equal to the real (splined) leading edge.
            If not the airfoil should be repaneled... """

        xle, yle   = self.le
        xleS, yleS = self.le_real
        norm2 = np.linalg.norm ([abs(xle-xleS), abs(yle-yleS)])

        return norm2 <= self.EPSILON_LE_CLOSE


    @property
    def isSymmetrical (self) -> bool:
        """ true if lower = - upper"""
        if np.array_equal(self.upper.x,self.lower.x): 
            if np.array_equal(self.upper.y, -self.lower.y):
                return True 
        return False 

    @property
    def isProbablyFlapped (self) -> bool:
        """ true if self is probably flapped"""
        if self.isNormalized: return False 
        if round((self.y[0] + self.y[-1]),4) == 0.0: return False   # te is symmetric around y=0
        return True

    @property
    def isFlapped (self) -> bool:
        """ true if self is flapped (has kink in curvature)"""
        return self.isProbablyFlapped and self.curvature.has_flap_kink

    @property
    def flap_angle_estimated (self) -> float:
        """ returns an estimation of flap angle in degrees if self is flapped""" 
        angle = 0.0 

        if not self.isProbablyFlapped: return angle 

        x_pos = self.curvature.flap_kink_at
        if x_pos:                                                   # calc angle from deflection of TE
            te_y = (self.y[0] + self.y[-1]) / 2
            te_x = (self.x[0] + self.x[-1]) / 2
            angle_rad = math.atan (te_y / (te_x-x_pos))             
            angle = - math.degrees (angle_rad)                      # flap down is positive 

        return round (angle,1) 


    @property
    def le (self) -> tuple: 
        """ coordinates of le defined by the smallest x-value (iLe)"""
        return round(self.x[self.iLe],7), round(self.y[self.iLe],7)      
    
    @property
    def le_real (self) -> tuple: 
        """ coordinates of le defined by spline"""
        # can be overloaded
        # for basic geometry equals to self.le
        return self.le      
    
    @property
    def te (self): 
        """ returns trailing edge upper and lower x,y of point coordinate data """
        return self.x[0], self.y[0], self.x[-1], self.y[-1]
  
    @property
    def te_gap (self) -> float: 
        """ trailing edge gap"""
        return  round(float (self.y[0] - self.y[-1]),7)
    
    @property
    def te_angle (self) -> float: 
        """ trailing edge angle in degrees"""

        x_min = 0.95                        # to avoid noise at TE - take angle at x=0.95..1.0
        upper = self.upper.angle_in_range (x_min=x_min)     # negative
        lower = self.lower.angle_in_range (x_min=x_min)     # positive
        return abs (upper - lower)

    @property
    def le_radius (self) -> float: 
        """ 
        Leading edge radius which is the reciprocal of curvature at le 
        """
        if self.curvature.at_le:
            return round (1.0 / self.curvature.at_le, 7)
        else: 
            return 0.0 

    @property
    def le_curvature (self) -> float: 
        """ 
        Leading edge curvature which is the reciprocal of the le radius 
        """
        if self.curvature.at_le:
            return self.curvature.at_le
        else: 
            return 0.0 


    @property
    def nPanels (self): 
        """ number of panels """
        return self.nPoints - 1
      
    @property
    def nPoints (self): 
        """ number of coordinate points"""
        return len (self.x)



    @property 
    def panelAngle_le (self): 
        """returns the panel angle of the 2 panels at leading edge - should be less 170"""

        # panang1 = atan((zt(2)-zt(1))/(xt(2)-xt(1))) *                &
        #           180.d0/acos(-1.d0)
        # panang2 = atan((zb(1)-zb(2))/(xb(2)-xb(1))) *                &
        #           180.d0/acos(-1.d0)
        # maxpanang = max(panang2,panang1)
        ile = self.iLe
        dx = self.x[ile-1] - self.x[ile]
        dy = self.y[ile-1] - self.y[ile]
        if dx > 0.0:
            angleUp = math.atan (dy/dx) * 180.0 / math.acos(-1)
        else: 
            angleUp = 90 

        dx = self.x[ile+1] - self.x[ile]
        dy = self.y[ile] - self.y[ile+1]
        if dx > 0.0:
            angleLo = math.atan (dy/dx) * 180.0 / math.acos(-1)
        else: 
            angleLo = 90 

        if angleUp < 90.0 and angleLo < 90.0: 
            angle = angleUp + angleLo           # total angle 
        else: 
            angle = 180.0                       # pathologic case with vertical le panel
        return angle 

    @property
    def panelAngle_min (self): 
        """ returns the min angle between two panels - something between 160-180° - 
        and the point index of the min point"""
        return np.min(panel_angles(self.x,self.y)),  np.argmin(panel_angles(self.x,self.y))       


    @property
    def upper(self) -> 'Line': 
        """the upper surface as a line object - where x 0..1"""
        if self._upper is None: 
            self._upper = self.side_class (np.flip (self.x [0: self.iLe + 1]), np.flip (self.y [0: self.iLe + 1]),
                                          linetype=Line.Type.UPPER)
        return self._upper 

    @property
    def lower(self) -> 'Line': 
        """the lower surface as a line object - where x 0..1"""
        if self._lower is None: 
            self._lower =  self.side_class (self.x[self.iLe:], self.y[self.iLe:],
                                           linetype=Line.Type.LOWER)
        return self._lower 

    def side(self, sidetype : Line.Type) -> 'Line': 
        """side with 'side_name' as a line object - where x 0..1"""
        if sidetype == Line.Type.UPPER: 
            return self.upper
        elif sidetype == Line.Type.LOWER:
            return self.lower
        else: 
            return None


    @property
    def camber (self) -> 'Line': 
        """ return the camber line """
        if self._camber is None: 
            self._create_camb_thick()
        return self._camber

    @property
    def thickness (self) -> 'Line': 
        """ the thickness distribution as a line object """
        if self._thickness is None: 
            self._create_camb_thick()
        return self._thickness


    @property
    def max_thick (self) -> float: 
        """ max thickness y/c """
        return self.thickness.highpoint.y

    @property
    def max_thick_x (self) -> float: 
        """ max thickness x/c """
        return self.thickness.highpoint.x

    @property
    def max_camb (self) -> float: 
        """ max camber y/c """
        return self.camber.highpoint.y

    @property
    def max_camb_x (self) -> float: 
        """ max camber x/c """
        return self.camber.highpoint.x


    @property
    def curvature (self) -> Curvature_of_xy: 
        " return the curvature object"
        if self._curvature is None: 
            self._curvature = Curvature_of_xy (self.x, self.y)  
        return self._curvature 


    @property 
    def lines_dict (self) -> dict[Line.Type, Line]:
        """ returns a dict with linetypes and their instances"""
        return {Line.Type.UPPER      : self.upper,
                Line.Type.LOWER      : self.lower,
                Line.Type.THICKNESS  : self.thickness,
                Line.Type.CAMBER     : self.camber}



    def set_te_gap (self, newGap : float, xBlend = TE_GAP_XBLEND, moving=False):
        """ set te gap - must be / will be normalized .

        Args: 
            newGap:   in y-coordinates - typically 0.01 or so 
            xblend:   the blending range from trailing edge 0..1
        """

        try: 
            self._set_te_gap (newGap, xBlend) 
            if not moving:
                self._rebuild_from_upper_lower ()
                self._reset () 
                self._changed (Geometry.MOD_TE_GAP, round(self.te_gap * 100, 2))   # finalize (parent) airfoil 
                self._set_xy (self._x, self._y)
        except GeometryException:
            self._clear_xy()
    

    def _set_te_gap (self, newGap, xBlend = TE_GAP_XBLEND):
        """ set te gap of upper and lower 
         The procedere is based on xfoil allowing to define a blending range from le.

        Arguments: 
            newGap:   in y-coordinates - typically 0.01 or so 
            xblend:   the blending range from trailing edge 0..1
        """

        newGap = clip (newGap, 0.0, 0.1)
        xBlend = clip (xBlend, 0.1, 1.0)

        dgap   = newGap - self.te_gap 

        if dgap == 0.0: return                              # nothing to do

        # create new side objects from x,y to allow repeated setting of te gap 
        self._upper  = self.side_class (np.flip (self.x [0: self.iLe + 1]), np.flip (self.y [0: self.iLe + 1]),
                                 linetype=Line.Type.UPPER)
        self._lower  = self.side_class (self.x[self.iLe:], self.y[self.iLe:],
                                 linetype=Line.Type.LOWER)

        for side in [self._upper, self._lower]:

            y_new = np.zeros (len(side.x))
            for i in range(len(side.x)):
                # thickness factor tails off exponentially away from trailing edge
                if (xBlend == 0.0): 
                    tfac = 0.0
                    if (i == 0 or i == (len(side.x)-1)):
                        tfac = 1.0
                else:
                    arg = min ((1.0 - side.x[i]) * (1.0/xBlend -1.0), 15.0)
                    tfac = np.exp(-arg)

                if side.type == Line.Type.UPPER:
                    y_new[i] = side.y[i] + 0.5 * dgap * side.x[i] * tfac 
                else:
                    y_new[i] = side.y[i] - 0.5 * dgap * side.x[i] * tfac  

            side.set_y (y_new)



    def set_le_radius (self, new_radius : float, xBlend = LE_RADIUS_XBLEND, moving=False):
        """ 
        Set le radius of upper and lower which is the reciprocal of curvature at le
        
        Arguments: 
            new_radius:  new radius to apply 
            xblend:      the blending range from leading edge 0.001..1
        """

        try: 
            self._set_le_radius (new_radius, xBlend) 
            if not moving:
                self._rebuild_from_upper_lower ()
                self._reset () 
                self._changed (Geometry.MOD_LE_RADIUS, round(new_radius*100,2))
                self._set_xy (self._x, self._y)
 
        except GeometryException:
            self._clear_xy()
    

    def set_le_curvature (self, new_curvature : float, xBlend = LE_RADIUS_XBLEND, moving=False):
        """ 
        Set le curvature of upper and lower which is the reciprocal of radius at le
        
        Arguments: 
            new_curvature:   new curvature to apply 
            xblend:          the blending range from leading edge 0.001..1
        """

        if new_curvature: 
            self.set_le_radius (1.0 / new_curvature, xBlend, moving)


    def _set_le_radius (self, new_radius : float, xBlend : float = 0.1):
        """ 
        Set le radius which is the reciprocal of curvature at le 

        The procedere is based on xfoil allowing to define a blending range from le.
        Uses thickness, changes upper and lower side.
        
        Arguments: 
            new_radius:   in y-coordinates - typically 0.01 or so
            xblend:   the blending range from leading edge 0.001..1 - Default 0.1"""


        new_radius = clip (new_radius, 0.001, 0.03)             # limit radius to reasonable values
        xBlend     = clip (xBlend, 0.01, 1.0)  

        # reset curvature so it's rebuild from x,y to get original curvature at LE
        self._curvature = None

        cur_radius = 1 / self.curvature.at_le
        factor     = new_radius / cur_radius

        # go over each thickness point, changing the thickness appropriately

        new_thickness = np.zeros (len(self.thickness.x))  

        for i in range(len(self.thickness.x)):
            # thickness factor tails off exponentially away from trailing edge
            arg = min (self.thickness.x[i] / xBlend, 15.0)
            srfac = (abs (factor)) ** 0.5 
            tfac = 1.0 - (1.0 - srfac) * np.exp(-arg)
            new_thickness [i] = self.thickness.y [i] * tfac

        # create new side objects from x,y to allow repeated setting of te gap 

        self._upper  = self.side_class (self.thickness.x, self.camber.y + new_thickness / 2.0 ,
                                 linetype=Line.Type.UPPER)
        self._lower  = self.side_class (self.thickness.x, self.camber.y - new_thickness / 2.0 ,
                                 linetype=Line.Type.LOWER)
        
        # create new curvature to recalc curvature at LE

        x = np.concatenate ((np.flip(self.upper.x), self.lower.x[1:]))
        y = np.concatenate ((np.flip(self.upper.y), self.lower.y[1:]))

        self._curvature = Curvature_of_xy (x, y) 


    def set_flapped_data (self, x : np.ndarray, y : np.ndarray, 
                          flap_angle : float, x_flap : float):
        """ set flapped x,y data - update geometry 

        Args: 
            x,y:  coordinates of flapped airfoil 
            flap_angle: flap angle of x,y data 
            x_flap: x position of flap
        """

        try: 
            self._set_xy (x, y)
            self._changed (Geometry.MOD_FLAP, f"{flap_angle:.1f}@{x_flap*100:.1f}")   # finalize (parent) airfoil 
        except GeometryException:
            self._clear_xy()
    

 
    def set_max_thick (self, val : float): 
        """ change max thickness"""
        self.set_highpoint_of (self.thickness,(None, val))
        

    def set_max_thick_x (self, val : float): 
        """ change max thickness x position"""
        self.set_highpoint_of (self.thickness,(val,None))


    def set_max_camb (self, val : float): 
        """ change max camber"""
        if not self.isSymmetrical:
            self.set_highpoint_of (self.camber,(None, val))


    def set_max_camb_x (self, val : float): 
        """ change max camber x position"""
        if not self.isSymmetrical:
            self.set_highpoint_of (self.camber,(val, None))
           

    def set_highpoint_of (self, aLine: Line, xy : tuple, finished=True): 
        """ change highpoint of a line - update airfoil """

        try: 
            aLine.set_highpoint (xy)
        except GeometryException: 
            logger.warning (f"{self} set highpoint failed for {aLine}")
            self._clear_xy ()

        if finished: 
            self.finished_change_of (aLine)


    def finished_change_of (self, aLine: Line): 
        """ change highpoint of a line - update geometry """

        if aLine.type == Line.Type.THICKNESS:
            self._rebuild_from_camb_thick ()

            amod = Geometry.MOD_MAX_THICK
            lab = aLine.highpoint.label_percent ()

        elif aLine.type == Line.Type.CAMBER:
            self._rebuild_from_camb_thick ()

            amod = Geometry.MOD_MAX_CAMB
            lab = aLine.highpoint.label_percent ()

        elif aLine.type == Line.Type.UPPER:
            self._rebuild_from_upper_lower ()

            amod = Geometry.MOD_MAX_UPPER
            lab = ' '

        elif aLine.type == Line.Type.LOWER:
            self._rebuild_from_upper_lower ()

            amod = Geometry.MOD_MAX_LOWER
            lab = ' '

        else:
            raise ValueError (f"{aLine.type} not supprted for set_highpoint") 

        self._reset()
        self._normalize()
        self._changed (amod, lab, remove_empty=True)
        self._set_xy (self._x, self._y)


    def _set_max_thick_upper_lower (self, thick_cur : float, thick_new : float):
        """ 
        Set max thickness by direct change of y coordinates of upper and lower side  
            - not via thickness line 
        """

        # currently le must be at 0,0 - te must be at 1,gap/2 (normalized airfoil) 
        if not self._isNormalized():
            raise GeometryException ("Airfoil isn't normalized. Thickness can't be set.")

        # the approach is quite simple: scale all y values by factor new/old

        self.upper.set_y (self.upper.y * thick_new / thick_cur)        
        self.lower.set_y (self.lower.y * thick_new / thick_cur)        


    def upper_new_x (self, new_x) -> np.ndarray: 
        """
        returns upper new y coordinates for new_x coordinates
        
        Using linear interpolation - shall be overloaded 
        """
        # evaluate the corresponding y-values on lower side 
        upper_y = np.zeros (len(new_x))
        for i, x in enumerate (new_x):
            upper_y[i] = self.upper.yFn(x)

        upper_y = np.round(upper_y, 10)

        return upper_y


    def lower_new_x (self, new_x) -> np.ndarray: 
        """
        returns lower new y coordinates for new_x coordinates
        
        Using linear interpolation - shall be overloaded 
        """
        # evaluate the corresponding y-values on lower side 
        lower_y = np.zeros (len(new_x))
        for i, x in enumerate (new_x):
            lower_y[i] = self.lower.yFn(x)

        lower_y = np.round(lower_y, 10)

        return lower_y


    def normalize (self, just_basic=False) -> bool:
        """
        Shift, rotate, scale airfoil so LE is at 0,0 and TE is symmetric at 1,y
        Returns True if normalization was made 

        'just_basic' will only normalize coordinates - not based on spline 
        """

        if just_basic: 
            if self._isNormalized(): return False
        else: 
            if self._isNormalized_spline(): return False

        try: 
            self._push_xy ()                    # ensure a copy of x,y 
            self._normalize() 
            self._changed (Geometry.MOD_NORMALIZE)       # finalize (parent) airfoil 
            self._set_xy (self._x, self._y)

        except GeometryException:
            self._clear_xy()
            return False 

        return True 
    

    def _normalize (self) -> bool:
        """
        Shift, rotate, scale airfoil so LE is at 0,0 and TE is symmetric at 1,y
        
        Returns True if it was normaized in self._x and _y
        """

        if self._isNormalized(): return False

        # current LE shall be new 0,0 
         
        norm2 = self._le_real_norm2 ()
        xLe, yLe = self.le_real
        logger.debug (f"{self} normalize xy: ({xLe:.7f},{yLe:.7f}) - norm2: {norm2:.7f} ")

        # sanity 
        if norm2 > 0.1: 
            raise GeometryException (f"{self} - LE ({xLe},{yLe}) too far away from 0,0 ")
 
        # Translate so that the leading edge is at 0,0 

        xn = self._x - xLe
        yn = self._y - yLe

        # Rotate the airfoil so chord is on x-axis 

        angle = np.arctan2 ((yn[0] + yn[-1])/ 2.0, (xn[0] + xn[-1])/ 2.0) 
        cosa  = np.cos (-angle) 
        sina  = np.sin (-angle) 

        for i in range (len(xn)):
            xni = xn[i]
            yni = yn[i]
            xn[i] = xni * cosa - yni * sina
            yn[i] = xni * sina + yni * cosa

        # sanity - with higher angles (flapped) there could be a new LE 

        ile = np.argmin (xn)

        if ile != self.iLe:

            # yes - LE changed - move and rotate once again 
            xLe, yLe = xn[ile], yn[ile]
            xn = xn - xLe
            yn = yn - yLe

            angle = np.arctan2 ((yn[0] + yn[-1])/ 2.0, (xn[0] + xn[-1])/ 2.0) 
            cosa  = np.cos (-angle) 
            sina  = np.sin (-angle) 

            for i in range (len(xn)):
                xni = xn[i]
                yni = yn[i]
                xn[i] = xni * cosa - yni * sina
                yn[i] = xni * sina + yni * cosa

        # Scale airfoil so that it has a length of 1 
        #  - there are mal formed airfoils with different TE on upper and lower
        #    scale both to 1.0  

        # sanity 
        if xn[0] == 0.0 or xn[-1] == 0.0: 
            raise GeometryException (f"Geometry corrupt during normalize")

        if xn[0] != 1.0 or xn[-1] != 1.0: 
            scale_upper = 1.0 / xn[0]
            scale_lower = 1.0 / xn[-1]

            for i in range (len(xn)):
                if i <= ile:
                    xn[i] = xn[i] * scale_upper
                    yn[i] = yn[i] * scale_upper
                else: 
                    xn[i] = xn[i] * scale_lower
                    yn[i] = yn[i] * scale_lower

        # due to numerical issues ensure 0 is 0.0 ..
        xn[ile] = 0.0 
        yn[ile] = 0.0 
        xn[0]   = 1.0 
        xn[-1]  = 1.0
        yn[-1]  = -yn[0]

        self._x = np.round (xn, 10) + 0.0
        self._y = np.round (yn, 10) + 0.0 

        return 


    def repanel (self, **kwargs):
        """repanel self with a new cosinus distribution 

            to be overloaded
        """
        raise NotImplementedError
    
    def _repanel (self, **kwargs):
        """repanel self with a new cosinus distribution 

            to be overloaded
        """
        pass



    def _blend (self, geo1_in : 'Geometry', geo2_in : 'Geometry', blendBy, moving=False):
        """ blends self out of two geometries depending on the blendBy factor"""

        # ensure geo1 is normalized - to this on a copy 
        
        if not geo1_in._isNormalized():
            geo1 = self.__class__(np.copy(geo1_in.x), np.copy(geo1_in.y))
            geo1.normalize()
        else: 
            geo1 = geo1_in

        # prepare geo2 Geometry to have linear or splined interpolation for blending

        if moving and geo2_in.__class__ != Geometry:
            # ensure geo2 is basic Geometry to have linear interpolation for blending
            geo2 = Geometry (np.copy(geo2_in.x), np.copy(geo2_in.y))
        elif not moving and  geo2_in.__class__ == Geometry:
            # ensure geo2 has no basic Geometry 
            from .geometry_spline import Geometry_Splined
            geo2 = Geometry_Splined (np.copy(geo2_in.x), np.copy(geo2_in.y))  
        else: 
            geo2 = geo2_in

        # ensure geo2 is normalized - to this on a copy 

        if not geo2._isNormalized():
            geo2 = self.__class__(np.copy(geo2.x), np.copy(geo2.y))
            geo2.normalize()
        
        # blend - optimze edge cases 

        blendBy = clip (blendBy, 0.0, 1.0)

        if blendBy == 0:
            self._x = np.copy(geo1.x)                       # take 1st arifoil
            self._y = np.copy(geo1.y)
            return
        elif blendBy == 1.0:
            self._x = np.copy(geo2.x)                       # take 2nd airfoil
            self._y = np.copy(geo2.y)
            return
      
        upper1  = geo1.upper
        lower1  = geo1.lower
        x_upper = geo1.upper.x
        x_lower = geo1.lower.x

        upper2_y = geo2.upper_new_x (x_upper)
        lower2_y = geo2.lower_new_x (x_lower)


        # now blend upper and lower of both airfoils 
        y_upper = (1 - blendBy) * upper1.y + blendBy * upper2_y
        y_lower = (1 - blendBy) * lower1.y + blendBy * lower2_y
        
        # rebuild x,y coordinates 
        self._rebuild_from (x_upper, y_upper, x_lower, y_lower)



    def blend (self, geo1 : 'Geometry', geo2 : 'Geometry', blendBy : float, moving=False):
        """ blends  self out of two geometries depending on the blendBy factor"""

        if geo1 and geo2: 
            
            self._blend (geo1, geo2, blendBy, moving=moving)   

            if not moving:      
                self._set_xy (self._x, self._y)
                self._changed (Geometry.MOD_BLEND, f"{blendBy*100:.0f}")


    # ------------------ private ---------------------------

    def _le_real_norm2 (self) -> float:
        """ norm2 of le_real coordinates """

        xLe, yLe = self.le_real
        return np.linalg.norm ([abs(xLe), abs(yLe)])


    def _create_camb_thick (self): 
        """
        creates thickness and camber distribution as Side_Airfoil objects
        with a x-distribution of the upper side.
        
        Using linear interpolation - shall be overloaded 

        Note: It's an approximation as thickness is just the sum of y_upper(x) and y_lower(x)
              and camber is just the mean value y_upper(x) and y_lower(x)
        """

        # evaluate the corresponding y-values on lower side 

        # handle not normalized airfoil - without changing self
        #   --> tmp new geo which will be normalized 

        if not self._isNormalized():
            logger.debug (f"{self} normalizing for thickness ")
            geo_norm = self.__class__(np.copy(self.x), np.copy(self.y))
            geo_norm._push_xy ()                        # init _x,_y
            geo_norm._normalize()

            if not geo_norm._isNormalized():
                logger.error (f"{self} normalizing failed ")
            upper = geo_norm.upper
            lower_y = geo_norm.lower_new_x (upper.x) 
        else: 
            upper = self.upper
            from timeit import default_timer as timer
            start = timer()

            lower_y = self.lower_new_x (upper.x)
            end = timer()
            logger.debug (f"Time lower calculation for {self}: {end - start:.4f} seconds")

        # sanity 
        
        if  not upper.isNormalized:
            raise GeometryException (f"{self} _create_camb_thick: Upper and Lower are not normalized")

        # thickness and camber can now easily calculated 

        thickness_y = np.round (upper.y - lower_y, 10)  
        camber_y    = np.round ((upper.y + lower_y) / 2.0, 10 ) 

        # for symmetric airfoil with unclean data set camber line to 0 
        
        if np.max(camber_y) < 0.00001: 
            camber_y = np.zeros (len(camber_y))

        self._thickness = self.line_class (upper.x, thickness_y, 
                                            linetype=Line.Type.THICKNESS)

        self._camber    = self.line_class (upper.x, camber_y, 
                                            linetype=Line.Type.CAMBER)
        return 


    def _rebuild_from (self, x_upper, y_upper, x_lower, y_lower):
        """ rebuilds self out upper and lower x and y values  """

        self._x = np.concatenate ((np.flip(x_upper), x_lower[1:]))
        self._y = np.concatenate ((np.flip(y_upper), y_lower[1:]))


    def _rebuild_from_upper_lower (self):
        """ rebuilds self out upper and lower side"""

        self._rebuild_from (self.upper.x, self.upper.y, self.lower.x, self.lower.y)


    def _rebuild_from_camb_thick(self):
        """ rebuilds self out of thickness and camber distribution """

        # x values of camber and thickness must be equal
        if not np.array_equal (self.thickness.x, self.camber.x):
            raise ValueError ("Geo rebuild: x-values of thickness and camber are not equal")
        if not self.thickness.isNormalized or not self.camber.isNormalized:
            raise ValueError ("Geo rebuild: Thickness or Camber are not normalized")

        # easy sum of thickness and camber to get new airfoil 

        x_upper = self.thickness.x
        y_upper = self.camber.y + self.thickness.y / 2.0 
        x_lower = self.thickness.x
        y_lower = self.camber.y - self.thickness.y / 2.0

        self._rebuild_from (x_upper, y_upper, x_lower, y_lower)

        # retain the old panel distribution 
        # self._repanel (retain=True) does not work 


    def _reset (self):
        """ reset all the sub objects like Lines and Splines"""
        self._reset_lines()
        self._reset_spline() 


    def _reset_lines (self):
        """ reinit the dependand lines of self""" 
        self._upper      = None                 # upper side 
        self._lower      = None                 # lower side 
        self._thickness  = None                 # thickness distribution
        self._camber     = None                 # camber line
        self._curvature  = None                 # curvature 

    def _reset_spline (self):
        """ reinit self spline data if x,y has changed""" 
        # to be overloaded


# ------------ test functions - to activate  -----------------------------------


if __name__ == "__main__":

    # ---- Test -----

    pass