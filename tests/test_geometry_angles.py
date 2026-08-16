#!/usr/bin/env python
# -*- coding: utf-8 -*-

import numpy as np

from airfoileditor.model.geometry import Flap_Setter, Line
from airfoileditor.base.spline import Spline1D


class Test_Line_Angle_In_Range:
    def test_falling_tangent_is_positive(self):
        x = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        y = -2.0 * x + 1.0
        line = Line(x, y)

        angle = line.angle_in_range(x_range = (0.0, 1.0))

        assert np.isclose(angle, 63.4349488, atol=1e-6)

    def test_rising_tangent_is_negative(self):
        x = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        y = 2.0 * x
        line = Line(x, y)

        angle = line.angle_in_range(x_range = (0.0, 1.0))

        assert np.isclose(angle, -63.4349488, atol=1e-6)

    def test_not_enough_points_returns_zero(self):
        x = np.array([0.0, 0.5, 1.0])
        y = np.array([0.0, 0.1, 0.0])
        line = Line(x, y)

        angle = line.angle_in_range(x_range = (0.9, 1.0))

        assert np.isclose(angle, 11.30993247, atol=1e-6)

    def test_degenerate_regression_returns_zero(self):
        x = np.array([0.0, 0.0, 1.0])
        y = np.array([0.0, 1.0, 2.0])
        line = Line(x, y)

        angle = line.angle_in_range(x_range = (0.0, 0.0))

        assert angle == 0.0

    def test_yFn_splined_matches_exact_curved_value(self):
        x = np.array([0.0, 0.2, 0.5, 0.8, 1.0])
        y = np.array([0.0, 0.04, 0.25, 0.64, 1.0])
        line = Line(x, y)

        y_at = line.yFn(0.5, splined=True)

        assert np.isclose(y_at, 0.25, atol=1e-6)
        assert np.isclose(Line.yFn_splined(0.5, x, y), 0.25, atol=1e-6)

    def test_repanel_near_corner_is_post_flap_sensitive(self):
        x_corner = 0.1505
        y_corner = 0.1505
        beta = 4.0

        pre_flap_x = np.array([0.00, 0.10, 0.13, 0.30, 0.50, 0.70, 0.90], dtype=float)
        pre_flap_y = np.array([0.00, 0.10, 0.13, 0.30, 0.50, 0.70, 0.90], dtype=float)

        post_flap_x = pre_flap_x.copy()
        post_flap_y = pre_flap_y.copy()
        post_flap_x[3] = 0.1540
        post_flap_y[3] = 0.1540

        x_corner_found, y_corner_found = Flap_Setter._find_concave_corner(
            pre_flap_x, pre_flap_y, x_corner, y_corner, beta
        )

        pre_x_new, pre_y_new = Flap_Setter._process_concave_side(
            pre_flap_x.copy(), pre_flap_y.copy(), x_corner, y_corner, beta
        )
        post_x_new, post_y_new = Flap_Setter._process_concave_side(
            post_flap_x.copy(), post_flap_y.copy(), x_corner, y_corner, beta
        )

        pre_corner_idx = np.flatnonzero(np.isclose(pre_x_new, x_corner_found, atol=1e-12, rtol=0.0))
        post_corner_idx = np.flatnonzero(np.isclose(post_x_new, x_corner_found, atol=1e-12, rtol=0.0))

        assert pre_corner_idx.size == 1
        assert post_corner_idx.size == 1
        assert np.isclose(pre_y_new[pre_corner_idx[0]], y_corner_found, atol=1e-12)
        assert np.isclose(post_y_new[post_corner_idx[0]], y_corner_found, atol=1e-12)
        assert not np.allclose(post_x_new, pre_x_new)
        assert not np.allclose(post_y_new, pre_y_new)
        assert post_corner_idx[0] + 1 < len(post_x_new)
        assert abs(post_x_new[post_corner_idx[0] + 1] - x_corner_found) < abs(pre_x_new[pre_corner_idx[0] + 1] - x_corner_found)
