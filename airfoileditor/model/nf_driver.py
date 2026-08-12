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
from .polar_dto         import Polar_Data_Row, Polar_Data_Set, Polar_File_Meta

import logging
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)

# Ceck if NeuralFoil core is available

try:
    from .neuralfoil_core.neuralfoil.core_api import (get_aero_from_kulfan_parameters,
                                                      available_model_sizes)
    _NF_AVAILABLE = True
    _NF_ERROR = ''
except ImportError:
    _NF_AVAILABLE = False
    _NF_ERROR = 'NeuralFoil core could not be imported'



@dataclass(frozen=True)
class Airfoil_As_CST:
    """CST-Kulfan airfoil representation as API DTO for NeuralFoil evaluation."""

    upper_weights: np.ndarray
    lower_weights: np.ndarray
    leading_edge_weight: float
    TE_thickness: float
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

    MODEL_SIZE_DEFAULT = "xlarge"
    MIN_CONFIDENCE     = 0.5                            # minimum NeuralFoil confidence for a valid polar point

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

        Args:
            airfoil_as_cst: CST-Kulfan definition of the airfoil — Airfoil_As_CST instance
            meta:        polar parameters — re, ncrit, val_range, xtript/b, etc.
            model_size:  NeuralFoil model size ("xxsmall".."xxxlarge", default "large")
            min_confidence: minimum NeuralFoil confidence for a valid polar point (default 0.9)

        Returns:
            Polar_Data_Set with source="neuralfoil" and nf_confidence per row.
        """
        if not cls.ready:
            raise RuntimeError ("NeuralFoil core is not available")

        t0 = time.perf_counter ()

        kulfan_parameters = {
            "upper_weights"      : airfoil_as_cst.upper_weights,
            "lower_weights"      : airfoil_as_cst.lower_weights,
            "leading_edge_weight": airfoil_as_cst.leading_edge_weight,
            "TE_thickness"       : airfoil_as_cst.TE_thickness,
        }

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
        if meta.auto_range:
            alpha_arr, predict = Neuralfoil_Evaluator._apply_auto_range_mask (alpha_arr, predict)

        # build DTO rows from NeuralFoil prediction dict
        result =  Polar_Data_Set (
            meta = result_meta,
            rows = Neuralfoil_Evaluator._build_rows (predict, alpha_arr),
        )

        logger.info (f"NeuralFoil '{model_size}' evaluated {len (alpha_arr)} points in {(time.perf_counter()-t0)*1000:.0f} ms")

        return result

    
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
        """
        Trim the wide auto_range polar to the interesting region between stalls.

        Going up from alpha=0:   find cl_max, keep up to AUTO_RANGE_TAIL points past it.
        Going down from alpha=0:  find cl_min, keep up to AUTO_RANGE_TAIL points past it.
        """
        cl = np.asarray (predict.get ("CL", []), dtype=float)
        n  = len (alpha_arr)

        if len (cl) != n or n == 0:
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

        # lower part: going down from alpha=0 — find first local cl_min, stop 1° before it
        cl_down   = cl[i0::-1]                                  # cl values from alpha=0 downward
        rising    = np.where (np.diff (cl_down) > 0)[0]         # first point where cl starts recovering
        i_peak_dn = i0 - int (rising[0]) if rising.size > 0 else i0 - int (np.argmin (cl_down))
        i_lo      = min (i0, i_peak_dn - n_per_deg)             # stop 1° after lower stall
        i_lo      = max (0, i_lo)                               # clamp to start of array

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

        cl   = _col ("CL")
        cd   = _col ("CD")
        cm   = _col ("CM")
        xtrt = _col ("Top_Xtr")
        xtrb = _col ("Bot_Xtr")
        conf = _col ("analysis_confidence")

        return [
            Polar_Data_Row (
                alpha      = float (alpha_arr[i]),
                cl         = float (cl[i]),
                cd         = float (cd[i]),
                cdp        = None,                  # NeuralFoil does not provide CDp
                cm         = float (cm[i]),
                xtrt       = float (xtrt[i]),
                xtrb       = float (xtrb[i]),
                nf_confidence = None if np.isnan (conf[i]) else float (conf[i]),
            )
            for i in range (len (alpha_arr))
        ]
