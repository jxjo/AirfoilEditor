#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Bridge module between AirfoilEditor and NeuralFoil.

Main entry point:
    Neuralfoil_Evaluator.get_polar_data_set (x, y, meta)   →  Polar_Data_Set
"""

import numpy as np
import time

from dataclasses        import dataclass
from .polar_dto         import Polar_Bubble_Range, Polar_Data_Row, Polar_Data_Set, Polar_File_Meta

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)

# Ceck if NeuralFoil core is available

try:
    from .neuralfoil_core.neuralfoil.core_api import (get_aero_from_kulfan_parameters,
                                                      available_model_sizes,
                                                      N_BL_POINTS,
                                                      bl_x_points)
    _NF_AVAILABLE = True
    _NF_ERROR = ''
except ImportError:
    _NF_AVAILABLE = False
    _NF_ERROR = 'NeuralFoil could not be loaded'



@dataclass(frozen=True)
class Airfoil_As_CST:
    """CST-Kulfan airfoil representation as API DTO for NeuralFoil evaluation."""

    upper_weights: np.ndarray
    lower_weights: np.ndarray
    le_weight: float
    te_thickness: float
    derotation_angle: float = 0.0  # angle airfoil was derotated to normalize in case of flapped airfoil 



class Neuralfoil_Evaluator:
    """NeuralFoil polar evaluation — returns backend-agnostic DTOs.

    Mirrors the role of Xfoil_Polar_Parser in xo2_driver:
        Xfoil_Polar_Parser.parse_file (path)                    → Polar_Data_Set  (loads from file)
        Neuralfoil_Evaluator.get_polar_data_set (x, y, meta)    → Polar_Data_Set  (evaluates)
    """

    NAME        = "NeuralFoil"

    ready       = _NF_AVAILABLE
    ready_msg   = _NF_ERROR


    ALPHA_DEFAULT      = np.arange (-6.0, 14.0, 0.5)   # fallback when meta has no val_range
    ALPHA_AUTO_MIN     = -20.0                          # lower bound for auto_range evaluation
    ALPHA_AUTO_MAX     =  20.0                          # upper bound for auto_range evaluation
    AUTO_RANGE_DEG     =  1.0                           # degrees kept/cut around stall
    CL_AUTO_MAX        =  1.5                           # upper bound for T2 auto_range evaluation
    CL_AUTO_STEP       =  0.05                          # fallback step when auto_range has no val_range
    T2_AUTO_RE_FACTOR  = 10.0                           # max effective Re as a factor of Re * sqrt(cl)

    MODEL_SIZE_DEFAULT = "xlarge"
    MIN_CONFIDENCE     = 0.5                            # minimum NeuralFoil confidence for a valid polar point
    BUBBLE_H_THRESHOLD =  3.8                           # shape factor above which a panel is considered separated

    T2_CL_TOLERANCE      = 1e-4
    T2_MAX_ITERATIONS    = 20
    T2_MAX_ALPHA_STEP    = 2.0
    T2_SEED_ALPHA_STEP   = 0.5
    T2_MIN_SEED_ALPHA_STEP = 0.05
    T2_REFINE_CL_STEP    = 0.01

    @staticmethod
    def is_available () -> bool:
        """ True if the vendored NeuralFoil core can be imported """
        return _NF_AVAILABLE


    @staticmethod
    def available_model_sizes () -> list[str]:
        """ Sorted list of valid NeuralFoil model size strings — empty if not available """
        if not _NF_AVAILABLE:
            return []
        return available_model_sizes


    @classmethod
    def get_polar_data_set (cls,
                            airfoil_as_cst: Airfoil_As_CST,
                            meta: Polar_File_Meta,
                            model_size: str = MODEL_SIZE_DEFAULT,
                            min_confidence: float = MIN_CONFIDENCE) -> Polar_Data_Set:
        """Evaluate a polar for an airfoil defined by its Kulfan (CST) parameters.

        T1 retains the fixed-Re alpha sweep. T2 solves a positive-cl sweep with
        meta.re interpreted as Re * sqrt(cl), using either explicit or automatic
        cl bounds. T2 stops at the first failed solve and refines the upper end
        between the last successful and first failed target, without retries.

        Args:
            airfoil_as_cst: CST-Kulfan definition of the airfoil — Airfoil_As_CST instance
            meta:        polar parameters — re, ncrit, val_range, xtript/b, etc.
            model_size: NeuralFoil model size ("xxsmall".."xxxlarge", default "xlarge").
            min_confidence: Minimum confidence for a valid point (default 0.5).

        Returns:
            Polar_Data_Set with source="neuralfoil" and nf_confidence per row.
        """
        if not cls.ready:
            raise RuntimeError ("NeuralFoil core is not available")

        t0 = time.perf_counter ()

        kulfan_parameters = {
            "upper_weights"      : airfoil_as_cst.upper_weights,
            "lower_weights"      : airfoil_as_cst.lower_weights,
            "leading_edge_weight": airfoil_as_cst.le_weight,
            "TE_thickness"       : airfoil_as_cst.te_thickness,
        }

        if meta.polar_type == "T2":
            alpha_arr, predict = cls._predict_T2 (kulfan_parameters, meta, model_size)
        else:
            alpha_arr = Neuralfoil_Evaluator._alpha_from_meta (meta)
            if meta.auto_range:
                step      = meta.val_range[2] if meta.val_range is not None else 0.5
                alpha_arr = np.arange (cls.ALPHA_AUTO_MIN, cls.ALPHA_AUTO_MAX + step * 0.5, step)

            predict = get_aero_from_kulfan_parameters (
                kulfan_parameters = kulfan_parameters,
                alpha             = alpha_arr,
                Re                = meta.re,
                n_crit            = meta.ncrit if meta.ncrit is not None else 9.0,
                xtr_upper         = meta.xtript if meta.xtript is not None else 1.0,
                xtr_lower         = meta.xtripb if meta.xtripb is not None else 1.0,
                model_size        = model_size,
            )

        result_meta = Polar_File_Meta (
            source        = "neuralfoil",
            polar_type    = meta.polar_type,
            re            = meta.re,
            ma            = meta.ma,
            ncrit         = meta.ncrit,
            xtript        = meta.xtript,
            xtripb        = meta.xtripb,
            flap_angle    = meta.flap_angle,
            x_flap        = meta.x_flap,
            y_flap        = meta.y_flap,
            spec_var      = meta.spec_var,
            val_range     = meta.val_range,
            auto_range    = meta.auto_range,
            nf_model_size = model_size,
        )

        # mask out points with low NeuralFoil confidence
        if min_confidence is not None:
            alpha_arr, predict = Neuralfoil_Evaluator._apply_confidence_mask (alpha_arr, predict, min_confidence)

        # apply derotation angle to the meta if the airfoil was derotated to normalize (flapped airfoil)
        if airfoil_as_cst.derotation_angle != 0.0:
            alpha_arr = alpha_arr - airfoil_as_cst.derotation_angle

        # apply auto_range mask to trim the polar to the interesting region between stalls
        if meta.auto_range and meta.polar_type != "T2":
            alpha_arr, predict = Neuralfoil_Evaluator._apply_auto_range_mask (alpha_arr, predict)

        # build DTO rows from NeuralFoil prediction dict
        result =  Polar_Data_Set (
            meta = result_meta,
            rows = Neuralfoil_Evaluator._build_rows (predict, alpha_arr),
        )

        logger.info (f"NeuralFoil '{model_size}' evaluated {len (alpha_arr)} points in {(time.perf_counter()-t0)*1000:.0f} ms")

        return result


    @classmethod
    def _predict_T2 (cls, kulfan_parameters: dict, meta: Polar_File_Meta,
                     model_size: str) -> tuple[np.ndarray, dict]:
        """Sweep a T2 cl range, then refine its first failure interval.

        The endpoint is the highest successfully solved cl, not a guaranteed
        physical cl_max. For speed, failures end the sweep without a cold retry.

        Args:
            kulfan_parameters: Normalized CST parameters passed to NeuralFoil.
            meta: cl range or auto-range settings and Re * sqrt(cl) constant.
            model_size: NeuralFoil network size.

        Returns:
            Normalized angles and final predictions for converged, rising-branch points.

        Raises:
            RuntimeError: If parameters are unsupported or the first point fails.
        """
        if meta.spec_var != "cl":
            raise RuntimeError ("NeuralFoil T2 requires cl as its specification variable")
        if meta.re is None or not np.isfinite (meta.re) or meta.re <= 0.0:
            raise RuntimeError ("NeuralFoil T2 requires a positive Re * sqrt(cl)")

        if meta.auto_range:
            lo = 1.0 / cls.T2_AUTO_RE_FACTOR ** 2
            hi = cls.CL_AUTO_MAX
            step = meta.val_range[2] if meta.val_range is not None else cls.CL_AUTO_STEP
        elif meta.val_range is not None:
            lo, hi, step = meta.val_range
        else:
            raise RuntimeError ("NeuralFoil T2 requires a cl range")

        if not np.all (np.isfinite ([lo, hi, step])) or not (0.0 < lo <= hi and step > 0.0):
            raise RuntimeError ("NeuralFoil T2 requires a finite, positive cl range and step")

        cl_targets  = np.arange (lo, hi + step * 0.5, step)
        cl_targets  = cl_targets[cl_targets <= hi + 1e-12]
        angles      = []
        predictions = []
        alpha_guess = None
        last_cl     = None
        failed_cl   = None

        # Main sweep: follow the rising branch until the requested upper bound or
        # the first failed solve. Do not retry from zero or try later coarse targets.
        for cl_target in cl_targets:
            # Reuse only the previous angle, never its lift: the new target has a
            # different Reynolds number and needs fresh evaluations of both seeds.
            solution = cls._solve_T2_point (kulfan_parameters, meta, model_size, float (cl_target),
                                            alpha_guess=alpha_guess)
            if solution is None:
                failed_cl = float (cl_target)
                break

            alpha, prediction = solution
            angles.append (alpha)
            predictions.append (prediction)
            alpha_guess = alpha
            last_cl = float (cl_target)

        if not predictions:
            raise RuntimeError (f"NeuralFoil T2 could not solve the first point at cl={lo:.4f}")

        # Refine only the gap below the failed target. Start AFTER the last success
        # to avoid duplicates, and never repeat the known failed coarse target.
        fine_step = min (cls.T2_REFINE_CL_STEP, step)
        if failed_cl is not None and fine_step < step:
            refine_targets = np.arange (last_cl + fine_step, failed_cl, fine_step)
            refine_alpha_step = max (cls.T2_MIN_SEED_ALPHA_STEP,
                                     cls.T2_SEED_ALPHA_STEP * fine_step / step)
            for cl_target in refine_targets:
                if cl_target >= failed_cl - 1e-12:
                    break
                solution = cls._solve_T2_point (kulfan_parameters, meta, model_size, float (cl_target),
                                                alpha_guess=alpha_guess,
                                                seed_alpha_step=refine_alpha_step)
                if solution is None:
                    break

                alpha, prediction = solution
                angles.append (alpha)
                predictions.append (prediction)
                alpha_guess = alpha
                last_cl = float (cl_target)

        if failed_cl is not None:
            logger.debug (f"NeuralFoil T2 sweep ended at highest solved cl={last_cl:.4f}")

        # Each accepted prediction contains one operating point. Join its arrays
        # along the point axis, preserving panel dimensions and any constant values.
        predict = {}
        for key, value in predictions[0].items ():
            if isinstance (value, np.ndarray) and value.ndim > 0 and value.shape[0] == 1:
                predict[key] = np.concatenate ([prediction[key] for prediction in predictions], axis=0)
            else:
                predict[key] = value

        return np.asarray (angles), predict


    @classmethod
    def _solve_T2_point (cls, kulfan_parameters: dict, meta: Polar_File_Meta,
                         model_size: str, cl_target: float,
                         alpha_guess: float | None = None,
                         seed_alpha_step: float | None = None) -> tuple[float, dict] | None:
        """Find alpha for one T2 target using a step-limited scalar secant iteration.

        Args:
            kulfan_parameters: Normalized CST parameters passed to NeuralFoil.
            meta: Validated polar parameters, including the Re * sqrt(cl) constant.
            model_size: NeuralFoil network size.
            cl_target: Positive target lift coefficient.
            alpha_guess: Optional normalized angle to seed continuation of a sweep.
            seed_alpha_step: Optional alpha interval for the continuation seed pair.

        Returns:
            Normalized alpha and its actual NeuralFoil prediction, or None if the
            solve fails or the solution is not on a locally rising lift branch.
        """
        # Target lift fixes Reynolds BEFORE iteration. Intermediate lift values
        # must never change Reynolds, or we would solve a different operating point.
        reynolds = meta.re / np.sqrt (cl_target)

        def fail (reason: str) -> None:
            logger.error ("NeuralFoil T2 solve failed: %s (cl=%.4f, Re=%.0f, alpha=%.4f)",
                          reason, cl_target, reynolds, alpha_current)
            return None

        def evaluate (alpha: float | list[float]) -> tuple[np.ndarray, dict]:
            alpha_values = np.atleast_1d (alpha)
            prediction = get_aero_from_kulfan_parameters (
                kulfan_parameters = kulfan_parameters,
                alpha             = alpha_values,
                Re                = np.full (len (alpha_values), reynolds),
                n_crit            = meta.ncrit if meta.ncrit is not None else 9.0,
                xtr_upper         = meta.xtript if meta.xtript is not None else 1.0,
                xtr_lower         = meta.xtripb if meta.xtripb is not None else 1.0,
                model_size        = model_size,
            )
            lift_values = np.asarray (prediction["CL"]).reshape (-1)
            return lift_values, prediction

        # A previous solved angle lets us estimate the local slope over a smaller
        # interval. Without a guess, retain the original 0 and 2 degree starting pair.
        if alpha_guess is None:
            initial_step = cls.T2_MAX_ALPHA_STEP
        else:
            initial_step = (cls.T2_SEED_ALPHA_STEP if seed_alpha_step is None
                            else seed_alpha_step)
        alpha_previous = 0.0 if alpha_guess is None else float (np.clip (
            alpha_guess, cls.ALPHA_AUTO_MIN, cls.ALPHA_AUTO_MAX - initial_step))
        alpha_current  = alpha_previous + initial_step

        # Both starting angles share Reynolds, so obtain their lift in one NF call.
        # Retain only the current point's prediction; all later updates stay scalar.
        initial_lift, initial_prediction = evaluate ([alpha_previous, alpha_current])
        cl_previous = float (initial_lift[0])
        cl_current  = float (initial_lift[1])
        prediction  = {}
        for key, value in initial_prediction.items ():
            if isinstance (value, np.ndarray) and value.ndim > 0 and value.shape[0] == 2:
                prediction[key] = value[1:2]
            else:
                prediction[key] = value

        # Each pass checks the current point, then takes at most one secant step.
        # The extra final check allows all T2_MAX_ITERATIONS updates to be used.
        for iteration in range (cls.T2_MAX_ITERATIONS + 1):
            if not np.isfinite (cl_previous) or not np.isfinite (cl_current):
                return fail ("non-finite lift prediction")

            delta_alpha = alpha_current - alpha_previous
            slope = (cl_current - cl_previous) / delta_alpha if delta_alpha != 0.0 else np.nan

            if abs (cl_current - cl_target) <= cls.T2_CL_TOLERANCE:
                if not np.isfinite (slope) or slope <= 1e-6:
                    return None
                return alpha_current, prediction

            if iteration == cls.T2_MAX_ITERATIONS:
                return fail (f"iteration limit reached (cl residual={cl_current - cl_target:.6f})")

            # A zero angle change means we hit a bound. Flat/falling secants are
            # rejected rather than allowing an unstable step through the stall region.
            if delta_alpha == 0.0:
                return fail ("alpha bound reached or zero secant step")
            if not np.isfinite (slope) :
                return fail (f"non-finite secant slope")
            
            if slope <= 1e-6:
                return None                                         # flat or falling secant, likely near stall

            correction = (cl_target - cl_current) / slope
            correction = float (np.clip (correction, -cls.T2_MAX_ALPHA_STEP, cls.T2_MAX_ALPHA_STEP))
            alpha_next = float (np.clip (alpha_current + correction, cls.ALPHA_AUTO_MIN, cls.ALPHA_AUTO_MAX))

            # Shift the secant pair, then evaluate only the new operating point.
            alpha_previous = alpha_current
            cl_previous    = cl_current
            alpha_current  = alpha_next
            lift_current, prediction = evaluate (alpha_current)
            cl_current = float (lift_current.item ())

        return None

    
    @staticmethod
    def _alpha_from_meta (meta: Polar_File_Meta) -> np.ndarray:
        """ Build alpha array from meta val_range or fall back to default """
        if meta.val_range is not None:
            lo, hi, step = meta.val_range
            return np.arange (lo, hi + step * 0.5, step)
        return Neuralfoil_Evaluator.ALPHA_DEFAULT.copy()


    @staticmethod
    def _apply_auto_range_mask (alpha_arr: np.ndarray,
                                predict: dict) -> tuple[np.ndarray, dict]:
        """Trim the wide auto_range polar to the interesting region between stalls.

        Going up from alpha=0: find the first cl maximum and keep AUTO_RANGE_DEG past it.
        Going down from alpha=0: find the lowest cl/cd point and keep AUTO_RANGE_DEG past it.

        Args:
            alpha_arr: Increasing, uniformly spaced angles of attack.
            predict: NeuralFoil prediction arrays, including CL and CD.

        Returns:
            Trimmed angles and corresponding prediction arrays.
        """
        cl = np.asarray (predict.get ("CL", []), dtype=float)
        cd = np.asarray (predict.get ("CD", []), dtype=float)
        n  = len (alpha_arr)

        if len (cl) != n or len (cd) != n or n == 0:
            return alpha_arr, predict

        # points per degree from the (uniform) alpha spacing
        step      = float (alpha_arr[1] - alpha_arr[0]) if n > 1 else 0.5
        n_per_deg = max (1, round (Neuralfoil_Evaluator.AUTO_RANGE_DEG / step))

        # index closest to alpha = 0
        i0 = int (np.argmin (np.abs (alpha_arr)))

        # upper part: going up from alpha=0 — find first stall (where cl stops increasing)
        cl_up     = cl[i0:]                                     # cl values from alpha=0 upward
        falling   = np.where (np.diff (cl_up) < 0)[0]           # first point where cl starts decreasing
        i_peak_up = i0 + int (falling[0]) if falling.size > 0 else i0 + int (np.argmax (cl_up))
        i_hi      = min (n - 1, i_peak_up + n_per_deg)

        # lower part: going down from alpha=0 — find lowest cl/cd point, keep 1° past it
        glide_down = (cl / cd)[i0::-1]                          # cl/cd values from alpha=0 downward
        i_peak_dn  = i0 - int (np.argmin (glide_down))
        i_lo       = min (i0, i_peak_dn - n_per_deg)            # stop 1° after lower stall
        i_lo       = max (0, i_lo)                             # clamp to start of array

        sl = slice (i_lo, i_hi + 1)
        predict_masked = {
            k: (v[sl] if isinstance (v, np.ndarray) and v.shape[0] == n else v)
            for k, v in predict.items()
        }
        return alpha_arr[sl], predict_masked


    @staticmethod
    def _apply_confidence_mask (alpha_arr: np.ndarray, predict: dict, min_confidence: float) -> tuple[np.ndarray, dict]:
        """
        Mask out points with NeuralFoil confidence below min_confidence.

        Returns:
            alpha_arr_masked, predict_masked
        """
        conf = np.asarray (predict.get ("analysis_confidence", []), dtype=float)
        n    = len (alpha_arr)

        if len (conf) != n:
            return alpha_arr, predict

        mask = conf >= min_confidence
        predict_masked = {
            k: (v[mask] if isinstance (v, np.ndarray) and v.shape[0] == n else v)
            for k, v in predict.items()
        }
        return alpha_arr[mask], predict_masked


    @staticmethod
    def _build_rows (predict: dict, alpha_arr: np.ndarray) -> list[Polar_Data_Row]:
        """ Convert NeuralFoil prediction dict to a list of Polar_Data_Row """

        if len (alpha_arr) == 0:
            return []

        def _col (key: str) -> np.ndarray:
            val = predict.get (key)
            if val is None:
                return np.full (len (alpha_arr), np.nan)
            arr = np.asarray (val, dtype=float).reshape (-1)
            return arr if arr.size > 1 else np.full (len (alpha_arr), arr.item())

        def _panel_matrix (prefix: str, n_panels: int) -> np.ndarray:
            """Local helper to reshape panel values into alpha x panels layout."""
            cols = []
            for i in range (n_panels):
                key = f"{prefix}_{i}"
                val = predict.get (key)
                if val is None:
                    cols.append (np.full (len (alpha_arr), np.nan))
                else:
                    arr = np.asarray (val, dtype=float).reshape (-1)
                    if arr.size == 0:
                        cols.append (np.empty (0, dtype=float))
                    elif arr.size == 1:
                        cols.append (np.full (len (alpha_arr), float (arr.item())))
                    else:
                        cols.append (arr)

            if not cols:
                return np.empty ((0, 0), dtype=float)

            n_alpha = len (alpha_arr)
            matrix = np.full ((n_alpha, len (cols)), np.nan, dtype=float)
            for j, col in enumerate (cols):
                if len (col) == n_alpha:
                    matrix[:, j] = col
                elif len (col) == 1:
                    matrix[:, j] = float (col[0])
            return matrix

        cl   = _col ("CL")
        cd   = _col ("CD")
        cm   = _col ("CM")
        xtrt = _col ("Top_Xtr")
        xtrb = _col ("Bot_Xtr")
        conf = _col ("analysis_confidence")

        n_panels = N_BL_POINTS
        upper_ue = _panel_matrix ("upper_bl_ue/vinf", n_panels)
        lower_ue = _panel_matrix ("lower_bl_ue/vinf", n_panels)
        cp_upper = 1.0 - upper_ue ** 2
        cp_lower = 1.0 - lower_ue ** 2
        cp_min = np.nanmin (np.concatenate ((cp_upper, cp_lower), axis=1), axis=1)

        upper_H = _panel_matrix ("upper_bl_H", n_panels)
        lower_H = _panel_matrix ("lower_bl_H", n_panels)
        bubble_top = Neuralfoil_Evaluator._estimate_bubble (upper_H, xtrt)
        bubble_bot = Neuralfoil_Evaluator._estimate_bubble (lower_H, xtrb)

        return [
            Polar_Data_Row (
                alpha      = float (alpha_arr[i]),
                cl         = float (cl[i]),
                cd         = float (cd[i]),
                cdp        = None,                  # NeuralFoil does not provide CDp
                cm         = float (cm[i]),
                xtrt       = float (xtrt[i]),
                xtrb       = float (xtrb[i]),
                cp_min     = None if np.isnan (cp_min[i]) else float (cp_min[i]),
                bubble_top = bubble_top[i],
                bubble_bot = bubble_bot[i],
                nf_confidence = None if np.isnan (conf[i]) else float (conf[i]),
            )
            for i in range (len (alpha_arr))
        ]


    @classmethod
    def _estimate_bubble (cls, H: np.ndarray, xtr: np.ndarray) -> list[Polar_Bubble_Range | None]:
        """Estimate a laminar separation bubble per row from the BL shape factor.

        A panel is considered separated once its shape factor exceeds BUBBLE_H_THRESHOLD;
        the bubble is assumed to end at the (natural) transition point, since NeuralFoil
        provides no wall shear stress to detect reattachment directly, unlike XFOIL.
        """
        results: list[Polar_Bubble_Range | None] = []
        for i in range (H.shape[0]):
            if xtr[i] >= 1.0:                              # no transition detected - can't be a bubble
                results.append (None)
                continue
            separated = (H[i] >= cls.BUBBLE_H_THRESHOLD) & (bl_x_points < xtr[i])
            idx = np.where (separated)[0]
            if idx.size == 0:
                results.append (None)
            else:
                x_start = float (bl_x_points[idx[0]])
                x_end   = float (max (bl_x_points[idx[-1]], xtr[i]))
                results.append (Polar_Bubble_Range (x_start=x_start, x_end=x_end))
        return results
