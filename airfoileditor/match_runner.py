#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Matcher - Optimization threads for fitting airfoil geometry

    Thread-based optimization using Nelder-Mead algorithm to fit
    Bezier or B-Spline curves to target lines.
"""

import numpy as np
from typing                         import Type, override

from PyQt6.QtCore                   import QThread, pyqtSignal, QEventLoop

from .base.math_util                import nelder_mead, derivative1
from .base.spline                   import Bezier
from .base.widgets                  import style 
from .model.airfoil                 import Airfoil, Airfoil_Bezier, Airfoil_BSpline, clip
from .model.geometry                import Line
from .model.geometry_spline         import Geometry_Splined
from .model.geometry_curve          import BSpline, Side_Airfoil_Curve, Geometry_Curve
from .model.geometry_bezier         import Side_Airfoil_Bezier
from .model.geometry_bspline        import Side_Airfoil_BSpline
from .model.case                    import Match_Targets

import logging
logger = logging.getLogger(__name__)

#--------------------

class Matcher_Base (QThread):
    """Base worker thread for Bezier and B-spline airfoil matching."""

    sig_new_results     = pyqtSignal(int, int, object)  # ipass, nevals, Match_Result
    sig_pass_start      = pyqtSignal (int, int)         # ipass, new ncp
    sig_finished        = pyqtSignal(object)            # final Match_Result (is_optimized=True)

    STEP_SIZE = None                                    # initial step size for nelder mead - to be overridden in child classes

    def __init__(self, parent=None):
        super().__init__(parent)

        self._side : Side_Airfoil_Bezier | Side_Airfoil_BSpline = None
        self._targets : Match_Targets = None

        self._ncp    = None
        self._niter  = 0
        self._nevals = 0




    def __del__(self):  
        self.wait()


    @property
    def _curve (self) -> Bezier | BSpline:
        return self._side.curve


    def _y1_from_curvature (self, le_curvature: float, curve : Bezier| BSpline, cp_x2: float) -> float:
        """
        Compute the second control-point y value from the target LE curvature.
        """

        raise NotImplementedError ("must be implemented in child classes ")


    def _penalty_reversals (self, xb: np.ndarray, curv: np.ndarray,
                            region : tuple = (0.2, 1.0),
                            max_reversals: int = 0,
                            scale: float = 0.01) -> float:
        """ 
        Penalize curvature sign changes beyond the allowed reversal count.

        The penalty stays zero while the curvature-sign pattern remains within the
        allowed number of reversals and grows smoothly once additional violations
        appear.
        
        Logic:
        - max_reversals=0: No negative values allowed → penalty = sum of negative values
        - max_reversals=1: One sign change allowed → after going negative, penalty = any positive values
        - max_reversals=2: Two sign changes allowed → after 2nd change, penalty = further violations
        
        Args:
            xb: x coordinates.
            curv: Curvature values sampled at ``xb``.
            region: x range in which reversals are checked.
            max_reversals: Maximum allowed sign changes.
            scale: Scaling factor for the returned penalty.
            
        Returns:
            float: Reversal penalty contribution.
        """
        x_start, x_end = region
        body_mask = (xb >= x_start) & (xb <= x_end)
        curv_body = curv[body_mask]
        
        if len(curv_body) < 2:
            return 0.0
        
        # Track sign changes from left to right
        signs = np.sign(curv_body)
        signs[signs == 0] = 1  # treat zero as positive to avoid ambiguity
        
        # Find indices where sign changes occur
        sign_changes_idx = np.where(np.diff(signs) != 0)[0] + 1
        n_changes = len(sign_changes_idx)
        
        penalty_sum = 0.0
        
        # Unified logic for all max_reversals values
        if n_changes <= max_reversals:
            # Number of changes is within allowed limit - no penalty
            penalty_sum = 0.0
        else:
            # Too many changes - penalize violations from appropriate starting point
            if max_reversals == 0:
                # Lock to positive from the beginning (entire region)
                violation_start_idx = 0
                locked_sign = 1  # positive
            else:
                # Lock to sign after the (max_reversals)-th change
                violation_start_idx = sign_changes_idx[max_reversals]
                locked_sign = signs[violation_start_idx]
            
            after_limit = curv_body[violation_start_idx:]
            
            # Penalty for values with opposite sign to locked_sign
            if locked_sign > 0:
                # Locked to positive, penalize negative values
                violations = np.where(after_limit < 0, -after_limit, 0.0)
            else:
                # Locked to negative, penalize positive values
                violations = np.where(after_limit > 0, after_limit, 0.0)
            
            # Apply sqrt to each violation for aggressiveness on small values, then take mean for normalization
            penalty_sum = np.mean(np.sqrt(violations + 1e-10))
        
        # Apply scaling
        penalty = penalty_sum * scale
            
        return penalty


    def _penalty_te_curv (self, curv_te : float, 
                          max_curv_te: float,
                          max_reversals: int,
                          threshold: float = 0.01,
                          scale: float = 0.01) -> float:
        """ 
        Penalize trailing-edge curvature outside the allowed range.
        
        Args:
            curv_te: Trailing-edge curvature.
            max_curv_te: Maximum allowed trailing-edge curvature.
            threshold: Tolerance around the allowed range.
            scale: Scaling factor for the returned penalty.

        Returns:
            float: Trailing-edge curvature penalty contribution.
        """

        # sign of max_curv_te depends on reversals 
        max_curv_te = abs(max_curv_te) * (-1) ** max_reversals   # if max_reversals is odd, max_curv_te is negative; if even, positive (or zero)

        # Define the allowed range: between 0.0 and max_curv_te
        min_allowed = min(0.0, max_curv_te)
        max_allowed = max(0.0, max_curv_te)
        
        # Penalty if curv_te is outside the allowed range
        penalty = 0.0
        if curv_te < min_allowed - threshold:
            penalty = (abs(curv_te - min_allowed) - threshold) * scale
        elif curv_te > max_allowed + threshold:
            penalty = (abs(curv_te - max_allowed) - threshold) * scale

        # if penalty > 0.0:
        #     print (f"curv_te: {curv_te:.3f}  min_allowed: {min_allowed:.3f}  max_allowed: {max_allowed:.3f}  penalty: {penalty:.5f}")
        return penalty


    def _penalty_le_curv (self, curv_le: float, target_curv_le: float,
                          threshold: float = 0.01,
                          scale: float = 0.0001) -> float:
        """
        Penalize deviation from the target leading-edge curvature.

        Args:
            curv_le: Leading-edge curvature.
            target_curv_le: Target leading-edge curvature.
            threshold: Tolerance around the target curvature.
            scale: Scaling factor for the returned penalty.

        Returns:
            float: Leading-edge curvature penalty contribution.
        """

        delta = abs(abs(curv_le) - abs(target_curv_le))
        if delta <= threshold:
            return 0.0

        return (delta - threshold) * scale


    def _penalty_bumps (self, x : np.ndarray, curv : np.ndarray, 
                        max_reversals: int,
                        scale: float = 0.01) -> float:
        """
        Penalize reversals of derivative of curvature derivatives in a given x region.

        This acts as a smoothness term that suppresses bumps 
        
        Args:
            x: x coordinates.
            curv: Curvature values sampled at ``x``.
            max_reversals: Maximum allowed curvature reversals (sign changes).
            scale: Scaling factor for the returned penalty.
        """

        # Compute derivative of derivative
        curv_d   = derivative1 (x, curv)
        curv_d_d = derivative1 (x, curv_d)

        x_start, x_end = (0.2, 1.0)
        body_mask = (x >= x_start) & (x <= x_end)

        x_body   = x [body_mask]
        d_body   = curv_d   [body_mask]
        d_d_body = curv_d_d [body_mask]
        
        if len(x_body) < 2:
            return 0.0

        # curvature should montonically decrease in body region 
        #  - also becoming negative (reversal of ucvature)
        # -> avoid reversals of derivative of curvature 

        signs = np.sign(d_body)
        signs[signs == 0] = 1  # treat zero as positive to avoid ambiguity       
        sign_changes_idx = np.where(np.diff(signs) != 0)[0] + 1

        n_d = len(sign_changes_idx)

        # derivative of curvature decreases and may increase again
        # -> allow one reveresal of derivative of derivative  

        signs = np.sign(d_d_body)
        signs[signs == 0] = 1  # treat zero as positive to avoid ambiguity
        sign_changes_idx = np.where(np.diff(signs) != 0)[0] + 1

        n_d_d = len(sign_changes_idx)

        n_d_d = n_d_d - 1 - max_reversals       # allow one reversal + one per curve reversal
        n_d_d = max (n_d_d, 0)                  # don't allow negative reversal count
 
        # print (f" n_changes_d: {n_d}  n_changes_d_d: {n_d_d}")

        penalty = n_d * scale + n_d_d * scale

        return penalty

    #--------------------

    def _map_curve_to_variables (self): 
        """ 
        Map curve control points to the optimization variable vector.

        Returns:
            tuple[list, list]: Variable values and matching bound tuples.
        """

        sign   = -1 if self._side.isLower else 1         # lower side: y is inverted in solution space
        cp_x   = self._curve.cpoints_x
        cp_y   = self._curve.cpoints_y
        ncp    = self._curve.ncp
        vars   = []
        bounds = []

        for icp in range (2, ncp-1):                # skip LE (0), cp1 (1) and TE (ncp-1)
                                                    # cp1: x is 0.0 (vertical tangent), y is analytical from target LE curvature
                                                    # solution space is always positive (sign handles upper/lower)
            vars.append   (cp_x[icp])
            bounds.append ((0.005, 0.95))
            vars.append   (sign * cp_y[icp])
            bounds.append ((-0.1, 0.5))             # allow slight negative for reflex, limit upward

        return vars, bounds 


    def _map_variables_to_curve (self, vars: list): 
        """Map optimization variables back to curve control points."""

        sign   = -1 if self._side.isLower else 1         # lower side: y is inverted in solution space
        cp_x   = self._curve.cpoints_x
        cp_y   = self._curve.cpoints_y
        ncp    = self._curve.ncp
        ivar   = 0

        for icp in range (2, ncp-1):                # skip LE (0), cp1 (1) and TE (ncp-1)
            cp_x[icp] = vars[ivar];  ivar += 1
            cp_y[icp] = sign * vars[ivar];  ivar += 1

        # cp_y[1] is determined analytically from target LE curvature and current cp_x[2]

        cp_y[1] = sign * self._y1_from_curvature (self._targets.le_curvature, self._curve, cp_x[2])    # negative for lower side

        self._curve.set_cpoints (cp_x, cp_y)
        # Note: _u (panel distribution) is NOT reset here for performance - it's set once per optimization pass
        # and stays fixed. Arc-length recalculation on every objective evaluation would be too expensive.


    # ------ core run --------------


    def _objectiveFn (self, variables : list, show_info = False ) -> float:  
        """Evaluate the objective value for the current optimization variables."""
        
        targets = self._targets

        # rebuild BSpline 

        self._map_variables_to_curve (variables)

        # get needed values from current bspline

        x      = self._side.x                                       # single vectorized call
        c_line = self._side.curvature ()
        curv   = -c_line.y if self._side.isUpper else c_line.y      # curve for upper side has to be negated

        # -- rms of deviation - calc via linear interpolation of BSpline y values at target x 

        if targets.min_rms:
            self._side.reset_target_deviation ()                    # update target deviation line for current bspline shape
            obj_rms = self._side.target_deviation.rms()             # get current rms from target deviation line
        else:
            obj_rms = 0.0  

        # -- le curvature is analytically enforced via cp_y[1] - but for low ncp it could be wrong

        if targets.le_curvature is not None:
            penalty_le_curv = self._penalty_le_curv (curv[0], 
                                        targets.le_curvature, 
                                        threshold = 0.01, 
                                        scale     = 0.00001)
        else:
            penalty_le_curv = 0.0

        # -- te curvature limit

        if targets.max_te_curvature is not None:
            penalty_te_curv = self._penalty_te_curv (curv[-1], 
                                        targets.max_te_curvature, 
                                        targets.max_nreversals,
                                        threshold = 0.01, 
                                        scale     = 0.02) # 0.02
        else:
            penalty_te_curv = 0.0


        # -- penalty for curvature derivative to avoid bumps 

        if targets.bump_control:

            # penalty_bumps = self._penalty_bumps (x, curv, targets.max_nreversals, targets.max_te_curvature, scale=0.001) #0.05
            penalty_bumps = self._penalty_bumps (x, curv, targets.max_nreversals, scale=0.0001) 

        else:
            penalty_bumps = 0.0

        # -- penalty for curvature reversals

        penalty_reversals = self._penalty_reversals (x, curv, 
                                        region = (0.2, 1.0),
                                        max_reversals = targets.max_nreversals,
                                        scale = 0.1) # 0.1

        # objective function is sum of single objectives and penalties - should be as low as possible
        
        obj = obj_rms + penalty_le_curv + penalty_te_curv + penalty_bumps + penalty_reversals

        if self._nevals%100 == 0 or show_info:  
            logger.info (f"{self._nevals:4d}:  "
                    f"obj: {obj:.6f}   "
                    f"{('rms: '        + f'{obj_rms:.6f}   ') if obj_rms > 1e-9 else ''}"
                    f"{('le_curv: '    + f'{penalty_le_curv:.6f}   ') if penalty_le_curv > 1e-9 else ''}"
                    f"{('te_curv: '    + f'{penalty_te_curv:.6f}   ') if penalty_te_curv > 1e-9 else ''}"
                    f"{('bumps: '      + f'{penalty_bumps:.6f}   ')   if penalty_bumps > 1e-9 else ''}"
                    f"{('reversals: '  + f'{penalty_reversals:.6f}')  if penalty_reversals > 1e-9 else ''}")

        self._nevals += 1                       # counter of objective evaluations (for entertainment)

        # signal parent with new results 
        if self._nevals%100 == 0 or show_info:  
            result = Match_Result(self._side, self._targets, rms=obj_rms, objective=obj, curv=curv)
            self.sig_new_results.emit (self._ipass, self._nevals, result)
            self.msleep(2)                      # give parent some time to do updates

        return obj 

    

    def _run_single_pass (self, ncp = 6) -> float: 
        """Run one Nelder-Mead optimization pass for a fixed control-point count."""

        self._niter      = 0                        # number of iterations needed
        self._nevals     = 0                        # current number of objective function evals

        # sanity - ncp=3: fully determined analytically 

        if ncp == 3:
            self._map_variables_to_curve ([])      # just applies the analytical cp_y[1]
            return 0.0

        # -- reset Bezier to standard start position before each run  

        self._side.re_fit_curve(self._targets.side, self._targets.le_curvature, ncp=ncp)   # reset bezier to standard start position before each run - important for optimization behavior

        self.sig_pass_start.emit (self._ipass, ncp) # dialog can update UI, new ncp
        self.msleep(10)                             # give parent some time to do updates

        #-- map control point x,y to optimization variable 

        dv_start, bounds = self._map_curve_to_variables ()

        # ----- objective function

        f = lambda dv : self._objectiveFn (dv) 

        # -- initial step size 

        # step = 0.25                      # big enough to explore solution space 

        # -- calculate max_iter based on current number of variables

        max_iter = len(dv_start) * 300

        # ----- nelder mead find minimum --------

        res, niter = nelder_mead (f, dv_start,
                    step=self.STEP_SIZE, no_improve_thr=1e-7,             
                    no_improv_break_beginning=100, 
                    no_improv_break=20, 
                    max_iter=max_iter,         
                    bounds = bounds,
                    stop_callback=self.isInterruptionRequested)     # QThread method 

        dv = res[0]

        logger.info (f"Finished after {niter} iterations and {self._nevals} evaluations.") 
        objective = self._objectiveFn (dv, show_info=True)          # final evaluation with info printout

        #-- evaluate the new y values on Bezier for the target x-coordinate

        self._map_variables_to_curve (dv)

        self._niter      = niter
        self._nevals     = 0 

        return objective

    # ------ Public Methods --------------

    def set_match (self, side : Side_Airfoil_Curve, targets : Match_Targets):
        """Set the side to optimize together with its match targets."""

        if not isinstance (side, (Side_Airfoil_Bezier, Side_Airfoil_BSpline)):
            raise ValueError ("side must be an instance of Side_Airfoil_Bezier or Side_Airfoil_BSpline")
        if not isinstance (targets, Match_Targets):
            raise ValueError ("targets must be an instance of Match_Targets")

        self._targets = targets
        self._side    = side
        self._ncp     = side.curve.ncp


    def run (self):
        """ 
        Run the multi-pass optimization process for the configured side.
        """

        # Note: This is never called directly. It is called by Qt once the
        # thread environment has been set up and the thread is started with start().

        logger.info (f"---- Matcher starting for {self._side} side"
                            f"   target_curv_le: {self._targets.le_curvature:.0f}"
                            f"   max_curv_te: {self._targets.max_te_curvature:.1f}"
                            f"   max_reversals: {self._targets.max_nreversals}")

        self._ipass    = 0

        self._side.target_deviation.set_fast (True)             # needed for fast rms evaluation

        # set ncp for auto mode 
        if self._targets.ncp_auto:
            npc_list = range(self._side.NCP_BOUNDS[0], self._side.NCP_BOUNDS[1] + 1)  
        else:
            npc_list = [self._ncp]

        # Dictionary to store all results: {objective: control_points}
        results = {}

        for ncp in npc_list:

            self._ipass += 1
            logger.info (f"---- Pass {self._ipass}  ncp: {ncp} ")

            # run single nelder mead optimization 

            objective = self._run_single_pass (ncp=ncp)

            # Store result and decide if good enough to end 

            results[objective] = self._curve.cpoints.copy()

            if objective < 0.000030:                
                break
            elif self.isInterruptionRequested():
                break

        # Select best result (minimum objective)
        if results:
            best_objective = min(results.keys())
            best_cpoints = results[best_objective]
            self._side.set_controlPoints(best_cpoints)
            if self._targets.ncp_auto:
                logger.info (f"Selected best result: ncp={len(best_cpoints)}, objective={best_objective:.6f}")

        self._side.target_deviation.set_fast (False)            # needed for accurate rms evaluation

        result = Match_Result (self._side, self._targets, is_optimized=True)
        self.sig_finished.emit (result)


# --------------------


class Matcher_Bezier (Matcher_Base):
    """Matcher worker specialized for Bezier airfoil-side curves."""

    STEP_SIZE = 0.05                                    # initial step size for nelder mead


    @override
    def _y1_from_curvature (self, le_curvature: float, curve : Bezier| BSpline, cp_x2: float) -> float:
        """Compute the second control-point y value from the target LE curvature.

        Assume a leading-edge control-point layout of:
            P0 = (0, 0)
            P1 = (0, y1)
            P2 = (x2, y2)

        This gives a vertical start tangent and solves analytically for ``y1`` so
        that the start curvature matches ``le_curvature``.

        The formulas used are:

        Bézier:
            |kappa(0)| = (degree - 1) / degree * |x2| / y1^2

        Args:
            le_curvature: Desired curvature magnitude at the start point.
            curve: Curve instance used to determine the correct leading-edge formula.
            cp_x2: x coordinate of the third control point ``P2``.

        Returns:
            float: ``y1`` that produces the requested leading-edge curvature.
        """

        degree = curve.degree
        factor = (degree - 1) / degree

        y1 = np.sqrt(factor * abs(cp_x2) / abs(le_curvature))

        return y1



class Matcher_BSpline (Matcher_Base):
    """Matcher worker specialized for B-spline airfoil-side curves."""

    STEP_SIZE = 0.02                                     # initial step size for nelder mead

    @override
    def _y1_from_curvature (self, le_curvature: float, curve : Bezier| BSpline, cp_x2: float) -> float:
        """Compute the second control-point y value from the target LE curvature.

        Assume a leading-edge control-point layout of:
            P0 = (0, 0)
            P1 = (0, y1)
            P2 = (x2, y2)

        This gives a vertical start tangent and solves analytically for ``y1`` so
        that the start curvature matches ``le_curvature``.

        The formulas used are:

        B-spline (open-uniform/clamped, degree=4):
            ncp=5 (minimal): |kappa(0)| = (degree - 1) / degree * |x2| / y1^2
            ncp≥6: |kappa(0)| = (degree - 1) / (2 * degree) * |x2| / y1^2
            
        The factor changes because additional control points dilute cp[2]'s influence.

        Args:
            le_curvature: Desired curvature magnitude at the start point.
            curve: Curve instance used to determine the correct leading-edge formula.
            cp_x2: x coordinate of the third control point ``P2``.

        Returns:
            float: ``y1`` that produces the requested leading-edge curvature.
        """

        degree = curve.degree
        ncp = curve.ncp
        
        # Factor depends on number of control points for clamped B-splines
        # With minimal ncp (degree+1), cp[2] has maximum influence
        # With more control points, influence is diluted
        if ncp <= degree + 1:  # minimal case (ncp=5 for degree=4)
            factor = (degree - 1) / degree
        else:
            factor = (degree - 1) / (2 * degree)

        y1 = np.sqrt(factor * abs(cp_x2) / abs(le_curvature))

        return y1



# --------------------


class Match_Result:
    """Structured result for an airfoil matching operation."""

    def __init__(self, side: Side_Airfoil_Curve, targets: Match_Targets, 
                 *, rms: float | None = None, objective: float | None = None, 
                 curv: np.ndarray | None = None,
                 is_optimized: bool = False):
        """Initialize match result with calculated or provided metrics.
        
        Args:
            side: The airfoil side being matched.
            targets: Match targets for this optimization.
            rms: Pre-calculated RMS deviation (calculated if None).
            objective: Objective function value (optional).
            curv: Pre-calculated curvature array with correct sign (calculated if None).
            is_optimized: True if result comes from a real optimizer run, not the initial fit.
        """
        self._side = side
        self._targets = targets
        
        # Calculate and store all metrics
        self._rms = rms if rms is not None else side.target_deviation.rms()
        self._ncp = side.curve.ncp
        
        # Use provided curv (already has correct sign) or calculate from side
        if curv is not None:
            self._le_curvature = abs(curv[0])
            self._te_curvature = curv[-1]
            self._nreversals   = Line(x=side.x, y=curv).nreversals() 
        else:
            curv_line = side.curvature()
            self._le_curvature = abs(curv_line.y[0])
            self._te_curvature = curv_line.y[-1] if side.isLower else -curv_line.y[-1]
            self._nreversals   = curv_line.nreversals() 
        
        self._max_dy_tuple = side.target_deviation.max_dy()  # (position, value)
        
        # Optional fields
        self._objective    = objective
        self._is_optimized = is_optimized

    @property
    def name(self) -> str:
        """Name of the result, e.g. for labeling in the UI."""
        return f"{self._side.name}"
    
    @property
    def is_optimized(self) -> bool:
        """True if this result is from a real optimizer run, not the initial fit."""
        return self._is_optimized

    @property
    def side(self) -> Side_Airfoil_Curve:
        """The airfoil side being matched."""
        return self._side
    
    @property
    def targets(self) -> Match_Targets:
        """The match targets for this optimization."""
        return self._targets
    
    @property
    def rms(self) -> float:
        """RMS deviation from the target."""
        return round(self._rms, 6) if self._rms is not None else None
    
    @property
    def ncp(self) -> int:
        """Number of control points."""
        return self._ncp
    
    @property
    def le_curvature(self) -> float:
        """Leading-edge curvature."""
        return round(self._le_curvature, 1) if self._le_curvature is not None else None
    
    @property
    def te_curvature(self) -> float:
        """Trailing-edge curvature."""
        return round(self._te_curvature, 2) if self._te_curvature is not None else None
    
    @property
    def max_dy_position(self) -> float:
        """Position (x-coordinate) of maximum y deviation."""
        return round(self._max_dy_tuple[0], 2) if self._max_dy_tuple[0] is not None else None
    
    @property
    def max_dy(self) -> float:
        """Maximum y deviation from the target."""
        return round(self._max_dy_tuple[1], 6) if self._max_dy_tuple[1] is not None else None
    
    @property
    def objective(self) -> float | None:
        """Final objective function value."""
        return self._objective
       
    @property
    def nreversals(self) -> int | None:
        """Number of curvature reversals."""
        return self._nreversals
    
    @property
    def style_deviation(self) -> style:
        """UI style for this result's deviation."""
        if self._rms < 0.0001:                          # equals .01% deviation
            return style.GOOD
        elif self._rms < 0.0005:
            return style.NORMAL
        else:
            return style.WARNING
    
    @property
    def style_curv_le(self) -> style:
        """UI style for this result's LE curvature."""
        delta = abs(self._targets.le_curvature - self._le_curvature)
        
        if delta > 10: 
            return style.WARNING
        elif delta > 1.0: 
            return style.NORMAL
        else: 
            return style.GOOD
    
    @property
    def style_curv_te(self) -> style:
        """UI style for this result's TE curvature."""

        # sign of max_curv_te depends on reversals
        # if max_reversals is odd, max_curv_te is negative; if even, positive (or zero) 
        max_curv_te = abs(self._targets.max_te_curvature) * (-1) ** self._targets.max_nreversals  

        min_allowed = min(0.0, max_curv_te)
        max_allowed = max(0.0, max_curv_te)

        delta = 0.0
        if self._te_curvature < min_allowed:
            delta = abs(self._te_curvature - min_allowed) 
        elif self._te_curvature > max_allowed:
            delta = abs(self._te_curvature - max_allowed) 

        if delta > 2.0: 
            return style.WARNING
        elif delta > 0.1:
            return style.NORMAL
        else: 
            return style.GOOD
    
    @property
    def style_max_dy(self) -> style:
        """UI style for this result's maximum deviation."""
        max_dy = self._max_dy_tuple[1]
        
        if max_dy < 0.0002:                             # equals .02% deviation
            return style.GOOD
        elif max_dy < 0.001:
            return style.NORMAL
        else:
            return style.WARNING
    
    @property
    def style_nreversals(self) -> style:
        """UI style for this result's curvature reversals."""
        if self._nreversals is None:
            return style.NORMAL
        
        if self._nreversals <= self._targets.max_nreversals:
            return style.GOOD
        else:
            return style.WARNING

    def is_ncp_good(self) -> bool:
        """Determine if the number of control points is good based on targets."""
        if self._targets.max_nreversals:
            # reflexed or rearload - more complex shapes - allow higher ncp
            good_ncp = self._side.NCP_DEFAULT + 1
        else:
            # simple shapes - lower ncp is sufficient and more robust
            good_ncp = self._side.NCP_DEFAULT

        return self.ncp <= good_ncp and self.is_optimized

    @property
    def style_ncp(self) -> style:
        """UI style for this result's number of control points."""

        return style.GOOD if self.is_ncp_good() else style.NORMAL


    def is_good_enough(self) -> bool:
        """Return whether this result satisfies the quality targets."""
        return all(s == style.GOOD for s in (
            self.style_curv_le,
            self.style_curv_te,
            self.style_deviation,
        ))

    def is_perfect (self) -> bool:
        """Return whether this result is perfect (meets all targets with good style)."""
        return all(s == style.GOOD for s in (
            self.style_curv_le,
            self.style_curv_te,
            self.style_deviation,
            self.style_max_dy,
            self.style_nreversals
        ))

