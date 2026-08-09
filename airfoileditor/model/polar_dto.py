#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Typed DTOs for backend-agnostic polar data exchange.

This module defines neutral data contracts used between solver-specific loaders
(e.g. XFOIL, NeuralFoil) and the domain model in polar_set.

It intentionally has no dependency on Polar, Polar_Point, Worker, or UI code.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Polar_File_Meta:
    """Metadata parsed or computed for a polar dataset."""

    source: Literal["xfoil", "neuralfoil"] | None = None
    airfoil_name: str | None = None
    polar_type: str | None = None
    re: float | None = None
    ma: float | None = None
    ncrit: float | None = None
    xtript: float | None = None
    xtripb: float | None = None
    flap_angle: float | None = None
    x_flap: float | None = None
    y_flap: float | None = None
    y_flap_spec: str | None = None
    spec_var: str | None = None
    val_range: tuple[float, float, float] | None = None
    auto_range: bool | None = None
    xf_source_path: str | None = None       # xfoil: path of the parsed polar file
    nf_model_size: str | None = None        # neuralfoil: model size used for evaluation


@dataclass(frozen=True)
class Polar_Bubble_Range:
    """Separated bubble chord range [x_start, x_end] on a surface."""

    x_start: float
    x_end: float


@dataclass(frozen=True)
class Polar_Data_Row:
    """A single operating point row of a polar dataset."""

    alpha: float
    cl: float
    cd: float
    cdp: float | None
    cm: float
    xtrt: float
    xtrb: float
    xf_cp_min: float | None = None                    # xfoil: minimum pressure coefficient
    xf_bubble_top: Polar_Bubble_Range | None = None   # xfoil: laminar bubble top side
    xf_bubble_bot: Polar_Bubble_Range | None = None   # xfoil: laminar bubble bot side
    nf_confidence: float | None = None                # neuralfoil: prediction confidence [0..1]


@dataclass(frozen=True)
class Polar_Data_Set:
    """Complete polar payload independent of solver backend."""

    meta: Polar_File_Meta
    rows: list[Polar_Data_Row]
