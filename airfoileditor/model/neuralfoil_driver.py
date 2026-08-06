#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Bridge module between AirfoilEditor and vendored NeuralFoil-Core runtime.

Keep all app-facing integration logic here so vendored code can remain a
clean snapshot under `airfoileditor/model/neuralfoil_core/neuralfoil`.
"""

import numpy as np
from typing import Any

from .polar_dto import Polar_Data_Row, Polar_Data_Set, Polar_File_Meta


class Neuralfoil_Polar_Adapter:
    """Convert NeuralFoil dictionary outputs to backend-agnostic polar DTOs."""

    @staticmethod
    def _as_1d_array(value: float | np.ndarray, n: int | None = None, name: str = "value") -> np.ndarray:
        """Normalize scalar or vector to a 1-D float array.

        If n is given, scalars are broadcast and vectors must match n.
        """
        arr = np.asarray(value, dtype=float).reshape(-1)

        if n is None:
            return arr

        if arr.size == 1:
            return np.full(n, arr.item(), dtype=float)

        if arr.size != n:
            raise ValueError(f"Expected '{name}' with length {n}, got {arr.size}.")

        return arr

    @classmethod
    def to_polar_dataset(
        cls,
        prediction: dict[str, float | np.ndarray],
        alpha: float | np.ndarray,
        re: float | np.ndarray,
        ncrit: float | np.ndarray,
        ma: float = 0.0,
        polar_type: str = "T1",
        xtript: float | None = None,
        xtripb: float | None = None,
        airfoil_name: str | None = None,
    ) -> Polar_Data_Set:
        """Build a PolarDataSet from NeuralFoil core prediction output.

        NeuralFoil core output currently provides CL, CD, CM, Top_Xtr, Bot_Xtr
        but no CDp. In the DTO, `cdp` is therefore set to None.
        """

        alpha_arr = cls._as_1d_array(alpha, name="alpha")
        n_cases = alpha_arr.size

        cl_arr = cls._as_1d_array(prediction["CL"], n=n_cases, name="CL")
        cd_arr = cls._as_1d_array(prediction["CD"], n=n_cases, name="CD")
        cm_arr = cls._as_1d_array(prediction["CM"], n=n_cases, name="CM")
        xtrt_arr = cls._as_1d_array(prediction["Top_Xtr"], n=n_cases, name="Top_Xtr")
        xtrb_arr = cls._as_1d_array(prediction["Bot_Xtr"], n=n_cases, name="Bot_Xtr")

        re_arr = cls._as_1d_array(re, n=n_cases, name="Re")
        ncrit_arr = cls._as_1d_array(ncrit, n=n_cases, name="n_crit")

        rows: list[Polar_Data_Row] = []
        for i in range(n_cases):
            rows.append(
            Polar_Data_Row(
                    alpha=float(alpha_arr[i]),
                    cl=float(cl_arr[i]),
                    cd=float(cd_arr[i]),
                    cdp=None,
                    cm=float(cm_arr[i]),
                    xtrt=float(xtrt_arr[i]),
                    xtrb=float(xtrb_arr[i]),
                )
            )

        meta = Polar_File_Meta(
            source="neuralfoil",
            airfoil_name=airfoil_name,
            polar_type=polar_type,
            re=float(re_arr[0]) if re_arr.size else None,
            ma=float(ma),
            ncrit=float(ncrit_arr[0]) if ncrit_arr.size else None,
            xtript=xtript,
            xtripb=xtripb,
            spec_var="alpha",
        )

        return Polar_Data_Set(meta=meta, rows=rows)


class Neuralfoil_Driver:
    """Thin adapter entry point for future NeuralFoil integration."""

    def __init__(self, model_size: str = "large"):
        self.model_size = model_size

    def prediction_to_dataset(
        self,
        prediction: dict[str, float | np.ndarray],
        alpha: float | np.ndarray,
        re: float | np.ndarray,
        ncrit: float | np.ndarray,
        ma: float = 0.0,
        polar_type: str = "T1",
        xtript: float | None = None,
        xtripb: float | None = None,
        airfoil_name: str | None = None,
    ) -> Polar_Data_Set:
        """Convert NeuralFoil prediction output to PolarDataSet DTO."""

        return Neuralfoil_Polar_Adapter.to_polar_dataset(
            prediction=prediction,
            alpha=alpha,
            re=re,
            ncrit=ncrit,
            ma=ma,
            polar_type=polar_type,
            xtript=xtript,
            xtripb=xtripb,
            airfoil_name=airfoil_name,
        )

    def predict(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Placeholder API for upcoming integration work."""
        raise NotImplementedError("Neuralfoil_Driver.predict is not implemented yet")
