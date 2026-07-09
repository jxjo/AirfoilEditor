#!/usr/bin/env python
# -*- coding: utf-8 -*-

import numpy as np

from airfoileditor.model.geometry import Line


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
