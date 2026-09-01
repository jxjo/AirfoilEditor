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
            |-- Curvature_of_Spline                 - based on spline (in geometry_spline)
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

from timeit                 import default_timer as timer
from enum                   import Enum
from typing                 import override

import math
import numpy as np

from ..base.common_utils    import clip, StrEnum_Extended, fromDict, toDict
from ..base.math_util       import JPoint, newton, panel_angles
from ..base.spline          import Spline1D, Spline2D, build_local_spline1d

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)



class GeometryException(Exception):
    """ raised when geometry calculation failed """
    pass


class geo_parm (StrEnum_Extended):
    """Shared geometry parameter keys used across model/UI code."""

    THICKNESS       = "Thickness"
    THICKNESS_AT    = "Thickness At"
    CAMBER          = "Camber"

    TE_ANGLE        = "TE Angle"
    TE_ANGLE_UPPER  = "TE Angle Upper"
    TE_ANGLE_LOWER  = "TE Angle Lower"
    TE_CURV_UPPER   = "TE Curvature Upper"
    TE_CURV_LOWER   = "TE Curvature Lower"

    LE_CURV         = "LE Curvature"

    FLAP_ANGLE      = "Flap Angle"


# -----------------------------------------------------------------------------
#  Flap handling  
# -----------------------------------------------------------------------------

class Flap_Definition:
    """ 

    Defines the geometry of a flap 

    With set_flap a flapped version of the original airfoil is returned   

    """

    @staticmethod
    def have_same_hinge (flap_def1 : 'Flap_Definition', flap_def2 : 'Flap_Definition') -> bool:
        """
        Compare 2 flap definitions if they have the same hinge definition
        Return True if they are the same or both have no flap_def1
        """
        if flap_def1 and flap_def2:
            return  flap_def1.x_flap == flap_def2.x_flap and \
                    flap_def2.y_flap == flap_def2.y_flap and \
                    flap_def1.y_flap_spec == flap_def2.y_flap_spec
        elif flap_def1 is None and flap_def2 is None:
            return True
        else: 
            return False
        

    def __init__(self, dataDict : dict = None):
        """
        """

        self._x_flap        = fromDict (dataDict, "x_flap", 0.75)
        self._y_flap        = fromDict (dataDict, "y_flap", 0.0) 
        self._y_flap_spec   = fromDict (dataDict, "y_flap_spec", 'y/t')
        self._flap_angle    = fromDict (dataDict, "flap_angle", 0.0) 


    def _as_dict (self):
        """ returns a data dict with the parameters of self """

        d = {}
        toDict (d, "x_flap",        self.x_flap)                  
        toDict (d, "y_flap",        self.y_flap) 
        toDict (d, "y_flap_spec",   self.y_flap_spec) 
        toDict (d, "flap_angle",    self.flap_angle) 
        return d


    @property
    def x_flap (self) -> float: 
        return self._x_flap

    def set_x_flap (self, aVal : float):
        self._x_flap = clip (aVal, 0.02, 0.98)

    @property
    def y_flap (self) -> float: 
        return self._y_flap

    def set_y_flap (self, aVal : float):
        self._y_flap = clip (aVal, 0.0, 1.0)

    @property
    def y_flap_spec (self) -> str: 
        return self._y_flap_spec

    def set_y_flap_spec (self, aVal : str):
        self._y_flap_spec = aVal if aVal in ['y/c', 'y/t'] else self._y_flap_spec

    @property
    def flap_angle (self) -> float: 
        return self._flap_angle

    def set_flap_angle (self, aVal : float):
        self._flap_angle = clip (aVal, -20.0, 20.0)