# --------------------


class Match_Airfoil:
    """Utility class for matching both sides of a single airfoil.
    
    Automatically creates match targets from the provided airfoil and
    runs matching in separate threads. Designed for batch processing.
    """
    
    def __init__(self, airfoil: Airfoil, airfoil_class: Type[Airfoil_Bezier | Airfoil_BSpline]):
        """Initialize matcher for an airfoil.
        
        Args:
            airfoil: Target airfoil to match.
            airfoil_class: Either Airfoil_Bezier or Airfoil_BSpline.
        """
        if airfoil_class not in [Airfoil_Bezier, Airfoil_BSpline]:
            raise ValueError("airfoil_class must be Airfoil_Bezier or Airfoil_BSpline")
        
        # Determine default ncp from Side class
        side_class = Side_Airfoil_Bezier if airfoil_class == Airfoil_Bezier else Side_Airfoil_BSpline
        ncp = side_class.NCP_DEFAULT
        
        # Create target airfoil for matching - repanel and normalize like in UI
        airfoil_target = airfoil.asCopy(geometry=Geometry_Splined)
        airfoil_target.repanel(nPanels=100, le_bunch=0.85, te_bunch=0.3, mod_string='_repan')
        
        if not airfoil_target.isNormalized:
            airfoil_target.normalize(mod_string='_repan_norm')
        
        self._airfoil_target = airfoil_target
        
        # Create targets automatically from target airfoil
        self._targets_upper = Match_Targets.from_airfoil(airfoil_target, Line.Type.UPPER, ncp)
        self._targets_lower = Match_Targets.from_airfoil(airfoil_target, Line.Type.LOWER, ncp)
        
        # Create the resulting airfoil
        self._airfoil = airfoil_class.on_airfoil(airfoil_target, ncp=ncp)
        
        # Get the geometry to access sides
        geo: Geometry_Curve = self._airfoil.geo
        
        # Create matchers
        matcher_class = Matcher_Bezier if airfoil_class == Airfoil_Bezier else Matcher_BSpline
        
        self._matcher_upper = matcher_class()
        self._matcher_upper.set_match(geo.upper, self._targets_upper)
        
        self._matcher_lower = matcher_class()
        self._matcher_lower.set_match(geo.lower, self._targets_lower)
        
        # Interruption flag
        self._interrupted = False
    
    @property
    def airfoil(self) -> Airfoil:
        """The matched airfoil."""
        return self._airfoil
    
    @property
    def airfoil_target(self) -> Airfoil:
        """The target airfoil (repaneled and normalized)."""
        return self._airfoil_target
    
    def get_result_upper(self) -> Match_Result | None:
        """Match result for upper side."""
        geo: Geometry_Curve = self._airfoil.geo
        return Match_Result(geo.upper, self._targets_upper)
        
    def get_result_lower(self) -> Match_Result | None:
        """Match result for lower side."""
        geo: Geometry_Curve = self._airfoil.geo
        return Match_Result(geo.lower, self._targets_lower)
    
    @property
    def targets_upper(self) -> Match_Targets:
        """Match targets for upper side."""
        return self._targets_upper
    
    @property
    def targets_lower(self) -> Match_Targets:
        """Match targets for lower side."""
        return self._targets_lower
    
    def interrupt(self):
        """Request interruption of the matching process."""
        self._interrupted = True
        self._matcher_upper.requestInterruption()
        self._matcher_lower.requestInterruption()
    
    def do_match(self) -> bool:
        """Execute matching for both sides and wait for completion.
        
        This method blocks until both matchers finish or are interrupted.
        
        Returns:
            bool: True if matching completed successfully, False if interrupted.
        """
        # Reset interruption flag
        self._interrupted = False
        
        # Create event loop for blocking
        loop = QEventLoop()
        
        # Track completion
        finished = {'upper': False, 'lower': False}
        
        def on_upper_finished():
            finished['upper'] = True
            if finished['lower']:
                loop.quit()
        
        def on_lower_finished():
            finished['lower'] = True
            if finished['upper']:
                loop.quit()
        
        # Connect finished signals
        self._matcher_upper.finished.connect(on_upper_finished)
        self._matcher_lower.finished.connect(on_lower_finished)
        
        # Start both threads
        logger.info(f"Starting match for {self._airfoil.name}")
        self._matcher_upper.start()
        self._matcher_lower.start()
        
        # Block until both finish
        loop.exec()
        
        # Wait for threads to fully terminate
        self._matcher_upper.wait()
        self._matcher_lower.wait()
        
        success = not self._interrupted
        if success:
            logger.info(f"Match completed for {self._airfoil.name}")
        else:
            logger.info(f"Match interrupted for {self._airfoil.name}")
        
        return success
    
    def do_match_sequential(self) -> bool:
        """Execute matching sequentially without threading.
        
        Simpler alternative to do_match() that runs matchers one after another
        in the current thread. Doesn't require QEventLoop but takes longer.
        
        Returns:
            bool: True if matching completed successfully, False if interrupted.
        """
        # Reset interruption flag
        self._interrupted = False
        
        logger.info(f"Starting sequential match for {self._airfoil.name}")
        
        # Run upper side
        self._matcher_upper.run()
        
        # Check for interruption
        if self._matcher_upper.isInterruptionRequested():
            self._interrupted = True
            logger.info(f"Match interrupted for {self._airfoil.name}")
            return False
        
        # Run lower side
        self._matcher_lower.run()
        
        # Check for interruption
        if self._matcher_lower.isInterruptionRequested():
            self._interrupted = True
            logger.info(f"Match interrupted for {self._airfoil.name}")
            return False
        
        logger.info(f"Sequential match completed for {self._airfoil.name}")
        return True
        