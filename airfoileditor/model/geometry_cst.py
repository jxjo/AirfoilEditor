#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Geometry of a CST/Kulfan based airfoil.
"""

import numpy as np
import time
from typing import override

from ..base.common_utils  import clip
from ..base.math_util     import JPoint
from ..base.spline        import CST, bernstein_basis

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

    def __init__(
        self,
        linetype: Line.Type,
        weights,
        nPanels: int | None = None,
        le_weight: float = 0.0,
        te_gap: float = 0.0,
        n1: float = CST.DEFAULT_N1,
        n2: float = CST.DEFAULT_N2,
    ):
        super().__init__(linetype=linetype)

        self._curve = CST(
            weights=weights,
            le_weight=le_weight,
            te_gap=te_gap,
            n1=n1,
            n2=n2)

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
    SMOOTH_LAMBDA_DEFAULT = 0.00001

    WEIGHTS_UPPER_SAMPLE = np.array([0.17, 0.16, 0.14, 0.11, 0.09, 0.07, 0.05, 0.03], dtype=float)
    WEIGHTS_LOWER_SAMPLE = np.array([-0.17, -0.16, -0.14, -0.11, -0.09, -0.07, -0.05, -0.03], dtype=float)

    LE_MODE_DEFAULT = LE_Mode.FREE                  # default leading-edge mode for fit: no le_curvature constraint

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
        self.upper.cst.set_le_weight(le_weight)
        self.lower.cst.set_le_weight(le_weight)
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

        self.upper.cst.set_te_gap(0.5 * new_gap)
        self.lower.cst.set_te_gap(-0.5 * new_gap)

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


    @staticmethod
    def fit_from_xy (x_upper, y_upper, x_lower, y_lower,
                     n_weights: int = NCP_DEFAULT,
                     le_mode: LE_Mode = LE_Mode.C2,
                     le_curvature: float | None = None,
                     smooth_lambda: float = 0.0,
                     n1: float = CST.DEFAULT_N1,
                     n2: float = CST.DEFAULT_N2) -> tuple[np.ndarray, np.ndarray, float, float]:
        """
        Fit CST weights (upper, lower), a shared le_weight and a shared te_thickness
        to sampled upper/lower airfoil coordinates using linear least squares.

        The CST model y(x) = c(x) * sum_i(weights[i] * B_i(x)) + le_weight * x * (1-x)^p
        + te_gap * x is linear in weights, le_weight and te_gap - so upper and lower side
        data are stacked into a single combined linear system and solved with one
        np.linalg.lstsq call (fast, no iterative optimization).

        Args:
            x_upper, y_upper: sampled coordinates of the upper side (x in [0,1]).
            x_lower, y_lower: sampled coordinates of the lower side (x in [0,1]).
            n_weights: number of CST weights (Bernstein degree + 1) per side.
            le_mode: Leading-edge coupling mode:
                - "c2" (default): fit shared free a0 with upper/lower tied to
                  equal magnitude and opposite sign.
                - "fixed": pin |a0| from target le_curvature (must be > 0).
                - "free": fit upper/lower a0 independently (no coupling).
            le_curvature: target leading-edge curvature magnitude used only when
                le_mode="fixed".
            smooth_lambda: optional smoothing weight for second-difference regularization
                on both upper and lower weight vectors:
                smooth_lambda * sum((W[i+2] - 2*W[i+1] + W[i])**2).
                Use 0.0 (default) to disable smoothing.
            n1, n2: shared CST class-function exponents for both sides.

        Returns:
            tuple: (weights_upper, weights_lower, le_weight, te_thickness) - can be
            passed directly as Geometry_CST(weights_upper, weights_lower, le_weight, te_thickness).
        """
        if n_weights < 2:
            raise ValueError ("Geometry_CST.fit_from_xy: n_weights must be >= 2")
        if le_mode not in (LE_Mode.FREE, LE_Mode.C2, LE_Mode.FIXED):
            raise ValueError ("Geometry_CST.fit_from_xy: le_mode must be 'free', 'c2' or 'fixed'")
        if le_mode == LE_Mode.FIXED:
            if le_curvature is None or le_curvature <= 0.0:
                raise ValueError ("Geometry_CST.fit_from_xy: le_curvature must be > 0 when le_mode='fixed'")
        else:
            # Be tolerant if callers pass a stale LE curvature while mode is not fixed.
            le_curvature = None
        if smooth_lambda < 0.0:
            raise ValueError ("Geometry_CST.fit_from_xy: smooth_lambda must be >= 0")

        x_u = np.clip (np.asarray (x_upper, dtype=float), 0.0, 1.0)
        y_u = np.asarray (y_upper, dtype=float)
        x_l = np.clip (np.asarray (x_lower, dtype=float), 0.0, 1.0)
        y_l = np.asarray (y_lower, dtype=float)

        nu, nl = len (x_u), len (x_l)

        # Bernstein basis (n_weights, n_points) and class-function c(x) = x^n1 * (1-x)^n2

        Bu = bernstein_basis (n_weights - 1, x_u)
        Bl = bernstein_basis (n_weights - 1, x_l)
        cu = (x_u ** n1) * ((1.0 - x_u) ** n2)
        cl = (x_l ** n1) * ((1.0 - x_l) ** n2)

        # leading-edge-modification term x * (1-x)^p, shared exponent p depends on n_weights

        p = n_weights + 0.5
        le_term_u = x_u * ((1.0 - x_u) ** p)
        le_term_l = x_l * ((1.0 - x_l) ** p)

        # trailing edge gap term: +0.5*te_thickness*x (upper), -0.5*te_thickness*x (lower)

        te_term_u = 0.5 * x_u
        te_term_l = -0.5 * x_l

        rhs = np.concatenate ((y_u, y_l))

        independent_a0 = (le_mode == LE_Mode.FREE)
        free_a0        = (le_mode == LE_Mode.C2)

        columns = []

        if independent_a0:
            # weights_upper[0] and weights_lower[0] fully independent - no coupling at all,
            # handled below like any other free per-side weight (loop starts at index 0)
            pass
        elif free_a0:
            # a0 shared free unknown: +a0 on upper, -a0 on lower
            col_a0 = np.concatenate ((cu * Bu[0, :], -cl * Bl[0, :]))
            columns.append (col_a0)
        else:
            # a0 fixed from target le_curvature magnitude - move its contribution to rhs
            a0_fixed = np.sqrt (2.0 / le_curvature)
            fixed_contrib = np.concatenate ((a0_fixed * cu * Bu[0, :], -a0_fixed * cl * Bl[0, :]))
            rhs = rhs - fixed_contrib

        # free weights_upper - all weights if independent_a0, else only [1:] (a0 handled above)
        upper_start = 0 if independent_a0 else 1
        for i in range (upper_start, n_weights):
            columns.append (np.concatenate ((cu * Bu[i, :], np.zeros (nl))))

        # free weights_lower - all weights if independent_a0, else only [1:] (a0 handled above)
        lower_start = 0 if independent_a0 else 1
        for i in range (lower_start, n_weights):
            columns.append (np.concatenate ((np.zeros (nu), cl * Bl[i, :])))

        # shared le_weight and te_thickness - affect both sides
        columns.append (np.concatenate ((le_term_u, le_term_l)))
        columns.append (np.concatenate ((te_term_u, te_term_l)))

        def _regularized_lstsq (A_local: np.ndarray, rhs_local: np.ndarray) -> np.ndarray:
            """Solve least squares with optional second-difference regularization."""
            if smooth_lambda <= 0.0 or n_weights < 3:
                return np.linalg.lstsq (A_local, rhs_local, rcond=None)[0]

            n_cols = A_local.shape[1]
            reg_rows = []
            reg_rhs = []

            # build rows for Wi+2 - 2Wi+1 + Wi for upper and lower sides
            for side in (Line.Type.UPPER, Line.Type.LOWER):
                for i in range (n_weights - 2):
                    row = np.zeros (n_cols)
                    const = 0.0

                    for k, coeff in ((i, 1.0), (i + 1, -2.0), (i + 2, 1.0)):
                        if side == Line.Type.UPPER:
                            if independent_a0:
                                row[k] += coeff
                            elif free_a0:
                                if k == 0:
                                    row[0] += coeff
                                else:
                                    row[k] += coeff
                            else:
                                if k == 0:
                                    const += coeff * a0_fixed
                                else:
                                    row[k - 1] += coeff
                        else:
                            if independent_a0:
                                row[n_weights + k] += coeff
                            elif free_a0:
                                if k == 0:
                                    row[0] += -coeff            # lower W0 = -a0
                                else:
                                    row[n_weights + k - 1] += coeff
                            else:
                                if k == 0:
                                    const += coeff * (-a0_fixed)  # lower W0 = -a0_fixed
                                else:
                                    row[n_weights + k - 2] += coeff

                    reg_rows.append (np.sqrt (smooth_lambda) * row)
                    reg_rhs.append (np.sqrt (smooth_lambda) * (-const))

            if reg_rows:
                A_aug = np.vstack ((A_local, np.vstack (reg_rows)))
                rhs_aug = np.concatenate ((rhs_local, np.asarray (reg_rhs)))
                return np.linalg.lstsq (A_aug, rhs_aug, rcond=None)[0]

            return np.linalg.lstsq (A_local, rhs_local, rcond=None)[0]

        t0 = time.perf_counter()
        A = np.column_stack (columns)
        X = _regularized_lstsq (A, rhs)

        # a negative te_thickness would mean upper and lower side cross near the TE
        # (bowtie) - te_thickness must be >= 0, so if the unconstrained fit is
        # negative, refit with te_thickness fixed to 0 (drop its column)

        if X[-1] < 0.0:
            X = _regularized_lstsq (A[:, :-1], rhs)
            X = np.append (X, 0.0)

        print (f"fit_from_xy: {time.perf_counter() - t0:.6f} s")

        idx = 0

        weights_upper = np.empty (n_weights)
        weights_lower = np.empty (n_weights)

        if independent_a0:
            weights_upper[:] = X[idx: idx + n_weights]; idx += n_weights
            weights_lower[:] = X[idx: idx + n_weights]; idx += n_weights
        else:
            if free_a0:
                a0 = X[idx]; idx += 1
            else:
                a0 = a0_fixed

            weights_upper[0]  = a0
            weights_upper[1:] = X[idx: idx + n_weights - 1]; idx += n_weights - 1

            weights_lower[0]  = -a0
            weights_lower[1:] = X[idx: idx + n_weights - 1]; idx += n_weights - 1

        le_weight    = float (X[idx]); idx += 1
        te_thickness = float (X[idx])

        return weights_upper, weights_lower, le_weight, te_thickness


    @classmethod
    def geometry_as_CST (cls, geometry: Geometry, n_weights: int | None = None,
                         smooth_lambda: float = SMOOTH_LAMBDA_DEFAULT
                         ) -> tuple[np.ndarray, np.ndarray, float, float]:
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
            tuple: (weights_upper, weights_lower, le_weight, te_thickness) - can be
            passed directly as Geometry_CST(weights_upper, weights_lower, le_weight, te_thickness).
        """
        if n_weights is None:
            n_weights = cls.NCP_DEFAULT

        return cls.fit_from_xy (
            geometry.upper.x, geometry.upper.y, geometry.lower.x, geometry.lower.y,
            n_weights    = n_weights,
            le_mode = LE_Mode.FREE,
            smooth_lambda = smooth_lambda)


    @override
    def set_curve_parms_and_fit (self, 
                        target_side_upper : Line,
                        target_side_lower : Line,
                        ncp : int|None = None,
                        le_mode : LE_Mode = LE_Mode.FREE,
                        le_curvature : float|None = None,
                        smooth_lambda : float = SMOOTH_LAMBDA_DEFAULT):
        """ set new number of CST weights for both sides with fit to target_sides - update geometry"""

        if ncp is None:
            ncp = self.upper.ncp
        ncp = np.clip (ncp, self.NCP_BOUNDS[0], self.NCP_BOUNDS[1])  # limit number of control points to reasonable range

        weights_upper, weights_lower, le_weight, te_thickness = self.fit_from_xy (
                                                target_side_upper.x, target_side_upper.y,
                                                target_side_lower.x, target_side_lower.y,
                                                n_weights=ncp,
                                                le_mode=le_mode,
                                                le_curvature=le_curvature,
                                                smooth_lambda=smooth_lambda)

        self.upper.set_controlPoints (weights_upper)
        self.lower.set_controlPoints (weights_lower)
        self.set_le_weight (le_weight, moving=True)             # moving - avoid double changed
        self.set_te_gap (te_thickness, moving=True)

        self._reset()
        self._changed (self.MOD_CURVE + " ", f"#Weights={ncp}")