class Flap_Setter (Flap_Definition):
    """Build a flapped airfoil without mutating the original outline.

    The class copies the source upper/lower lines once and then derives a new
    flapped geometry from that local copy. Convex and concave sides are handled
    separately, and each operation stays local to the hinge region instead of
    re-parameterizing the whole airfoil.
    """

    def __init__(self, upper: 'Line', lower: 'Line'):
        """Keep a clean copy of the original upper and lower side."""

        super().__init__()

        # Preserve the original geometry; all flap changes are built on the copies.
        self._upper = Line (upper.x.copy(), upper.y.copy(), linetype=Line.Type.UPPER)
        self._lower = Line (lower.x.copy(), lower.y.copy(), linetype=Line.Type.LOWER)


    def set_flap_definition (self, flap_def : 'Flap_Definition'):
        """Set this setter from an existing flap definition object."""

        if isinstance(flap_def, Flap_Definition):
            self.set_x_flap (flap_def.x_flap)
            self.set_y_flap (flap_def.y_flap)
            self.set_y_flap_spec (flap_def.y_flap_spec)
            self.set_flap_angle (flap_def.flap_angle)


    @staticmethod
    def _find_hinge_footpoint(side_x, side_y, x_hinge, y_hinge):
        """Find the local hinge footpoint on the side spline.

        Used for the convex side: the flap tail is rotated around the hinge, and
        the footpoint marks where the fixed section meets the rotated section.
        """
        side_x = np.asarray(side_x, dtype=float)
        side_y = np.asarray(side_y, dtype=float)

        if side_x.size < 2:
            return float(x_hinge), float(y_hinge)

        local_spline, i0, i1 = build_local_spline1d(
            side_x, side_y,
            x_center=float(x_hinge),
            i_radius=5)
        if local_spline is None:
            return float(x_hinge), float(y_hinge)

        local_x = side_x[i0:i1]
        local_y = side_y[i0:i1]

        def f_distance(x):
            y     = local_spline.eval(float(x))
            dy_dx = local_spline.eval(float(x), der=1)
            return 2.0 * (float(x) - x_hinge) + 2.0 * (y - y_hinge) * dy_dx

        def df_distance(x):
            y       = local_spline.eval(float(x))
            dy_dx   = local_spline.eval(float(x), der=1)
            ddy_dx2 = local_spline.eval(float(x), der=2)
            return 2.0 + 2.0 * (dy_dx * dy_dx + (y - y_hinge) * ddy_dx2)

        x_guess = float(np.clip(x_hinge, local_x[0], local_x[-1]))
        x_low = float(local_x[0])
        x_high = float(local_x[-1])

        try:
            x0, _ = newton(
                f_distance,
                df_distance,
                x_guess,
                epsilon=1e-10,
                max_iter=25,
                bounds=(x_low, x_high),
            )
        except ValueError:
            i_min = int(np.argmin((local_x - x_hinge) ** 2 + (local_y - y_hinge) ** 2))
            x0 = float(local_x[i_min])

        y0 = float(local_spline.eval(x0))
        return float(x0), float(y0)


    @staticmethod
    def _get_additional_points_for_gap (side_x, side_y, x_hinge, y_hinge, x0, y0, beta_rad) -> tuple[list[float], list[float]]:
        """Add a short arc to smooth the convex hinge transition."""

        add_x, add_y = [], []

        cos_b, sin_b = np.cos(beta_rad), np.sin(beta_rad)

        # Rotate the hinge footpoint according to the flap deflection to obtain the
        # endpoint of the local arc in flap coordinates.
        x1 = x_hinge + (x0 - x_hinge) * cos_b - (y0 - y_hinge) * sin_b
        y1 = y_hinge + (x0 - x_hinge) * sin_b + (y0 - y_hinge) * cos_b

        # The arc length of the flap transition is compared with the current local
        # side spacing, so we only append extra points when the geometry gap is
        # large enough to justify a smoothing arc.
        arc_length = np.hypot(x1 - x0, y1 - y0)

        idx0 = np.searchsorted(side_x, x0) - 1
        idx0 = max(0, idx0)
        idx1 = min(len(side_x) - 1, idx0 + 2)
        arc_length_current = np.sum(np.hypot(np.diff(side_x[idx0:idx1+1]), np.diff(side_y[idx0:idx1+1])))

        if arc_length > 0.1 * arc_length_current:
            # The smooth arc is placed around the hinge and only spans the short
            # transition between the original curve and the rotated flap tail.
            radius = np.hypot(x0 - x_hinge, y0 - y_hinge)
            theta_start = np.arctan2(y0 - y_hinge, x0 - x_hinge)
            theta_end   = theta_start + beta_rad

            npoints = int(arc_length * 4 / arc_length_current) + 1
            theta_vals = np.linspace(theta_start, theta_end, npoints+2)[1:-1]

            add_x = x_hinge + radius * np.cos(theta_vals)
            add_y = y_hinge + radius * np.sin(theta_vals)

        return add_x, add_y


    @staticmethod
    def _process_convex_side (side_x, side_y, x_hinge, y_hinge, beta_degrees):
        """Rotate the convex flap tail and bridge the hinge with a short arc."""
        beta_rad = np.radians(-beta_degrees)
        cos_b, sin_b = np.cos(beta_rad), np.sin(beta_rad)

        # The hinge footpoint defines where the original surface meets the rotated
        # flap tail. Everything left of this point is kept fixed.
        x0, y0 = Flap_Setter._find_hinge_footpoint(side_x, side_y, x_hinge, y_hinge)

        main_mask = side_x < x0
        flap_mask = side_x > x0

        x_flap = side_x[flap_mask]
        y_flap = side_y[flap_mask]

        flapped_x = x_hinge + (x_flap - x_hinge) * cos_b - (y_flap - y_hinge) * sin_b
        flapped_y = y_hinge + (x_flap - x_hinge) * sin_b + (y_flap - y_hinge) * cos_b

        main_x = side_x[main_mask]
        main_y = side_y[main_mask]

        add_x, add_y = Flap_Setter._get_additional_points_for_gap(
            side_x, side_y, x_hinge, y_hinge, x0, y0, beta_rad
        )

        side_x_new = np.concatenate([main_x, add_x, flapped_x])
        side_y_new = np.concatenate([main_y, add_y, flapped_y])

        return side_x_new, side_y_new


    @staticmethod
    def _find_concave_corner (side_x, side_y, x_hinge, y_hinge, beta_degrees):
        """Find the real concave hinge corner in the local spline neighborhood."""
        side_x = np.asarray(side_x, dtype=float)
        side_y = np.asarray(side_y, dtype=float)

        if side_x.size < 2:
            return float(x_hinge), float(y_hinge)

        if np.any(np.isclose(side_x, x_hinge, rtol=0.0, atol=1e-12) &
                  np.isclose(side_y, y_hinge, rtol=0.0, atol=1e-12)):
            return float(x_hinge), float(y_hinge)

        idx = int(np.searchsorted(side_x, x_hinge))
        main_spline, i0, i1 = build_local_spline1d(
            side_x, side_y,
            x_center=float(x_hinge),
            i_radius=5)

        if main_spline is None:
            return float(x_hinge), float(y_hinge)

        local_x = side_x[i0:i1].copy()
        local_y = side_y[i0:i1].copy()

        beta_rad = np.radians(-beta_degrees)
        cos_b, sin_b = np.cos(beta_rad), np.sin(beta_rad)

        dx_f = local_x - x_hinge
        dy_f = local_y - y_hinge
        x_rot = x_hinge + dx_f * cos_b - dy_f * sin_b
        y_rot = y_hinge + dx_f * sin_b + dy_f * cos_b

        local_x = np.asarray(local_x, dtype=float)
        local_y = np.asarray(local_y, dtype=float)
        x_rot = np.asarray(x_rot, dtype=float)
        y_rot = np.asarray(y_rot, dtype=float)

        center_local_idx = int(np.clip(idx - i0, 0, len(x_rot) - 1))
        flap_spline, _, _ = build_local_spline1d(
            x_rot, y_rot,
            i_center=center_local_idx,
            i_radius=5)
        if flap_spline is None:
            return float(x_hinge), float(y_hinge)

        def f_corner(x):
            return main_spline.eval(float(x)) - flap_spline.eval(float(x))

        def df_corner(x):
            return main_spline.eval(float(x), der=1) - flap_spline.eval(float(x), der=1)

        x_low = float(np.min(np.concatenate([local_x, x_rot])))
        x_high = float(np.max(np.concatenate([local_x, x_rot])))
        x_guess = x_hinge + max(1e-8, 1e-6 * max(1.0, abs(x_hinge)))

        try:
            x_corner, _ = newton(f_corner, df_corner, x_guess,
                                epsilon=1e-10, max_iter=25,
                                bounds=(x_low, x_high))
        except ValueError:
            logger.error(f"Newton's method failed to converge for concave corner. Using fallback search.")
            x_corner = x_guess

        y_corner = float(main_spline.eval(x_corner))
        return float(x_corner), float(y_corner)


    @staticmethod
    def _repanel_around_corner(side_x: np.ndarray, side_y: np.ndarray, x_corner: float, y_corner: float):
        """Repanel the immediate neighbours of a real corner without crossing it.

        One local window centred on the corner yields a single arc-length trigger.
        Left of the corner: move the preceding point away if it sits too close.
        Right of the corner: the corner stays fixed; move the following point if needed.
        """
        side_x = np.asarray(side_x, dtype=float)
        side_y = np.asarray(side_y, dtype=float)

        corner_matches = np.flatnonzero(np.isclose(side_x, x_corner, rtol=0.0, atol=1e-12))
        if corner_matches.size == 0:
            raise ValueError("Corner point is required for around-corner repaneling.")

        corner_idx = int(corner_matches[0])

        # One shared window around the corner; spacing derived from full local arc-length.
        i0 = max(0, corner_idx - 5)
        i1 = min(len(side_x), corner_idx + 6)
        win_x = side_x[i0:i1]
        win_y = side_y[i0:i1]
        local_arc = np.hypot(np.diff(win_x), np.diff(win_y))
        positive_arc = local_arc[local_arc > 0]
        local_spacing = np.median(positive_arc) if positive_arc.size else 1e-6
        trigger = 0.30 * local_spacing

        def _nudge (i_neighbor, direction):
            """Move i_neighbor by trigger in direction (+1 or -1) along the side spline."""
            mask = (win_x <= x_corner) if direction < 0 else (win_x >= x_corner)
            lx, ly = win_x[mask], win_y[mask]
            if lx.size < 3:
                return
            spline = Spline1D(lx, ly, boundary='natural')
            x_target = side_x[i_neighbor] + direction * trigger
            if direction < 0 and i_neighbor > 0:
                x_target = max(x_target, side_x[i_neighbor - 1] + 1e-12)
            if direction > 0 and i_neighbor < len(side_x) - 1:
                x_target = min(x_target, side_x[i_neighbor + 1] - 1e-12)
            x_target = float(np.clip(x_target, spline.x[0], spline.x[-1]))
            side_x[i_neighbor] = x_target
            side_y[i_neighbor] = float(spline.eval(x_target))

        # Left side: nudge the point just before the corner when it sits too close.
        if corner_idx > 0:
            i_left = corner_idx - 1
            if i_left >= i0 and np.hypot(side_x[i_left] - x_corner, side_y[i_left] - y_corner) < trigger:
                _nudge(i_left, direction=-1)

        # Right side: keep the corner fixed; nudge the point just after it when needed.
        if corner_idx < len(side_x) - 1:
            i_right = corner_idx + 1
            if np.hypot(side_x[i_right] - x_corner, side_y[i_right] - y_corner) < trigger:
                _nudge(i_right, direction=+1)

        return side_x, side_y


    @staticmethod
    def _process_concave_side (side_x, side_y, x_hinge, y_hinge, beta_degrees):
        """Build the concave side with a real corner and a rotated flap tail."""
        beta_rad = np.radians(-beta_degrees)

        side_x = np.asarray(side_x, dtype=float)
        side_y = np.asarray(side_y, dtype=float)
        x_corner, y_corner = Flap_Setter._find_concave_corner(
            side_x, side_y, x_hinge, y_hinge, beta_degrees)

        main_mask = side_x < x_corner
        x_main = np.append(side_x[main_mask], x_corner)
        y_main = np.append(side_y[main_mask], y_corner)

        flap_mask = side_x >= x_corner
        x_flap = side_x[flap_mask]
        y_flap = side_y[flap_mask]

        if x_flap.size == 0:
            return Flap_Setter._repanel_around_corner(x_main, y_main, x_corner, y_corner)

        dx_f = x_flap - x_hinge
        dy_f = y_flap - y_hinge
        x_flap_rot = x_hinge + dx_f * np.cos(beta_rad) - dy_f * np.sin(beta_rad)
        y_flap_rot = y_hinge + dx_f * np.sin(beta_rad) + dy_f * np.cos(beta_rad)

        keep_mask = x_flap_rot > x_corner + 1e-12
        x_flap_rot = x_flap_rot[keep_mask]
        y_flap_rot = y_flap_rot[keep_mask]

        side_x_new = np.concatenate([x_main, x_flap_rot])
        side_y_new = np.concatenate([y_main, y_flap_rot])

        # One small repair step around the real corner keeps the spline local and stable.
        return Flap_Setter._repanel_around_corner(side_x_new, side_y_new, x_corner, y_corner)


    @property
    def hinge_point (self) -> tuple[float, float]:
        """ returns the hinge point (x, y) of the flap """

        y_h_upper = self._upper.yFn(self.x_flap, splined=True)
        y_h_lower = self._lower.yFn(self.x_flap, splined=True)

        if self.y_flap_spec == 'y/t':
            local_thickness = y_h_upper - y_h_lower
            y_hinge = y_h_lower + (self.y_flap * local_thickness)
        elif self.y_flap_spec == 'y/c':
            y_hinge = y_h_lower + self.y_flap
        else:
            raise ValueError (f"Invalid y_flap_spec: {self.y_flap_spec}")

        return self.x_flap, y_hinge


    def set_flap (self, flap_angle: float | None = None, flap_def: Flap_Definition | None = None) -> tuple['Line', 'Line']:
        """
        Main flap routine. Do flapping for the concave/convex surfaces.

        Args:
            flap_angle: Optional float, the flap deflection angle in degrees.
            flap_def: Optional Flap_Definition object to set angle and the hinge parameters.
        """

        # don't do anything for flap angle = 0 
        if flap_angle is not None: 
            self.set_flap_angle (flap_angle)
        elif isinstance(flap_def, Flap_Definition):
            self.set_flap_definition (flap_def)

        if self.flap_angle == 0.0: 
            return self._upper, self._lower

        upper_x, upper_y = self._upper.x, self._upper.y
        lower_x, lower_y = self._lower.x, self._lower.y

        # Determine local thickness and vertical hinge pivot coordinate
        x_hinge = self.x_flap

        y_h_upper = Line.yFn_splined(x_hinge, upper_x, upper_y)
        y_h_lower = Line.yFn_splined(x_hinge, lower_x, lower_y)
        y_hinge = y_h_lower + (self.y_flap * (y_h_upper - y_h_lower))
        
        # Evaluate routing distribution based on deflection angle
        if self.flap_angle >= 0:
            # DOWNWARD Deflection: Upper surface is convex, Lower surface is concave
            upper_x_new, upper_y_new = self._process_convex_side  (upper_x, upper_y, x_hinge, y_hinge, self.flap_angle)
            lower_x_new, lower_y_new = self._process_concave_side (lower_x, lower_y, x_hinge, y_hinge, self.flap_angle)
        else:
            # UPWARD Deflection: Upper surface is concave, Lower surface is convex
            upper_x_new, upper_y_new = self._process_concave_side (upper_x, upper_y, x_hinge, y_hinge, self.flap_angle)
            lower_x_new, lower_y_new = self._process_convex_side  (lower_x, lower_y, x_hinge, y_hinge, self.flap_angle)

        upper_new = Line(upper_x_new, upper_y_new, linetype=Line.Type.UPPER)
        lower_new = Line(lower_x_new, lower_y_new, linetype=Line.Type.LOWER)
    
        return upper_new, lower_new



