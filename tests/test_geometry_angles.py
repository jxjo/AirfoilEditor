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

    def test_repanel_near_corner_moves_neighbor_on_local_spline(self):
        side_x = np.array([0.00, 0.10, 0.149, 0.1500, 0.1510, 0.20, 0.30], dtype=float)
        side_y = np.array([0.00, 0.10, 0.149, 0.1500, 0.1510, 0.18, 0.30], dtype=float)
        x_corner = 0.1505
        y_corner = 0.1505

        x_new, y_new = Flap_Setter._repanel_near_corner(side_x.copy(), side_y.copy(), x_corner, y_corner)

        idx = np.searchsorted(x_new, x_corner)
        left_idx = max(0, idx - 1)
        right_idx = min(len(x_new) - 1, idx)

        assert np.isclose(x_new[left_idx], side_x[left_idx], atol=1e-12)
        assert x_new[right_idx] != side_x[right_idx]

        local_i0 = max(0, right_idx - 2)
        local_i1 = min(len(x_new), right_idx + 3)
        spline = Spline1D(x_new[local_i0:local_i1], y_new[local_i0:local_i1], boundary='natural')

        assert np.isclose(y_new[right_idx], spline.eval(x_new[right_idx]), atol=1e-8)
