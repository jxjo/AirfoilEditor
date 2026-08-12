#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Geometry of a CST/Kulfan based airfoil.
"""

import numpy as np
from typing import override

from ..base.common_utils  import clip
from ..base.cst           import CST, fit_cst_from_xy
from ..base.math_util     import JPoint

from .geometry            import Geometry, Line, Panelling
from .geometry_curve      import Geometry_Curve, Side_Airfoil_Curve, LE_Mode

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)


class Panelling_CST(Panelling):
    """Panelling helper for CST based geometry."""

    @classmethod
    def to_dict(cls, d: dict):
        if cls._nPanels != cls.N_PANELS_DEFAULT:
            d["cst_nPanels"] = cls._nPanels
        else:
            d.pop("cst_nPanels", None)

        if cls._le_bunch != cls.LE_BUNCH_DEFAULT:
            d["cst_le_bunch"] = cls._le_bunch
        else:
            d.pop("cst_le_bunch", None)

        if cls._te_bunch != cls.TE_BUNCH_DEFAULT:
            d["cst_te_bunch"] = cls._te_bunch
        else:
            d.pop("cst_te_bunch", None)


    @classmethod
    def from_dict(cls, d: dict):
        if "cst_nPanels" in d:
            cls._nPanels = d["cst_nPanels"]
        if "cst_le_bunch" in d:
            cls._le_bunch = d["cst_le_bunch"]
        if "cst_te_bunch" in d:
            cls._te_bunch = d["cst_te_bunch"]


class Side_Airfoil_CST(Side_Airfoil_Curve):
    """Single CST side of an airfoil with chordwise x in [0, 1]."""

    isCST = True

    NCP_DEFAULT          = 8          # hack: copy from Geometry_CST.NCP_DEFAULT - used for Match_Result

    def __init__(self,
                    linetype: Line.Type,
                    weights,
                    nPanels: int | None = None,
                    le_weight: float = 0.0,
                    te_gap: float = 0.0,
                    n1: float = CST.DEFAULT_N1,
                    n2: float = CST.DEFAULT_N2):
        
        super().__init__(linetype=linetype)

        self._curve = CST(weights=weights,le_weight=le_weight, te_gap=te_gap, n1=n1, n2=n2)

        self._nPanels = nPanels if nPanels is not None else Panelling.nPanels_for(linetype)
        self._le_bunch = Panelling.LE_BUNCH_DEFAULT
        self._te_bunch = Panelling.TE_BUNCH_DEFAULT


    @override
    def set_panelling(self, nPanels: int, le_bunch: float = None, te_bunch: float = None):
        """ set panel distribution parameters for this side - CST needs at least 10 panels """
        super().set_panelling(int(max(10, nPanels)), le_bunch, te_bunch)


    def _curve_state_key(self) -> tuple:
        """ hashable key of current CST weights/params + panelling params, for u cache invalidation """
        cst = self._curve
        return hash((
            tuple(float(w) for w in cst.weights),
            float(cst.le_weight),
            float(cst.te_gap),
            float(cst.n1),
            float(cst.n2),
            self._nPanels,
            self._le_bunch,
            self._te_bunch
        ))


    @property
    def cst(self) -> CST:
        """ returns the CST curve object of self"""
        return self._curve


    @override
    @property
    def controlPoints (self) -> list[tuple]: 
        """ cst weights (control points) as xy"""
        return self.curve.cpoints
    
    def set_controlPoints(self, weights : list | np.ndarray):
        """ set CST weights (control points) - compatibility with other side classes"""

        # create dummy cpx array for compatibility with set_cpoints
        self.curve.set_cpoints (np.zeros_like(weights), weights)
        self.reset_target_deviation ()


    def set_le_weight(self, le_weight: float):
        """ set leading edge weight and recalculate deviation """
        self.cst.set_le_weight (le_weight)
        self.reset_target_deviation ()


    def set_te_gap(self, te_gap: float):
        """ 
        set trailing edge gap to this side. Sign of the gap is applied based on the side type (upper/lower). 
        and recalculate deviation

        Args:
            te_gap: ! half of the airfoil trailing-edge gap !
        """                     
        # sign sanity
        if self.type == Line.Type.UPPER:
            signed_gap = abs(te_gap) 
        elif self.type == Line.Type.LOWER:
            signed_gap = -abs(te_gap)

        self.cst.set_te_gap (signed_gap)
        self.reset_target_deviation ()


    @property
    def controlPoints_as_jpoints (self) -> list[JPoint]: 
        """ CST control points (weights, LE weight, TE gap) as JPoints"""
        jpoints = []

        # add the weights as control points
        for i in range(self.cst.ncp):

            x, y = self.cst.weights_x[i], self.cst.weights[i]
            jpoint = JPoint(x, y, name=f"W{i}")

            jpoint.set_x_limits ((x,x))

            jpoints.append(jpoint)

        return jpoints



class Geometry_CST(Geometry_Curve):
    """Geometry based on CST/Kulfan upper and lower weight sets."""

    isBasic = False
    isCST = True
    isCurve = True
    description = "based on CST (Kulfan) surfaces"

    side_class = Side_Airfoil_CST
    line_class = Line

    CURVE_NAME = "CST"
    MOD_CURVE = CURVE_NAME

    NCP_DEFAULT          = 8                        # number of weights (control points) per side
    NCP_BOUNDS           = (4, 12)                  # min/max number of weights per side
    LE_WEIGHT_DEFAULT    = 0.0
    TE_THICKNESS_DEFAULT = 0.0
    SMOOTH_LAMBDA_MIN    = 1e-7
    SMOOTH_LAMBDA_MAX    = 1e-4
    SMOOTH_LAMBDA_DEFAULT = 6.3096e-06              # results in 0.6 tranformed to 0..1

    WEIGHTS_UPPER_SAMPLE = np.array([0.17, 0.16, 0.14, 0.11, 0.09, 0.07, 0.05, 0.03], dtype=float)
    WEIGHTS_LOWER_SAMPLE = np.array([-0.17, -0.16, -0.14, -0.11, -0.09, -0.07, -0.05, -0.03], dtype=float)

    LE_MODE_DEFAULT     = LE_Mode.FREE              # default leading-edge mode for fit: no le_curvature constraint

    # override as CST thickness is always 100% blending distance
    TE_GAP_XBLEND       = 1.0                       # default x position from TE where te gap blending starts


    def __init__ (self, 
                  weights_upper : list | np.ndarray, 
                  weights_lower : list | np.ndarray, 
                  le_weight : float = 0.0, 
                  te_thickness : float = 0.0,
                  **kwargs):
        """new Geometry based on two CST curves for upper and lower side """

        super().__init__( **kwargs)   

        te_gap = 0.5 * te_thickness
        self._upper = Side_Airfoil_CST(Line.Type.UPPER, weights_upper, le_weight=le_weight, te_gap= te_gap)
        self._lower = Side_Airfoil_CST(Line.Type.LOWER, weights_lower, le_weight=le_weight, te_gap=-te_gap)


    @override
    @property
    def isSymmetrical(self) -> bool:
        """ true if lower = - upper (weights negated, no LE/TE asymmetry)"""
        upper_w = self.upper.cst.weights
        lower_w = self.lower.cst.weights

        if len(upper_w) != len(lower_w):
            return False
        if not np.allclose(upper_w, -lower_w):
            return False
        if self.upper.cst.le_weight != 0.0 or self.lower.cst.le_weight != 0.0:
            return False
        if abs(self.upper.cst.te_gap + self.lower.cst.te_gap) > 1e-12:
            return False
        return True

    @override
    def _isNormalized (self):
        """ true if LE is at 0,0 and TE is symmetrical at x=1"""
        # CST is always normalized
        return True

    @override
    @property
    def upper(self) -> Side_Airfoil_CST:
        if self._upper is None:
            self._upper = Side_Airfoil_CST(Line.Type.UPPER, 
                                           np.copy(self.WEIGHTS_UPPER_SAMPLE), 
                                           le_weight=self.LE_WEIGHT_DEFAULT, 
                                           te_gap=0.5 * self.TE_THICKNESS_DEFAULT)
        return self._upper


    @override
    @property
    def lower(self) -> Side_Airfoil_CST:
        if self._lower is None:
            self._lower = Side_Airfoil_CST(Line.Type.LOWER, 
                                           np.copy(self.WEIGHTS_LOWER_SAMPLE), 
                                           le_weight=self.LE_WEIGHT_DEFAULT, 
                                           te_gap=0.5 * self.TE_THICKNESS_DEFAULT)
        return self._lower


    def set_newSide_for(self, line_type: Line.Type, 
                        weights : list | np.ndarray, 
                        le_weight: float|None=None, 
                        te_thickness: float|None=None):
        """Create and set a new CST side for upper or lower."""

        if weights is None or len(weights) == 0:
            return
        if le_weight is None:
            le_weight = self.LE_WEIGHT_DEFAULT
        if te_thickness is None:
            te_thickness = self.TE_THICKNESS_DEFAULT

        te_gap  = 0.5 * te_thickness

        new_side = Side_Airfoil_CST(line_type, weights, le_weight=le_weight, te_gap=te_gap)

        if line_type == Line.Type.UPPER:
            self.set_upper(new_side)
        elif line_type == Line.Type.LOWER:
            self.set_lower(new_side)


    @override
    @property
    def panelling(self) -> Panelling_CST:
        if self._panelling is None:
            self._panelling = Panelling_CST()
        return self._panelling


    @property
    def description_long(self) -> str:
        return (
            f"{self.__class__.description}  "
            f"(#W {len(self.upper.cst.weights)}, {len(self.lower.cst.weights)})")


    @property
    def le_weight(self) -> float:
        """ leading edge weight (same for upper and lower)"""
        return self.upper.cst.le_weight

    def set_le_weight(self, le_weight: float, moving=False):
        le_weight = round(le_weight,3)
        self.upper.set_le_weight(le_weight)
        self.lower.set_le_weight(le_weight)
        if not moving:
          self._reset()
          self._changed(self.MOD_CURVE + " LE weight", le_weight)


    @property
    def te_gap(self) -> float:
        """ trailing edge gap (upper + lower)"""
        return self.upper.cst.te_gap - self.lower.cst.te_gap

    @override
    def set_te_gap(self, new_gap: float, xBlend=None, moving=False):
        new_gap = clip(new_gap, 0.0, 0.1)

        if abs(new_gap - self.te_gap) < 1e-10:
            return

        self.upper.set_te_gap(0.5 * new_gap)
        self.lower.set_te_gap(0.5 * new_gap)

        if not moving:
            self._reset()
            self._changed(Geometry.MOD_TE_GAP, round(self.te_gap * 100, 2))


    @override
    def repanel(self, nPanels: int = None, just_finalize=False):
        if not just_finalize:
            self._repanel(nPanels)
        else:
            self._panelling.save()

        self._reset_lines()
        self._changed(Geometry.MOD_REPANEL)


    @override
    def _repanel(self, nPanels: int = None, **kwargs):
        nPanels = nPanels if nPanels is not None else self.panelling.nPanels

        nPanels_upper = Panelling.nPanels_for(Line.Type.UPPER, nPanels)
        nPanels_lower = Panelling.nPanels_for(Line.Type.LOWER, nPanels)

        self.upper.set_panelling(nPanels_upper, self.panelling.le_bunch, self.panelling.te_bunch)
        self.lower.set_panelling(nPanels_lower, self.panelling.le_bunch, self.panelling.te_bunch)

        return True


    def as_dict(self) -> dict:
        return {
            "weights_upper": self.upper.cst.weights.tolist(),
            "weights_lower": self.lower.cst.weights.tolist(),
            "leading_edge_weight": self.upper.cst.le_weight,
            "te_thickness": self.te_gap,
        }


    @classmethod
    def smoothness_to_lambda(cls, smoothness: float) -> float:
        """Map user smoothness in [0,1] to solver regularization lambda."""
        s = clip(float(smoothness), 0.0, 1.0)
        if s <= 0.0:
            return 0.0
        return cls.SMOOTH_LAMBDA_MIN * ((cls.SMOOTH_LAMBDA_MAX / cls.SMOOTH_LAMBDA_MIN) ** s)


    @classmethod
    def lambda_to_smoothness(cls, smooth_lambda: float) -> float:
        """Map solver regularization lambda back to user smoothness in [0,1]."""
        if smooth_lambda <= 0.0:
            return 0.0
        lam = clip(float(smooth_lambda), cls.SMOOTH_LAMBDA_MIN, cls.SMOOTH_LAMBDA_MAX)
        return (np.log10(lam) - np.log10(cls.SMOOTH_LAMBDA_MIN)) / (
            np.log10(cls.SMOOTH_LAMBDA_MAX) - np.log10(cls.SMOOTH_LAMBDA_MIN)
        )


    @classmethod
    def geometry_as_CST (cls, geo: Geometry, n_weights: int | None = None,
                         smooth_lambda: float = SMOOTH_LAMBDA_DEFAULT
                         ) -> tuple[np.ndarray, np.ndarray, float, float, float]:
        """
        Fit CST parameters (fast linear least squares, see fit_from_xy) approximating
        an existing geometry's upper/lower x,y coordinates.

        The leading-edge weight (a0) is fitted fully independently for upper and lower
        (no coupling at all - see fit_from_xy's le_curvature=None). Tying a0 to a shared
        value (equal magnitude / opposite sign, or pinned to the geometry's own
        finite-difference leading edge curvature) was tried, but real airfoils often have
        a genuine asymmetry or mid-chord curvature inflection on one side (e.g. reflex
        airfoils) that forces the higher-order weights of the *other*, well-behaved side
        into large oscillating compensations to satisfy the shared constraint - fitting
        both sides fully independently avoids that cross-talk.

        Args:
            geometry: the Geometry (or subclass) instance to approximate.
            n_weights: number of CST weights (Bernstein degree + 1) per side -
                defaults to cls.DEFAULT_N_WEIGHTS.
            smooth_lambda: optional smoothing weight passed to fit_from_xy.

        Returns:
            tuple: (weights_upper, weights_lower, le_weight, te_thickness, derotation_angle) 
        """
        if n_weights is None:
            n_weights = cls.NCP_DEFAULT

        # ensure geometry is normalized

        if not geo._isNormalized():

            derotation_angle = -geo.flapped_chord_angle
            if abs(derotation_angle) > 0.0:
                logger.info(f"Geometry_CST: geometry is flapped, derotating by {derotation_angle:.2f}° to normalize")

            geo_norm = Geometry (geo.x, geo.y)          # temporary normalized copy of geometry
            geo_norm._push_xy()                         # speed hack
            geo_norm._normalize() 
            geo_norm._set_xy (geo_norm._x, geo_norm._y)
        else:
            geo_norm = geo
            derotation_angle = 0.0


        return (*fit_cst_from_xy (
            geo_norm.upper.x, geo_norm.upper.y, geo_norm.lower.x, geo_norm.lower.y,
            n_weights    = n_weights,
            le_mode = 'free',               # fully independent a0 for upper and lower
            smooth_lambda = smooth_lambda), derotation_angle)


    @override
    def set_curve_parms_and_fit (self, 
                        target_side_upper : Line,
                        target_side_lower : Line,
                        ncp : int|None = None,
                        le_mode : LE_Mode = LE_Mode.FREE,
                        le_curvature : float|None = None,
                        smooth_lambda : float = SMOOTH_LAMBDA_DEFAULT,
                        moving=False):
        """ set new number of CST weights for both sides with fit to target_sides - update geometry"""

        if ncp is None:
            ncp = self.upper.ncp
        ncp = np.clip (ncp, self.NCP_BOUNDS[0], self.NCP_BOUNDS[1])  # limit number of control points to reasonable range

        if le_mode == LE_Mode.FIXED:
            le_mode_str = "fixed"
        elif le_mode == LE_Mode.C2:
            le_mode_str = "c2"
        else:
            le_mode_str = "free"

        weights_upper, weights_lower, le_weight, te_thickness = fit_cst_from_xy (
                                                target_side_upper.x, target_side_upper.y,
                                                target_side_lower.x, target_side_lower.y,
                                                n_weights=ncp,
                                                le_mode=le_mode_str,
                                                le_curvature=le_curvature,
                                                smooth_lambda=smooth_lambda)

        self.upper.set_controlPoints (weights_upper)
        self.lower.set_controlPoints (weights_lower)
        self.set_le_weight (le_weight, moving=True)             # moving - avoid double changed
        self.set_te_gap (te_thickness, moving=True)

        self._reset()

        if not moving:
            self._changed (self.MOD_CURVE + " ", f"#Weights={ncp}")
