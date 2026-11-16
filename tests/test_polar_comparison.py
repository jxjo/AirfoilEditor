#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""  
Tests of the deviation (delta) of a polar to a reference polar - Polar.deviation_from  
"""

import numpy as np
import pytest

from airfoileditor.model.polar_set import Polar, Polar_Comparison, var
from airfoileditor.ui.ae_artists import Polar_Delta_Artist


def _polar (alpha_stall_max=9.0, alpha_stall_min=-8.0, d_alpha=0.25, cd_scale=1.0, dip=False, steep_spot=False) -> Polar:
    """ synthetic polar: linear lift cl = s * (alpha + 1.5) which rounds off to its peak 3 degrees before the stall angles 
    (the slope goes linearly to zero) and falls back behind - like cl_max and cl_min of a real polar """

    s     = 0.11
    alpha = np.arange (-12.0, 14.0, d_alpha)

    cl = s * (alpha + 1.5)
    cl = cl - s / 6.0 * np.clip (alpha - (alpha_stall_max - 3.0), 0.0, None)**2         # upper stall 
    cl = cl + s / 6.0 * np.clip ((alpha_stall_min + 3.0) - alpha, 0.0, None)**2         # lower stall

    if dip:                                                             # slope dip in the middle - e.g. bubble
        cl = cl - 0.08 * np.exp (-((alpha - 3.0) / 0.8)**2)

    if steep_spot:                                                      # local steep spot - like a kink in a real polar
        cl = cl + 0.07 * np.tanh ((alpha + 3.0) / 0.4)

    cd = (0.008 + 0.0003 * (alpha - 2.0)**2) * cd_scale

    polar = Polar (None)
    polar._values = {var.ALPHA: alpha, var.CL: cl, var.CD: cd, var.CM: -0.05 + 0 * alpha}
    polar._values[var.GLIDE] = np.where ((cd > 0) & (cl != 0), cl / cd, 0.0)
    return polar


def _threshold (polar : Polar) -> float:
    """ lift slope below which the range is cut: fraction of the median slope of the branch cl_min .. cl_max """

    alpha, cl = polar._ofVar (var.ALPHA), polar._ofVar (var.CL)
    slope = np.gradient (cl, alpha)
    i_max = int (np.argmax (cl))
    i_min = int (np.argmin (cl[:i_max + 1]))

    return Polar_Comparison.MIN_SLOPE_FRACTION * np.median (slope[i_min:i_max + 1])


def _finite (x, delta):
    ok = np.isfinite (delta)
    return x[ok]


def _cut (polar : Polar, alpha_from=-100.0, alpha_to=100.0) -> Polar:
    """ copy of polar with only the samples in the alpha range - e.g. a polar which ends before stall """

    alpha = polar._ofVar (var.ALPHA)
    keep  = (alpha >= alpha_from) & (alpha <= alpha_to)

    cut = Polar (None)
    cut._values = {key: values[keep] for key, values in polar._values.items ()}
    return cut


class Test_Polar_Comparison:

    def test_cl_range_ends_before_cl_max (self):

        cur, ref = _polar (), _polar (cd_scale=1.05)

        x, delta, _ = cur.deviation_from (ref, (var.CL, var.CD))
        x_ok = _finite (x, delta)

        cl_max = cur._ofVar (var.CL).max ()
        assert x_ok.max () < cl_max - 0.01                              # delta stops before the rounding off to stall


    def test_valid_range_slope_criterion (self):

        polar = _polar ()
        mask = Polar_Comparison._valid_cl_range (polar)

        alpha = polar._ofVar (var.ALPHA)
        cl    = polar._ofVar (var.CL)
        slope = np.gradient (cl, alpha)
        threshold = _threshold (polar)

        # inside the range: slope is high enough at the ends - the sample behind is cut
        idx = np.flatnonzero (mask)
        assert slope[idx[0]]  >= threshold - 1e-9
        assert slope[idx[-1]] >= threshold - 1e-9
        assert slope[idx[-1] + 1] < threshold                            # next sample is cut
        assert idx[-1] < np.argmax (cl)                                  # cut before cl_max
        assert idx[0] > 0 and idx[0] > np.argmin (cl)                    # cut at the negative stall too


    def test_steep_spot_does_not_move_the_cut (self):
        """ a local steep spot gives a high maximum slope - the median based range is not affected """

        normal = _polar ()
        spot   = _polar (steep_spot=True)

        slope_spot = np.gradient (spot._ofVar (var.CL), spot._ofVar (var.ALPHA))
        assert slope_spot.max () > 1.4 * np.median (slope_spot)          # the spot is there

        idx_normal = np.flatnonzero (Polar_Comparison._valid_cl_range (normal))
        idx_spot   = np.flatnonzero (Polar_Comparison._valid_cl_range (spot))

        assert abs (idx_spot[-1] - idx_normal[-1]) <= 1                  # same end at stall (+/- one sample)


    def test_both_polars_limit_the_range (self):

        early_stall = _polar (alpha_stall_max=7.0)
        late_stall  = _polar (alpha_stall_max=10.0)

        x1, d1, _ = early_stall.deviation_from (late_stall, (var.CL, var.CD))
        x2, d2, _ = late_stall.deviation_from (early_stall, (var.CL, var.CD))

        # same end of the delta whichever is the current or reference polar
        assert _finite (x1, d1).max () == pytest.approx (_finite (x2, d2).max (), abs=0.03)
        assert _finite (x1, d1).max () < early_stall._ofVar (var.CL).max ()


    def test_all_value_variables_use_the_same_range (self):

        cur, ref = _polar (), _polar (cd_scale=1.05)
        ends = []
        for value_var in (var.CD, var.GLIDE, var.CM):
            x, delta, _ = cur.deviation_from (ref, (var.CL, value_var))
            ends.append (_finite (x, delta).max ())
        assert ends[0] == pytest.approx (ends[1]) and ends[0] == pytest.approx (ends[2])


    def test_slope_dip_in_the_middle_is_not_cut (self):

        polar = _polar (dip=True)
        mask = Polar_Comparison._valid_cl_range (polar)

        alpha = polar._ofVar (var.ALPHA)
        slope = np.gradient (polar._ofVar (var.CL), alpha)
        threshold = _threshold (polar)

        idx = np.flatnonzero (mask)
        assert mask[idx[0]:idx[-1] + 1].all ()                           # one contiguous range 
        assert alpha[idx[0]] < 0.0 and alpha[idx[-1]] > 5.0              # range spans over the dip
        assert (slope[idx] < threshold).any ()                           # ... which has a slope below the threshold


    def test_alpha_base_compares_the_whole_range (self):

        cur, ref = _polar (), _polar (cd_scale=1.05)

        x, delta, _ = cur.deviation_from (ref, (var.ALPHA, var.CD))

        assert np.isfinite (delta).all ()
        assert len (x) == len (cur._ofVar (var.ALPHA))


    def test_few_samples_are_not_cut (self):

        polar = Polar (None)
        polar._values = {var.ALPHA: np.array ([0.0, 1.0]), var.CL: np.array ([0.1, 0.2])}

        assert Polar_Comparison._valid_cl_range (polar).all ()


    def test_empty_polar (self):

        polar = Polar (None)

        assert Polar_Comparison._valid_cl_range (polar).size == 0
        x, delta, _ = polar.deviation_from (_polar (), (var.CL, var.CD))
        assert x.size == 0 and delta.size == 0

