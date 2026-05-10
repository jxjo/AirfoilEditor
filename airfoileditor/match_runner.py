#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Matcher - Optimization threads for fitting airfoil geometry

    Thread-based optimization using Nelder-Mead algorithm to fit
    Bezier or B-Spline curves to target lines.
"""

import numpy as np
from timeit                         import default_timer as timer
from typing                         import Type, override

from PyQt6.QtCore                   import QThread, pyqtSignal, QEventLoop

from .base.math_util                import nelder_mead, derivative1, interpolate, differential_evolution
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

class Matcher (QThread):
    """Base worker thread for Bezier and B-spline airfoil matching."""

    sig_new_results     = pyqtSignal(int, int, object)  # ipass, nevals, Match_Result
    sig_pass_start      = pyqtSignal (int, int, bool)   # ipass, new ncp
    sig_finished        = pyqtSignal(object)            # final Match_Result


    def __init__(self, parent=None):
        super().__init__(parent)

        self._side : Side_Airfoil_Bezier | Side_Airfoil_BSpline = None
        self._targets : Match_Targets = None

        self._ncp    = None
        self._nevals = 0

        # dev 
        self._penalty_bumps_min = 999999
        self._penalty_bumps_max = -999999

    def __del__(self):  
        self.wait()


    @property
    def _curve (self) -> Bezier | BSpline:
        return self._side.curve


    def _step_size (self, ncp: int) -> float:
        """Calculate step size for Nelder-Mead based on number of control points."""

        # For curves with less control points, the solution may be farther from the initial guess, 
        # so we can use a larger step size. For more control points, we can use a smaller step size to fine-tune the solution.

        if self._side.isBezier:

            step = interpolate ( 5, 8, 0.3, 0.1, ncp)  # linear interpolation  

        elif self._side.isBSpline:

            step = interpolate ( 5, 10, 0.2, 0.4, ncp)  # linear interpolation between (5, 0.2) and (10, 0.4)

        else:
            step = 0.1
        return step


    @staticmethod
    def _penalty_reversals (xb: np.ndarray, curv: np.ndarray,
                            region : tuple | None = None,
                            max_reversals: int = 0,
                            threshold: float = Line.CURV_THRESHOLD,
                            smooth: bool = False,
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
            threshold: Tolerance around zero to avoid noise-driven sign changes.
            scale: Scaling factor for the returned penalty.
            
        Returns:
            float: Reversal penalty contribution.
        """
        if isinstance(region, tuple):
            x_start, x_end = region
            body_mask = (xb >= x_start) & (xb <= x_end)
            curv_body = curv[body_mask]
        else:
            curv_body = curv

        # take only values above threshold to avoid false positives from small oscillations around zero
        if threshold > 0.0:
            mask      = np.abs(curv_body) > threshold
            curv_body = curv_body [mask]
        
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

        if n_changes > max_reversals:
            # Too many changes - penalize least significant segments
            # Split curvature into segments based on sign changes
            segment_bounds = [0] + list(sign_changes_idx) + [len(curv_body)]
            
            # Calculate the "area" (sum of absolute values) for each segment
            segment_maxs = []
            for i in range(len(segment_bounds) - 1):

                start_idx = segment_bounds[i]
                end_idx   = segment_bounds[i + 1]
                segment = curv_body[start_idx:end_idx]

                max_val = np.max(np.abs(segment))
                segment_maxs.append(max_val)
            
            # Sort segments by area (largest to smallest)
            segment_maxs.sort(reverse=True)
            # We want to keep (max_reversals + 1) most significant segments
            # The smaller rest should be penalized
            n_segments_to_keep = max_reversals + 1
            segments_to_penalize = segment_maxs[n_segments_to_keep:]
            
            # Sum the max values of the segments we're penalizing
            penalty_sum = sum(segments_to_penalize)
        
        # Apply scaling
        if penalty_sum > 1.0:
            penalty_sum = penalty_sum ** 0.3                # damp very high penalties to avoid instability
        penalty = penalty_sum * scale                     

        return penalty


    @staticmethod
    def _penalty_te_curv (curv_te : float, 
                          max_curv_te: float,
                          max_reversals: int,
                          threshold: float = 0.05,
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


    @staticmethod
    def _penalty_le_curv (curv_le: float, target_curv_le: float,
                          threshold: float = Line.CURV_THRESHOLD,
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


    @staticmethod
    def _penalty_le_curv_monoton (curv : np.ndarray, scale: float = 0.01) -> float:
        """
        Penalize non-monotonic curvature in the leading-edge region.

        This ensures that highest curvature is exactly at the leading edge.

        Args:
            curv: Curvature values sampled at the leading-edge region.
            scale: Scaling factor for the returned penalty.
        """

        # sanity 
        if len(curv) < 10:
            return 0.0

        # sum up all positive differences (where curvature increases) and scale the penalty

        curv_diff = np.diff(np.abs(curv[:10]))
        pen_le_curv_monoton = (np.sum(curv_diff[curv_diff > 0]) / np.abs(curv[0])) * scale

        return pen_le_curv_monoton


    @staticmethod
    def _penalty_bumpiness (x : np.ndarray, curv : np.ndarray, 
                            max_reversals: int = 0,
                            scale: float = 0.01) -> float:
        """
        Penalize bumbiness by integrating the curvature derivatives in the body region.

        This acts as a smoothness term that suppresses bumps 
        
        Args:
            x: x coordinates.
            curv: Curvature values sampled at ``x``.
            max_reversals: Maximum allowed curvature reversals (sign changes).
            scale: Scaling factor for the returned penalty.
        """

        # define a weighting window that focuses on the body region and smoothly reduces the penalty 
        # towards the leading and trailing edges as high values of curvature derivative 
        # would interfere with smoothing 
        x0      = 0.05                
        width0  = 0.45 # 0.3
        x1      = 1.0   
        width1  = 0.3 # 0.15 if max_reversals == 0 else 0.3     # limit - as high values at te could confuse damping
        w       = np.zeros_like(x)

        # Middle region
        mid_mask = (x >= x0 + width0) & (x <= x1 - width1)
        w[mid_mask] = 1.0

        # Left smooth ramp
        left_mask = (x >= x0) & (x < x0 + width0)
        t = (x[left_mask] - x0) / width0
        w[left_mask] = 0.5 * (1 - np.cos(np.pi * t))

        # Right smooth ramp
        right_mask = (x > x1 - width1) & (x <= x1)
        t = (x1 - x[right_mask]) / width1
        w[right_mask] = 0.5 * (1 - np.cos(np.pi * t))

        # Compute derivative of derivative

        curv_d  = derivative1 (x, curv)
        curv_dd = derivative1 (x, curv_d)
        
        # Penalty = integral of (k'')^2
        # we just look at second derivative to be smooth - no square as we have normal high values in range
        # pen_d  = np.trapezoid (w * np.abs(curv_d),  x)  / 1e3
        pen_dd = np.trapezoid (w * np.abs(curv_dd), x)  / 1e4 # second derivative of curvature should also be smooth

        pen = pen_dd * scale   # sqrt to limit to high values

        # print ( f"Smoothness penalty: {pen:.6f}  pen_dd: {pen_dd:.6f} " )

        return pen


    @staticmethod
    def _penalty_bumps (x : np.ndarray, curv : np.ndarray, 
                        region : tuple | None = (0.05, 0.9),    
                        max_reversals: int = 0,
                        scale: float = 0.01) -> float:
        """
        Penalize reversals of derivative of curvature derivatives in a given x region.

        This is a measure of real bumps
        
        Args:
            x: x coordinates.
            curv: Curvature values sampled at ``x``.
            max_reversals: Maximum allowed curvature reversals (sign changes).
            scale: Scaling factor for the returned penalty.
        """

        # mask region of interest
        if isinstance(region, tuple):
            x_start, x_end = region
            body_mask = (x >= x_start) & (x <= x_end)
            x_body    = x    [body_mask]
            curv_body = curv[body_mask]
        else:
            x_body    = x
            curv_body = curv

        # Compute derivative of derivative
        curv_d  = derivative1 (x_body, curv_body)
        curv_dd = derivative1 (x_body, curv_d)


        # noramlize to be similar to curv values and avoid scale issues with penalty threshold
        curv_d = np.abs(curv_d) / 10.0
        curv_dd = curv_dd/ 100.0

        # curvature should montonically decrease in body region 
        #  - also becoming negative (reversal of curvature)
        # -> avoid reversals of derivative of curvature 

        # pen_d = Matcher._penalty_reversals (x_body, curv_d, threshold=0.3, scale=scale*0.01)  
        pen_d = Matcher._penalty_reversals (x_body, curv_d, threshold=0.03, scale=2.0)  

        # derivative of curvature decreases and may increase again
        # -> allow max_reversals of derivative of derivative  

        pen_dd = Matcher._penalty_reversals (x_body, curv_dd, threshold=0.02, 
                                             max_reversals=max_reversals, scale=1.0)  

        pen = (pen_d + pen_dd) * scale

        return pen


    #--------------------

    def _calc_dv_bounds (self, ncp : int,  max_thickness: float) -> list [tuple]: 
        """ 
        determine a good estimate for the design variable bounds.
            LE (cp0), cp1 and TE (cp-1) are fixed, 
            so only the inner control points are design variables.
        Args:
            ncp: number of control points
            max_thickness: maximum thickness of the airfoil (for y bounds)
            
        Returns:
            list[tuple]: List of bound tuples for each design variable.
        """

        bounds = []

        x_max = 0.98
        x_min = 0.0005
        y_max = abs(max_thickness) * 2.5           # solution space is positive
        y_min = -0.02                              # SA7036i needs negative cp-2 

        for icp in range (2, ncp-1):                

            bounds.append ((x_min, x_max))
            bounds.append ((y_min, y_max))             

        return bounds 



    def _map_curve_to_dv (self) -> list [float]: 
        """ 
        Map curve control points to the optimization designvariable vector.
            LE (cp0), cp1 and TE (cp-1) are fixed, 
            so only the inner control points are design variables.

        Returns:
            tuple[list, list]: Variable values and matching bound tuples.
        """

        sign   = -1 if self._side.isLower else 1        # lower side: y is inverted in solution space
        cp_x   = self._curve.cpoints_x
        cp_y   = self._curve.cpoints_y 
        ncp    = len( cp_x )
        vars   = []

        for icp in range (2, ncp-1):               
                                                   
            vars.append   (cp_x[icp])
            vars.append   (sign * cp_y[icp])            # solution space is always positive (sign handles upper/lower)

        return vars 


    def _map_dv_to_curve (self, vars: list): 
        """Map optimization variables back to curve control points."""

        sign   = -1 if self._side.isLower else 1         # lower side: y is inverted in solution space
        cp_x   = self._curve.cpoints_x
        cp_y   = self._curve.cpoints_y
        ncp    = len( cp_x )
        ivar   = 0

        for icp in range (2, ncp-1):                # skip LE (0), cp1 (1) and TE (ncp-1)
            cp_x[icp] = vars[ivar];  ivar += 1
            cp_y[icp] = sign * vars[ivar];  ivar += 1

        # cp_y[1] is determined analytically from target LE curvature and current cp_x[2]

        cp_y[1] = sign * self._curve.cp_y1_from_curvature (self._targets.le_curvature, cp_x[2], 
                                                           degree=self._curve.degree, ncp=ncp)    # negative for lower side

        self._curve.set_cpoints (cp_x, cp_y)
        # Note: _u (panel distribution) is NOT reset here for performance - it's set once per optimization pass
        # and stays fixed. Arc-length recalculation on every objective evaluation would be too expensive.


    # ------ core run --------------


    def _objectiveFn (self, variables : list, show_info = False ) -> float:  
        """Evaluate the objective value for the current optimization variables."""
        
        targets = self._targets

        # rebuild BSpline 
        self._map_dv_to_curve (variables)

        # get needed values from current bspline
        x      = self._side.x                                       # single vectorized call

        # fast check if x is monoton 

        x_diff = np.diff(x)
        if not np.all(x_diff > 0):
            # Return high penalty - optimizer should avoid these regions entirely
            # logger.info (f"Non-monotonic x detected - returning high penalty")
            return 10.0

        # get curvature of current curve 
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
            penalty_le_curv = self._penalty_le_curv (curv[0], targets.le_curvature, threshold = 0.01, 
                                        scale = 0.00001)
        else:
            penalty_le_curv = 0.0

        # -- le curvature should be monotonically decreasing in the leading-edge region 

        penalty_le_curv_monoton = self._penalty_le_curv_monoton (curv, scale=0.1) 

        # -- te curvature limit

        if targets.max_te_curvature is not None:
            penalty_te_curv = self._penalty_te_curv (curv[-1], targets.max_te_curvature, targets.max_nreversals,
                                        scale = 0.0001)   # 0.01
        else:
            penalty_te_curv = 0.0

        # -- penalty for curvature derivatives not being smooth to avoid bumps 

        if targets.bump_control:
            penalty_bumps = self._penalty_bumpiness (x, curv, 
                                        max_reversals=targets.max_nreversals, 
                                        scale=0.0500)  
        else:
            penalty_bumps = 0.0

        # -- penalty for curvature reversals

        penalty_reversals = self._penalty_reversals (x, curv, region = (0.1, 1.0),
                                        max_reversals = targets.max_nreversals,
                                        scale = 0.001) 

        # objective function is sum of single objectives and penalties - should be as low as possible
        
        obj = obj_rms + penalty_le_curv + penalty_le_curv_monoton + penalty_te_curv + penalty_bumps + penalty_reversals

        if self._nevals%50 == 0 or show_info:  
            logger.info (f"{self._nevals:4d}:  "
                    f"obj: {obj:.6f}   "
                    f"{('rms: '        + f'{obj_rms:.6f}   ') if obj_rms > 1e-9 else ''}"
                    f"{('le_curv: '    + f'{penalty_le_curv:.6f}   ') if penalty_le_curv > 1e-9 else ''}"
                    f"{('le_monoton: ' + f'{penalty_le_curv_monoton:.6f}   ') if penalty_le_curv_monoton > 1e-9 else ''}"
                    f"{('te_curv: '    + f'{penalty_te_curv:.6f}   ') if penalty_te_curv > 1e-9 else ''}"
                    f"{('bumps: '      + f'{penalty_bumps:.6f}   ')   if penalty_bumps > 1e-9 else ''}"
                    f"{('reversals: '  + f'{penalty_reversals:.6f}')  if penalty_reversals > 1e-9 else ''}")

        self._nevals += 1                       # counter of objective evaluations (for entertainment)

        # signal parent with new results 
        if self._nevals%50 == 0 or show_info:  
            result = Match_Result(self._side, self._targets, rms=obj_rms, objective=obj, curv=curv)
            self.sig_new_results.emit (self._ipass, self._nevals, result)
            self.msleep(2)                      # give parent some time to do updates

        return obj 

    

    def _run_single_pass (self, ncp = 6) -> float: 
        """Run one Nelder-Mead optimization pass for a fixed control-point count."""
    
        # ----- objective function

        f = lambda dv : self._objectiveFn (dv) 

        bounds      = self._calc_dv_bounds (ncp, self._targets._side.max_xy[1])   

        # -- reset Bezier/B-Spline to standard start position before each run 
        #       Golbal search don't need it - but cp arrays must be resized to ncp

        self._side.re_fit_curve(self._targets.side, le_curvature=self._targets.le_curvature, ncp=ncp)   

        # ----- optional global search differential evolution find dv_start --------

        if ncp < 5:

            self._nevals     = 0                                # current number of objective function evals

            self.sig_pass_start.emit (self._ipass, ncp, True)   # dialog can update UI, new ncp, global search
            self.msleep(10)                                     # give parent some time to do updates
    
            n_vars      = len(bounds)
            pop_size    = max(20,  n_vars * 5)                  # 10-15x the number of variables
            generations = max(300, n_vars * 100)                # Scale with problem complexity

            dv_start, _, gen = differential_evolution (
                    f, bounds,
                    bound_mode='reflect',
                    pop_size=pop_size, mutation_factor=0.6, crossover_rate=0.9,
                    generations=generations,
                    no_improve_break=30, no_improve_thr=1e-3,   # Threshold for improvement
                    stop_callback=self.isInterruptionRequested, # QThread method 
                    seed=42)                                    # Reproducible results
        
            objective = self._objectiveFn (dv_start, show_info=True)  # final evaluation with info printout
            logger.info (f"Finished DE within {gen} generations, {self._nevals} evals, objective: {objective:.6f}")

            step_size = 0.1                                     # fixed step size for Nelder-Mead after global search 

        else:

            step_size = self._step_size(ncp)                    # step size based on number of control points

            dv_start = self._map_curve_to_dv ()

        # ----- nelder mead find minimum --------

        self.sig_pass_start.emit (self._ipass, ncp, False)      # dialog can update UI, new ncp
        self.msleep(10)                                         # give parent some time to do updates

        self._nevals = 0 

        max_iter  = len(dv_start) * 300                         # max_iter based on current number of variables

        res, niter = nelder_mead (f, dv_start,
                    step=step_size, no_improve_thr=1e-7,             
                    no_improv_break_beginning=150, no_improv_break=100, #20
                    min_iter=200, max_iter=max_iter,        
                    bounds = bounds,
                    stop_callback=self.isInterruptionRequested)  # QThread method 

        dv = res[0]

        objective = self._objectiveFn (dv, show_info=True)          # final evaluation with info printout
        logger.info (f"Finished nelder mead after {niter} iterations and {self._nevals} evaluations.") 

        #-- evaluate the new y values on Bezier for the target x-coordinate

        self._map_dv_to_curve (dv)

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
            npc_list = range(self._side.NCP_AUTO_RANGE[0], self._side.NCP_AUTO_RANGE[1] + 1)  
        else:
            npc_list = [self._ncp]

        # Dictionary to store all results: {objective: control_points}
        results = {}
        ncp_devaluation = 1.0

        for ncp in npc_list:

            self._ipass += 1
            logger.info (f"---- Pass {self._ipass}  ncp: {ncp} ")

            # run single nelder mead optimization 

            objective = self._run_single_pass (ncp=ncp)

            # Store result and decide if good enough to end 

            objective_devaluated = objective * ncp_devaluation
            results[objective_devaluated] = self._curve.cpoints.copy()
            ncp_devaluation *= 1.05   # slightly devalue higher ncp results to prefer simpler solutions if objective is similar

            if objective < 0.000040:                
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

        result = Match_Result (self._side, self._targets)
        self.sig_finished.emit (result)


# --------------------


class Match_Result:
    """Structured result for an airfoil matching operation."""

    def __init__(self, side: Side_Airfoil_Curve, targets: Match_Targets, 
                 *, rms: float | None = None, objective: float | None = None, 
                 curv: np.ndarray | None = None):
        """Initialize match result with calculated or provided metrics.
        
        Args:
            side: The airfoil side being matched.
            targets: Match targets for this optimization.
            rms: Pre-calculated RMS deviation (calculated if None).
            objective: Objective function value (optional).
            curv: Pre-calculated curvature array with correct sign (calculated if None).
        """

        self._targets = targets

        self._cpoints = side.curve.cpoints.copy()           # store control points of the final curve
        self._name    = f"{side.name}"
        self._isUpper = side.isUpper
        self._ncp_default = side.NCP_DEFAULT
        
        # Calculate and store all metrics
        self._rms = rms if rms is not None else side.target_deviation.rms()
        
        # Use provided curv (already has correct sign) or calculate from side
        if curv is None: 
            curv = side.curvature().y if side.isLower else -side.curvature().y  # curve for upper side has to be negated
        
        self._le_curvature = abs(curv[0])
        self._te_curvature = curv[-1]
        self._nreversals   = Line(x=side.x, y=curv).nreversals() 
        self._bumps        = Matcher._penalty_bumps (side.x, curv, 
                                                     max_reversals=targets.max_nreversals, scale=1.0)
        
        self._max_dy_tuple = side.target_deviation.max_dy()  # (position, value)
        
        # Optional fields
        self._objective    = objective

    @property
    def name(self) -> str:
        """Name of the result, e.g. for labeling in the UI."""
        return self._name

    @property
    def isUpper(self) -> bool:
        """Whether this result is for the upper side of the airfoil."""
        return self._isUpper
         
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
        return len(self._cpoints) 
    
    @property
    def le_curvature(self) -> float:
        """Leading-edge curvature."""
        return round(self._le_curvature, 1) 
    
    @property
    def te_curvature(self) -> float:
        """Trailing-edge curvature."""
        return round(self._te_curvature, 2) 
    
    @property
    def max_dy_position(self) -> float:
        """Position (x-coordinate) of maximum y deviation."""
        return round(self._max_dy_tuple[0], 2) 
    
    @property
    def max_dy(self) -> float:
        """Maximum y deviation from the target."""
        return round(self._max_dy_tuple[1], 6) 
    
    @property
    def objective(self) -> float | None:
        """Final objective function value."""
        return self._objective
       
    @property
    def nreversals(self) -> int | None:
        """Number of curvature reversals."""
        return self._nreversals
    
    @property 
    def bumps (self) -> float | None:
        """Bump penalty value - unscaled"""
        return round(self._bumps, 6) 
    
    @property
    def style_deviation(self) -> style:
        """UI style for this result's deviation."""
        if self._rms < 0.0001:                          # equals .01% deviation
            return style.GOOD
        elif self._rms < 0.0003:
            return style.NORMAL
        else:
            return style.WARNING
    
    @property
    def style_curv_le(self) -> style:
        """UI style for this result's LE curvature."""
        delta = abs(self.targets.le_curvature - self._le_curvature)
        
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
        max_curv_te = abs(self.targets.max_te_curvature) * (-1) ** self.targets.max_nreversals  

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
        
        if self._nreversals <= self.targets.max_nreversals:
            return style.GOOD
        else:
            return style.WARNING

    @property
    def style_bumps(self) -> style:
        """UI style for this result's bump penalty."""
        
        if self._bumps <= 0.01:
            return style.GOOD
        elif self._bumps <= 0.3:
            return style.NORMAL
        else:
            return style.WARNING


    def is_ncp_good(self) -> bool:
        """Determine if the number of control points is good based on targets."""
        if self.targets.max_nreversals:
            # reflexed or rearload - more complex shapes - allow higher ncp
            good_ncp = self._ncp_default + 1
        else:
            # simple shapes - lower ncp is sufficient and more robust
            good_ncp = self._ncp_default

        return self.ncp <= good_ncp

    @property
    def style_ncp(self) -> style:
        """UI style for this result's number of control points."""

        return style.GOOD if self.is_ncp_good() else style.NORMAL


    def is_good_enough(self) -> bool:
        """Return whether this result satisfies the quality targets."""

        # return good if max one styles is normal, the rest is good

        styles = [
            self.style_deviation,
            self.style_max_dy,
            self.style_curv_le,
            self.style_curv_te,
            self.style_nreversals,
            self.style_bumps
        ]
        normal_count = sum(1 for s in styles if s == style.NORMAL)
        good = normal_count <= 1 and all(s == style.GOOD for s in styles if s != style.NORMAL)  
        
        return good
        

    def is_perfect (self) -> bool:
        """Return whether this result is perfect (meets all targets with good style)."""
        return all(s == style.GOOD for s in (
            self.style_curv_le,
            self.style_curv_te,
            self.style_deviation,
            self.style_max_dy,
            self.style_nreversals,
            self.style_bumps
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
        
        self._matcher_upper = Matcher()
        self._matcher_upper.set_match(geo.upper, self._targets_upper)
        
        self._matcher_lower = Matcher()
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
        