# -----------------------------------------------------------------------------
#  Panel Distribution  
# -----------------------------------------------------------------------------


class Paneling:
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
        return Paneling.nPanels_for(linetype, self.nPanels)


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
            total_nPanels = Paneling.N_PANELS_DEFAULT
        
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
        Used by Paneling_Spline directly as u, and by curve-based pannelling
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

        self._values        = None                  # curvature values at knots 0..npoints    

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
        # At the LE, a round nose (e.g. CST with n1=0.5) has a vertical tangent, so
        # dy/dx (and therefore nx) is +-inf there - the limiting unit normal is
        # horizontal (+-1, 0). Handle that case explicitly instead of letting
        # inf/inf produce nan (which would silently drop the LE comb line).
        nn = np.sqrt(nx**2 + ny**2)
        le_mask = np.isinf(nn)
        with np.errstate(divide="ignore", invalid="ignore"):
            nx = np.where(le_mask, np.sign(nx), nx / nn)
            ny = np.where(le_mask, 0.0, ny / nn)

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
    def max_is_at_le (self) -> bool: 
        """ True if max value of curvature is at LE"""
        return self.iLe is not None and math.isclose (abs(self.values[self.iLe]), self.max, abs_tol=1e-6)


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

        if math.isclose (upper_x_max, lower_x_max, abs_tol=0.015):
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
    isCST           = False
    isHicksHenne    = False

    CURV_THRESHOLD  = 0.01                      # threshold for curvature to be counted as reversal 
    TE_ANGLE_RANGE  = (0.9, 1.0)                # x range to calculate TE angle - ! sync with xo2
    
    # ----------------------------------------------

    def __init__ (self, x,y, 
                  linetype : Type |None = None, 
                  name : str|None = None):

        self._x         = np.array(x)
        self._y         = np.array(y)
        self._type      = linetype 
        self._name      = name 
        self._highpoint = None                  # the high Point of the line  


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
        self._reset()
    
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



    def reversals (self, x_start= 0.1, x_end=1.0, smooth=True, threshold=CURV_THRESHOLD) -> np.ndarray:
        """ 
        returns the x positions of reversals (change of y sign) on self. 
        Smoothing with a moving average can be applied to avoid false positives.
        Take only y values > threshold into account to avoid noise driven sign changes.
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

        if threshold > 0.0:
            mask      = np.abs(curv_body) > threshold
            x_body    = x_body    [mask]
            curv_body = curv_body [mask]

        sign_change_indices = np.where (curv_body[:-1] * curv_body[1:] < 0)[0]
        sign_change_x       = x_body [sign_change_indices]         # x positions of sign changes
    
        return sign_change_x


    def nreversals (self, x_start= 0.1, x_end=1.0, smooth=True, threshold=CURV_THRESHOLD) -> int:
        """ 
        returns the number of reversals (change of y sign) on self. 
        Smoothing with a moving average can be applied to avoid false positives.
        Take only y values > threshold into account to avoid noise driven sign changes.
        """

        return len (self.reversals (x_start, x_end, smooth, threshold))

    

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



    @staticmethod
    def yFn_splined(x: float, x_data: np.ndarray, y_data: np.ndarray) -> float:
        """Return a local spline-interpolated y value for a single x.

        A small cubic spline is built from neighboring points around x, which
        provides a more accurate value than plain linear interpolation near curved
        segments while keeping the operation local and fast.
        """
        x_arr = np.asarray(x_data, dtype=float)
        y_arr = np.asarray(y_data, dtype=float)

        if x_arr.size < 2:
            return float(y_arr[0])

        x_val = float(x)
        if x_val <= x_arr[0]:
            return float(y_arr[0])
        if x_val >= x_arr[-1]:
            return float(y_arr[-1])

        local_spline, _, _ = build_local_spline1d(
            x_arr, y_arr,
            x_center=x_val, i_radius=2)
        if local_spline is None:
            return float(np.interp(x_val, x_arr, y_arr))

        return float(local_spline.eval(x_val))


    def yFn (self, x, splined: bool = False):
        """Return interpolated y values based on x.

        With splined=True, use a local spline around x for higher accuracy on curved
        segments. The default keeps the original linear interpolation behavior.
        """
        if splined and np.isscalar(x):
            return self.yFn_splined(x, self.x, self.y)
        else: 
            return np.interp(x, self.x, self.y)


    def angle_in_range (self, x_range = (0.9, 1.0)) -> float:
        """
        Computes tangent angle in degrees in x-range [x_min, x_max].

        If the tangent is falling down, angle is positive.
        If the tangent is rising, angle is negative.
        """
        x_min, x_max = x_range[0], x_range[1]

        # Select points within the chosen x-range
        mask = (self.x >= x_min) & (self.x <= x_max)
        x_sel = self.x[mask]
        y_sel = self.y[mask]

        if len(x_sel) < 2:
            if len(self.x) < 2:
                return 0.0
            x_sel = self.x[-2:]
            y_sel = self.y[-2:]

        n_dp = float(len(x_sel))
        sum_x = np.sum(x_sel)
        sum_y = np.sum(y_sel)
        sum_xy = np.sum(x_sel * y_sel)
        sum_x2 = np.sum(x_sel * x_sel)

        # Linear regression slope: y = slope*x + intercept
        denom = n_dp * sum_x2 - sum_x * sum_x
        if np.isclose(denom, 0.0):
            return 0.0

        slope = (n_dp * sum_xy - sum_x * sum_y) / denom

        # Sign follows Xoptfoil2 convention: falling tangent is positive.
        angle_deg = -np.degrees(np.arctan(slope))

        return angle_deg


    @property
    def te_angle (self) -> float:
        """ 
        Angle at TE in degrees - positive is downward, negative upward
        The angle is calculated by linear regression of the last few points in the TE_ANGLE_RANGE.
        """

        return self.angle_in_range (self.TE_ANGLE_RANGE)


    @property
    def te_gap (self):
        """ 
        Returns signed y value of the y point which is half the TE gap.
        """
        return self.y[-1]


    def set_te_gap (self, te_gap : float, xBlend : float = None, moving=False):
        """
        Apply a trailing-edge gap to this side. Sign of the gap is applied based on the side type (upper/lower). 
        The gap is blended over a specified range from the trailing edge.

        Args:
            te_gap: ! half of the airfoil trailing-edge gap !
            xBlend: blending range from trailing edge, 0.0..1.0
            moving: compatibility flag for curve-based sides; ignored for basic Line.
        """
        # sign sanity
        if self.type == Line.Type.UPPER:
            dgap = -(abs(self.te_gap) - abs(te_gap))
        elif self.type == Line.Type.LOWER:
            dgap = abs(self.te_gap) - abs(te_gap)

        if xBlend is None:
            xBlend = Geometry.TE_GAP_XBLEND

        if dgap == 0.0:
            pass                # xBlend could have been changed

        y_new = np.zeros (len(self.x))
        for i in range(len(self.x)):
            # Thickness factor tails off exponentially away from trailing edge.
            if xBlend == 0.0:
                tfac = 0.0
                if i == 0 or i == (len(self.x) - 1):
                    tfac = 1.0
            else:
                arg = min ((1.0 - self.x[i]) * (1.0 / xBlend - 1.0), 15.0)
                tfac = np.exp(-arg)

            y_new[i] = self.y[i] + dgap * self.x[i] * tfac
 
        self.set_y (y_new)


    @staticmethod
    def insert_point_at_x(side_x : np.ndarray, side_y: np.ndarray, x_new: float, y_new: float = None):
        """
        Inserts a new point at the specified x-coordinate. If y_new is not provided, it will be interpolated.

        Args:
            side_x: The x-coordinates of the existing points.
            side_y: The y-coordinates of the existing points.
            x_new: The x-coordinate where the new point should be inserted.
            y_new: The y-coordinate of the new point. If None, it will be interpolated.
        """
        if y_new is None:
            y_new = Line.yFn_splined(x_new, side_x, side_y)

        # Find the index where to insert the new point
        idx = np.searchsorted(side_x, x_new)

        # Insert the new point into x and y arrays
        side_x = np.insert(side_x, idx, x_new)
        side_y = np.insert(side_y, idx, y_new)

        return side_x, side_y

    # ------------------ private ---------------------------


    def _get_maximum (self) -> tuple[float, float]: 
        """ 
        calculates and returns the x,y position of the maximum y value of self
            If self is symmetrical return (0.5,0)  
        """
        max_y = abs(np.max(self.y))
        min_y = abs(np.min(self.y))

        if max_y == 0.0 and min_y == 0.0:
            return 0.5, 0.0

        x = self.x
        is_upper_side = max_y >= min_y

        # Reverse lower-side values so the local search always targets a maximum.
        y = self.y if is_upper_side else self.y * -1.0
        imax = int(np.argmax(y))

        xmax = float(x[imax])
        ymax = float(y[imax])

        # Refine the discrete maximum with a local spline when there is enough neighborhood.
        if 3 < imax < len(self.x) - 3:
            local_spline, i0, i1 = build_local_spline1d(
                x, y,
                i_center=imax, boundary='notaknot')

            if local_spline is not None:
                x_local = x[i0:i1]
                y_local = y[i0:i1]

                bounds = (float(x_local[0]), float(x_local[-1]))
                x_guess = float(np.clip(xmax, bounds[0], bounds[1]))

                xmax_newton = None
                try:
                    xmax_newton, _ = newton(
                        lambda x_val: local_spline.eval(float(x_val), der=1),
                        lambda x_val: local_spline.eval(float(x_val), der=2),
                        x_guess,
                        epsilon=1e-10,
                        max_iter=25,
                        bounds=bounds)
                except ValueError:
                    pass

                newton_is_valid = (
                    xmax_newton is not None
                    and np.isfinite(xmax_newton)
                    and bounds[0] <= xmax_newton <= bounds[1]
                    and float(local_spline.eval(xmax_newton, der=2)) <= 0.0)

                if newton_is_valid:
                    xmax = float(xmax_newton)
                    ymax = float(local_spline.eval(xmax))
                else:
                    i_local_max = int(np.argmax(y_local))
                    xmax = float(x_local[i_local_max])
                    ymax = float(y_local[i_local_max])

        if not is_upper_side:
            ymax = -ymax

        return round(xmax, 7), round(ymax, 7)



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
        self._reset()
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
        self._reset()

        return y_new 
           

    def _reset (self):
        """ reinit self if x,y has changed""" 
        self._highpoint = None


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
    isCST           = False
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

        self._te_gap_xBlend    = None           # x position from TE where te gap blending starts
        self._le_radius_xBlend = None           # x position from LE where le radius blending ends
        self._paneling = None                  # "paneller"  for spline or Bezier 
        self._flap_setter = None                # "flap setter" 

        self._modification_dict = {}            # dict of modifications made to self 


    @override
    def __repr__(self) -> str:
        # overwritten to get a nice print string 
        return f"<{type(self).__name__}>"


    def _changed (self, aMod : str, 
                  val : float|str|None = None,
                  remove_empty = False,
                  moving = False):
        """ handle geometry changed 
            - save the modification made aMod with optional val
            - handle callbacks"""

        is_dat_based = self.isBasic or self.isSplined

        # sanity: rthere must be temp data
        if is_dat_based and (self._x is None or self._y is None):
            logger.warning (f"{self} _changed called but no temp xy data available")
            return

        if not moving:

            # when final, set temp _x _y to final 
            if is_dat_based:
                self._x_org     = np.asarray (self._x)
                self._y_org     = np.asarray (self._y)
                self._clear_xy()

            # store modification made - can be list or single mod 
            if remove_empty and (val is None or not (str(val))):
                self._modification_dict.pop (aMod, None)            # remove empty item
            else:                     
                self._modification_dict[aMod] = val

            # info Airfoil: x,y changed and available
            if callable(self._callback_changed):
                self._callback_changed ()
            else:
                logger.debug (f"{self} no change callback to airfoil defined")

        else:
            # moving - just reset dependent data - no callback, no final xy, no modification dict
            self._reset()

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


    @property
    def is_temp_xy (self) -> bool:
        """ 
        true if _x,_y is set which is typically when a modification is in progress (moved) 
        and not yet finalized
        """
        return self._x is not None and self._y is not None


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
    def paneling (self) -> Paneling:
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
    def flapped_chord_angle (self) -> float:
        """ returns angle of chord when self is flapped"""

        if not self.isProbablyFlapped: 
            return 0.0 
        else:
            angle = math.atan2 ((self.y[0] + self.y[-1])/ 2.0, (self.x[0] + self.x[-1])/ 2.0)
            return round (math.degrees(angle), 4)


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
    def te_gap_xBlend (self) -> float:
        """ x position from TE where te gap blending starts """
        if self._te_gap_xBlend is None:
            return self.TE_GAP_XBLEND
        else:
            return self._te_gap_xBlend
    
    @property
    def te_angle (self) -> float: 
        """ trailing edge angle in degrees"""

        upper = self.upper.te_angle
        lower = self.lower.te_angle
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
    def le_radius_xBlend (self) -> float:
        """ 
        x position from LE where le radius blending ends
        """
        if self._le_radius_xBlend is None: 
            return self.LE_RADIUS_XBLEND
        else: 
            return self._le_radius_xBlend


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
    def curvature (self) -> Curvature_Abstract: 
        " return the curvature object"
        if self._curvature is None: 
            from .geometry_spline import Curvature_of_Spline
            self._curvature = Curvature_of_Spline (Spline2D (self.x, self.y))  
        return self._curvature 


    @property 
    def lines_dict (self) -> dict[Line.Type, Line]:
        """ returns a dict with linetypes and their instances"""
        return {Line.Type.UPPER      : self.upper,
                Line.Type.LOWER      : self.lower,
                Line.Type.THICKNESS  : self.thickness,
                Line.Type.CAMBER     : self.camber}

    def get_line (self, linetype : Line.Type) -> Line:
        """ returns the line object for the given linetype"""
        lines = self.lines_dict
        return lines.get(linetype, None)
    

    def is_equal (self, other : 'Geometry') -> bool:
        """ Check if two Geometry objects are equal based on their x and y. """
        if not isinstance(other, Geometry):
            return False
        return (np.array_equal(self.x, other.x) and
                np.array_equal(self.y, other.y))

    def is_equal_xy (self, x : np.ndarray, y : np.ndarray) -> bool:
        """ Check if the Geometry object's x and y are equal to the provided arrays. """
        return (np.array_equal(self.x, x) and
                np.array_equal(self.y, y))


    def get_geo_parm(self, parm: geo_parm, x: float | None = None) -> float | tuple:
        """
        Unified accessor for geometry parameters.
        
        Args:
            parm: geo_parm enum specifying which parameter to retrieve
            x: optional x position for THICKNESS_AT queries
        
        Returns:
            - THICKNESS_AT: tuple (x, thickness_at_x) for requested x position
            - THICKNESS: tuple (max_thick_x, max_thick) at max thickness position
            - CAMBER: tuple (max_camb_x, max_camb) at max camber position
            - TE_ANGLE: scalar angle in degrees
            - TE_ANGLE_UPPER: scalar upper trailing edge angle
            - TE_ANGLE_LOWER: scalar lower trailing edge angle
            - TE_CURV_UPPER: scalar upper trailing edge curvature
            - TE_CURV_LOWER: scalar lower trailing edge curvature
            - LE_CURV: scalar leading edge curvature
        """
        if parm == geo_parm.THICKNESS_AT:
            if x is None:
                x = 0.5  # default x position
            return (x, self.thickness_at(x))
        
        elif parm == geo_parm.THICKNESS:
            return (self.max_thick_x, self.max_thick)
        
        elif parm == geo_parm.CAMBER:
            return (self.max_camb_x, self.max_camb)
        
        elif parm == geo_parm.TE_ANGLE:
            return self.te_angle
        
        elif parm == geo_parm.TE_ANGLE_UPPER:
            return self.upper.te_angle
        
        elif parm == geo_parm.TE_ANGLE_LOWER:
            return self.lower.te_angle
        
        elif parm == geo_parm.TE_CURV_UPPER:
            # Curvature at trailing edge (upper side)
            if hasattr(self.upper, 'curvature') and self.upper.curvature is not None:
                return self.upper.curvature.at_te
            return 0.0
        
        elif parm == geo_parm.TE_CURV_LOWER:
            # Curvature at trailing edge (lower side)
            if hasattr(self.lower, 'curvature') and self.lower.curvature is not None:
                return self.lower.curvature.at_te
            return 0.0
        
        elif parm == geo_parm.LE_CURV:
            return self.le_curvature
        
        else:
            raise ValueError(f"Unknown geometry parameter: {parm}")


    def thickness_at (self, x : float) -> float:
        """ returns the thickness at x by evaluating the thickness line"""
        return self.thickness.yFn (x)
    

    def set_te_gap (self, new_gap : float, xBlend : float = None, moving=False):
        """ set te gap - must be / will be normalized .

        Args: 
            new_gap:  in y-coordinates - typically 0.01 or so 
            xBlend:   the blending range from trailing edge 0..1
        """

        if xBlend is not None:
            self._te_gap_xBlend = clip (xBlend, 0.1, 1.0)


        try: 
            new_gap = clip (new_gap, 0.0, 0.1)

            # clear xy to reset upper and lower side objects
            self._clear_xy()

            if new_gap == self.te_gap:
                return

            # set gap in upper and lower side objects - the gap is split between upper and lower
            self.upper.set_te_gap (new_gap / 2.0, self.te_gap_xBlend)
            self.lower.set_te_gap (new_gap / 2.0, self.te_gap_xBlend)

            self._rebuild_from_upper_lower ()

            self._changed (Geometry.MOD_TE_GAP, round(self.te_gap * 100, 2), moving=moving)   

        except GeometryException:
            self._clear_xy()



    def set_le_radius (self, new_radius : float, xBlend : float = None, moving=False):
        """ 
        Set le radius of upper and lower which is the reciprocal of curvature at le
        
        Arguments: 
            new_radius:  new radius to apply 
            xBlend:      the blending range from leading edge 0.001..1
        """
        if xBlend is not None:
            self._le_radius_xBlend = clip (xBlend, 0.01, 1.0)
    

        try: 
            self._set_le_radius (new_radius, self.le_radius_xBlend) 

            self._rebuild_from_upper_lower ()
            self._changed (Geometry.MOD_LE_RADIUS, round(new_radius*100,2), moving=moving)
 
        except GeometryException:
            self._clear_xy()
    

    def set_le_curvature (self, new_curvature : float, xBlend = LE_RADIUS_XBLEND, moving=False):
        """ 
        Set le curvature of upper and lower which is the reciprocal of radius at le
        
        Arguments: 
            new_curvature:   new curvature to apply 
            xBlend:          the blending range from leading edge 0.001..1
        """

        if new_curvature: 
            self.set_le_radius (1.0 / new_curvature, xBlend, moving)


    def _set_le_radius (self, new_radius : float, xBlend : float = LE_RADIUS_XBLEND):
        """ 
        Set le radius which is the reciprocal of curvature at le 

        The procedere is based on xfoil allowing to define a blending range from le.
        Uses thickness, changes upper and lower side.
        
        Arguments: 
            new_radius:   in y-coordinates - typically 0.01 or so
            xBlend:   the blending range from leading edge 0.001..1 - Default 0.1"""


        new_radius = clip (new_radius, 0.001, 0.03)             # limit radius to reasonable values
        xBlend     = clip (xBlend, 0.01, 1.0)  

        # use original x,y (reset) 
        self._clear_xy()
        cur_radius = self.le_radius
        factor     = new_radius / cur_radius

        x_thickness = np.copy (self.thickness.x)
        y_thickness = np.copy (self.thickness.y)
        y_camber    = np.copy (self.camber.y)

        new_thickness = np.zeros (len(x_thickness))
        srfac         = (abs (factor)) ** 0.5

        for i in range(len(x_thickness)):
            # thickness factor tails off exponentially away from leading edge
            arg = min (x_thickness[i] / xBlend, 15.0)
            tfac = 1.0 - (1.0 - srfac) * np.exp(-arg)
            new_thickness [i] = y_thickness [i] * tfac

        # create new side objects from x,y to allow repeated setting of te gap

        self._upper  = self.side_class (x_thickness, y_camber + new_thickness / 2.0,
                                 linetype=Line.Type.UPPER)
        self._lower  = self.side_class (x_thickness, y_camber - new_thickness / 2.0,
                                 linetype=Line.Type.LOWER)

        self._rebuild_from_upper_lower ()

        # ensure new le radius is calculated with the new value
        self._reset()


    @property
    def flap_setter (self) -> Flap_Setter:
        """ controller to flap self"""

        if self._flap_setter is None and not self.isFlapped and not self.isCurve: 
            self._flap_setter = Flap_Setter (self.upper, self.lower)
        return self._flap_setter 
    
    
    def set_flap (self, 
                  flap_angle: float|None = None, 
                  flap_def: Flap_Definition | None = None,
                  moving=False) :
        """ 
        flap the geometry - an optional flap angle or flap definition can be submitted
        If successful, new geometry is set  
        """

        if self.flap_setter is None:
            logger.warning (f"{self} cannot set_flap (either already flapped or curved)")
            return
        
        upper_new, lower_new = self.flap_setter.set_flap (flap_angle=flap_angle, flap_def=flap_def)

        if upper_new and lower_new:
            self._upper = upper_new
            self._lower = lower_new

            self._rebuild_from_upper_lower()

            mod_str = f"{self.flap_setter.flap_angle:.1f}@{self.flap_setter.x_flap*100:.1f}"
            self._changed (Geometry.MOD_FLAP, mod_str, moving=moving)

 
    def set_max_thick (self, val : float): 
        """ change max thickness"""
        self.set_highpoint_of (Line.Type.THICKNESS,(None, val))
        

    def set_max_thick_x (self, val : float): 
        """ change max thickness x position"""
        self.set_highpoint_of (Line.Type.THICKNESS,(val,None))


    def set_max_camb (self, val : float): 
        """ change max camber"""
        if not self.isSymmetrical:
            self.set_highpoint_of (Line.Type.CAMBER,(None, val))


    def set_max_camb_x (self, val : float): 
        """ change max camber x position"""
        if not self.isSymmetrical:
            self.set_highpoint_of (Line.Type.CAMBER,(val, None))
           

    def set_highpoint_of (self, line_type: Line.Type, xy : tuple, moving=False):
        """ 
        change highpoint of a line - update airfoil 
        """

        try: 

            aLine = self.lines_dict[line_type]

            aLine.set_highpoint (xy)
            aLine.highpoint.label_percent ()

        except GeometryException: 
            logger.warning (f"{self} set highpoint failed for {line_type}")
            self._clear_xy ()
            return 

        if line_type == Line.Type.THICKNESS:
            self._rebuild_from_camb_thick ()
            amod = Geometry.MOD_MAX_THICK
            lab  = aLine.highpoint.label_percent ()
        elif line_type == Line.Type.CAMBER:
            self._rebuild_from_camb_thick ()
            amod = Geometry.MOD_MAX_CAMB
            lab  = aLine.highpoint.label_percent ()
        elif line_type == Line.Type.UPPER:
            self._rebuild_from_upper_lower ()
            amod = Geometry.MOD_MAX_UPPER
            lab  = ' '
        elif line_type == Line.Type.LOWER:
            self._rebuild_from_upper_lower ()
            amod = Geometry.MOD_MAX_LOWER
            lab  = ' '
        else:
            raise ValueError (f"{line_type} not supported for set_highpoint_of")

        # rebuild could have moved splined le
        self._normalize()

        self._changed (amod, lab, remove_empty=True, moving=moving)   

        return 


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
            self._push_xy ()                            # ensure a copy of x,y 
            self._normalize() 
            self._changed (Geometry.MOD_NORMALIZE)      # finalize (parent) airfoil 

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

        xn = self.x - xLe
        yn = self.y - yLe

        # Rotate the airfoil so chord is on x-axis 

        def rotate_xy(x_values, y_values, rotation_angle):
            cosa = np.cos(-rotation_angle)
            sina = np.sin(-rotation_angle)
            x_rot = x_values * cosa - y_values * sina
            y_rot = x_values * sina + y_values * cosa
            return x_rot, y_rot

        angle = np.arctan2 ((yn[0] + yn[-1])/ 2.0, (xn[0] + xn[-1])/ 2.0) 
        xn, yn = rotate_xy (xn, yn, angle)

        # sanity - with higher angles (flapped) there could be a new LE 

        ile = np.argmin (xn)

        if ile != self.iLe:

            # yes - LE changed - move and rotate once again 
            xLe, yLe = xn[ile], yn[ile]
            xn = xn - xLe
            yn = yn - yLe

            angle = np.arctan2 ((yn[0] + yn[-1])/ 2.0, (xn[0] + xn[-1])/ 2.0) 
            xn, yn = rotate_xy (xn, yn, angle)

        # Scale airfoil so that it has a length of 1 
        #  - there are mal formed airfoils with different TE on upper and lower
        #    scale both to 1.0  

        # sanity 
        if xn[0] == 0.0 or xn[-1] == 0.0: 
            raise GeometryException (f"Geometry corrupt during normalize")

        if xn[0] != 1.0 or xn[-1] != 1.0: 
            scale_upper = 1.0 / xn[0]
            scale_lower = 1.0 / xn[-1]

            mask = np.arange(len(xn)) <= ile
            xn[mask] = xn[mask] * scale_upper
            yn[mask] = yn[mask] * scale_upper
            xn[~mask] = xn[~mask] * scale_lower
            yn[~mask] = yn[~mask] * scale_lower

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
        """repanel self with a new panel distribution  """
        raise NotImplementedError


    def _repanel (self, **kwargs):
        """inner repanel self with a new panel distribution"""
        raise NotImplementedError


    def blend (self, geo1_in : 'Geometry', geo2_in : 'Geometry', blendBy : float, moving=False):
        """ blends  self out of two geometries depending on the blendBy factor"""

        if not (geo1_in and geo2_in):
            return
        # ensure geo1 is normalized - to this on a copy 
        
        if not geo1_in._isNormalized():
            geo1 = self.__class__(np.copy(geo1_in.x), np.copy(geo1_in.y))
            geo1.normalize()
        else: 
            geo1 = geo1_in

        # prepare geo2 Geometry to have linear or splined interpolation for blending

        if moving and not geo2_in.isBasic:
            # ensure geo2 is basic Geometry to have linear interpolation for blending
            geo2 = Geometry (np.copy(geo2_in.x), np.copy(geo2_in.y))
        elif not moving and  geo2_in.isBasic:
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

        self._changed (Geometry.MOD_BLEND, f"{blendBy*100:.0f}", moving=moving)   # finalize (parent) airfoil


    def assess_quality (self) -> list [str]:
        """ 
        Assess the quality of the geometry and curvature.
        Return a list of issues found
        """
        issues = []

        if self.le[0] != 0.0 or self.le[1] != 0.0 : 
            issues.append("LE not at (0,0)")
        elif self.isSplined and not self.isLe_closeTo_le_real:
            issues.append("Spline LE not at (0,0)")

        if not self.isFlapped:
            te_not_at_1 = ""
            te_not_sym  = ""
            if self.te[0] != 1.0 or self.te[2] != 1.0 : 
                te_not_at_1 = "TE x not at 1.0"
            if self.te[1] != -self.te[3]: 
                if te_not_at_1:
                    te_not_at_1 += " and y not symmetric"
                else:   
                    te_not_sym = "TE y not symmetric"
            if te_not_at_1:
                issues.append (te_not_at_1)
            if te_not_sym:
                issues.append (te_not_sym)

        if abs(self.te_gap) > 0.01:
            issues.append(f"TE gap too large: {self.te_gap:.4f}")

        if self.nPanels <100 or self.nPanels > 200:
            issues.append("Panel count should be 100..200")

        if self.panelAngle_le == 180.0: 
            issues.append("LE has two points")
        elif self.panelAngle_le > Geometry.LE_PANEL_ANGLE_TOO_BLUNT: 
            issues.append(f"LE panel angle {self.panelAngle_le:.1f}° too blunt")

        if self.panelAngle_le < Geometry.PANEL_ANGLE_TOO_SHARP: 
            issues.append(f"LE panel angle {self.panelAngle_le:.1f}° too sharp")
        elif self.panelAngle_min[0] < Geometry.PANEL_ANGLE_TOO_SHARP: 
            issues.append(f"Panel angle i={self.panelAngle_min[1]} < {Geometry.PANEL_ANGLE_TOO_SHARP}°")

        # if not self.curvature.max_is_at_le:
        #     issues.append("Max curvature not at LE")
       
        if (self.curvature.upper.needles() + self.curvature.lower.needles()):    
            issues.append("Curvature spikes; check .dat decimals")
    
        if self.curvature.upper.nreversals() > 1:
            issues.append(f"Upper curvature reversals: {self.curvature.upper.nreversals()}")

        if self.curvature.lower.nreversals() > 1:
            issues.append(f"Lower curvature reversals: {self.curvature.lower.nreversals()}")

        if self.curvature.max_te > 2.0:
            issues.append(f"TE max curvature {self.curvature.max_te:.1f} high (spoiler?)")

        return issues


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


    def _reset (self):
        """ reset all the sub objects like Lines or Splines"""

        # to be overriden in derived classes if needed

        self._upper      = None                 # upper side 
        self._lower      = None                 # lower side 
        self._thickness  = None                 # thickness distribution
        self._camber     = None                 # camber line
        self._curvature  = None                 # curvature 


if __name__ == "__main__":

    # ---- Test -----

    pass