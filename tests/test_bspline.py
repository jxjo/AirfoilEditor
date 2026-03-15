#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""

    BSpline pytest classes

"""

import numpy as np
import pytest
from airfoileditor.base.spline import *


class Test_BSpline:

    def setup_method(self):
        self.spl = BSpline([0.0, 0.2, 0.65, 1.0], [0.0, 0.18, 0.08, 0.0], degree=3)

    def test_eval_clamped_endpoints(self):
        """Clamped B-Spline interpolates its first and last control points."""
        x0, y0 = self.spl.eval(0.0)
        xn, yn = self.spl.eval(1.0)

        np.testing.assert_allclose([x0, y0], [0.0, 0.0], atol=1e-10)
        np.testing.assert_allclose([xn, yn], [1.0, 0.0], atol=1e-10)

    def test_eval_scalar_vs_array(self):
        """eval() returns identical values for scalar and array inputs."""
        u = np.linspace(0.0, 1.0, 21)
        x_arr, y_arr = self.spl.eval(u, update_cache=False)

        x_scalar = np.array([self.spl.eval(ui, update_cache=False)[0] for ui in u])
        y_scalar = np.array([self.spl.eval(ui, update_cache=False)[1] for ui in u])

        np.testing.assert_allclose(x_arr, x_scalar, atol=1e-10)
        np.testing.assert_allclose(y_arr, y_scalar, atol=1e-10)

    def test_eval_derivatives_finite_difference(self):
        """First and second derivatives from eval() agree with central finite differences."""
        h = 1e-6
        u = np.array([0.2, 0.4, 0.6, 0.8])

        x_fwd, y_fwd = self.spl.eval(u + h, update_cache=False)
        x_bwd, y_bwd = self.spl.eval(u - h, update_cache=False)
        dx_fd = (x_fwd - x_bwd) / (2 * h)
        dy_fd = (y_fwd - y_bwd) / (2 * h)

        dx, dy = self.spl.eval(u, der=1, update_cache=False)
        np.testing.assert_allclose(dx, dx_fd, rtol=1e-4)
        np.testing.assert_allclose(dy, dy_fd, rtol=1e-4)

        # Second derivative via finite difference on first derivative
        dx_fwd, dy_fwd = self.spl.eval(u + h, der=1, update_cache=False)
        dx_bwd, dy_bwd = self.spl.eval(u - h, der=1, update_cache=False)
        ddx_fd = (dx_fwd - dx_bwd) / (2 * h)
        ddy_fd = (dy_fwd - dy_bwd) / (2 * h)

        ddx, ddy = self.spl.eval(u, der=2, update_cache=False)
        np.testing.assert_allclose(ddx, ddx_fd, rtol=1e-4)
        np.testing.assert_allclose(ddy, ddy_fd, rtol=1e-4)

    def test_curvature_consistent_with_derivatives(self):
        """curvature() matches the standard formula applied to eval() derivatives."""
        u = np.linspace(0.1, 0.9, 9)

        dx,  dy  = self.spl.eval(u, der=1, update_cache=False)
        ddx, ddy = self.spl.eval(u, der=2, update_cache=False)

        kappa_expected = (dx * ddy - dy * ddx) / (dx**2 + dy**2)**1.5
        kappa = self.spl.curvature(u)

        np.testing.assert_allclose(kappa, kappa_expected, atol=1e-10)

    def test_set_cpoint_invalidates_cache(self):
        """set_cpoint() changes the curve shape and clears cached evaluations."""
        u = np.linspace(0.0, 1.0, 21)
        _, y_before = self.spl.eval(u)

        self.spl.set_cpoint(1, (0.25, 0.22))
        _, y_after = self.spl.eval(u)

        assert not np.allclose(y_before, y_after), "Curve shape must change after set_cpoint"

        # Clamped endpoints must still hold after the update
        x0, y0 = self.spl.eval(0.0)
        xn, yn = self.spl.eval(1.0)
        np.testing.assert_allclose([x0, y0], [0.0, 0.0], atol=1e-10)
        np.testing.assert_allclose([xn, yn], [1.0, 0.0], atol=1e-10)


class Test_BSpline_Degree4:

    def setup_method(self):
        # 6 control points required for degree 4
        self.spl = BSpline(
            [0.0, 0.1, 0.3, 0.6, 0.85, 1.0],
            [0.0, 0.12, 0.20, 0.15, 0.05, 0.0],
            degree=4)

    def test_eval_clamped_endpoints(self):
        """Degree-4 clamped B-Spline interpolates first and last control points."""
        x0, y0 = self.spl.eval(0.0)
        xn, yn = self.spl.eval(1.0)

        np.testing.assert_allclose([x0, y0], [0.0, 0.0], atol=1e-10)
        np.testing.assert_allclose([xn, yn], [1.0, 0.0], atol=1e-10)

    def test_eval_derivatives_finite_difference(self):
        """Degree-4: first and second derivatives agree with central finite differences."""
        h = 1e-6
        u = np.array([0.2, 0.4, 0.6, 0.8])

        x_fwd, y_fwd = self.spl.eval(u + h, update_cache=False)
        x_bwd, y_bwd = self.spl.eval(u - h, update_cache=False)
        dx_fd = (x_fwd - x_bwd) / (2 * h)
        dy_fd = (y_fwd - y_bwd) / (2 * h)

        dx, dy = self.spl.eval(u, der=1, update_cache=False)
        np.testing.assert_allclose(dx, dx_fd, rtol=5e-4)
        np.testing.assert_allclose(dy, dy_fd, rtol=5e-4)

        dx_fwd, dy_fwd = self.spl.eval(u + h, der=1, update_cache=False)
        dx_bwd, dy_bwd = self.spl.eval(u - h, der=1, update_cache=False)
        ddx_fd = (dx_fwd - dx_bwd) / (2 * h)
        ddy_fd = (dy_fwd - dy_bwd) / (2 * h)

        ddx, ddy = self.spl.eval(u, der=2, update_cache=False)
        np.testing.assert_allclose(ddx, ddx_fd, rtol=5e-4)
        np.testing.assert_allclose(ddy, ddy_fd, rtol=5e-4)

    def test_curvature_consistent_with_derivatives(self):
        """Degree-4: curvature() matches the standard formula applied to eval() derivatives."""
        u = np.linspace(0.1, 0.9, 9)

        dx,  dy  = self.spl.eval(u, der=1, update_cache=False)
        ddx, ddy = self.spl.eval(u, der=2, update_cache=False)

        kappa_expected = (dx * ddy - dy * ddx) / (dx**2 + dy**2)**1.5
        kappa = self.spl.curvature(u)

        np.testing.assert_allclose(kappa, kappa_expected, atol=1e-10)


class Test_BSpline_InsertKnot:

    def setup_method(self):
        self.spl = BSpline([0.0, 0.2, 0.65, 1.0], [0.0, 0.18, 0.08, 0.0], degree=3)

    def test_insert_knot_preserves_curve(self):
        """insert_knot() adds a control point without changing the curve shape."""
        u = np.linspace(0.0, 1.0, 51)
        x_before, y_before = self.spl.eval(u, update_cache=False)
        ncp_before = self.spl.ncp

        self.spl.insert_knot(0.4)

        x_after, y_after = self.spl.eval(u, update_cache=False)

        assert self.spl.ncp == ncp_before + 1
        np.testing.assert_allclose(x_after, x_before, atol=1e-8)
        np.testing.assert_allclose(y_after, y_before, atol=1e-8)

    def test_insert_knot_preserves_endpoints(self):
        """insert_knot() keeps clamped endpoints intact."""
        self.spl.insert_knot(0.6)

        x0, y0 = self.spl.eval(0.0)
        xn, yn = self.spl.eval(1.0)
        np.testing.assert_allclose([x0, y0], [0.0, 0.0], atol=1e-10)
        np.testing.assert_allclose([xn, yn], [1.0, 0.0], atol=1e-10)

    def test_insert_knot_multiple(self):
        """Multiple knot insertions all preserve the curve shape."""
        u = np.linspace(0.0, 1.0, 51)
        x_before, y_before = self.spl.eval(u, update_cache=False)

        for x in [0.25, 0.5, 0.75]:
            self.spl.insert_knot(x)

        x_after, y_after = self.spl.eval(u, update_cache=False)
        np.testing.assert_allclose(x_after, x_before, atol=1e-8)
        np.testing.assert_allclose(y_after, y_before, atol=1e-8)


class Test_BSpline_RemoveCpoint:

    def setup_method(self):
        # Start with 6 control points so we have room to remove one
        self.spl = BSpline(
            [0.0, 0.15, 0.35, 0.60, 0.82, 1.0],
            [0.0, 0.14, 0.18, 0.12, 0.04, 0.0],
            degree=3)

    def test_remove_cpoint_reduces_count(self):
        """remove_cpoint() decreases the control point count by one."""
        ncp_before = self.spl.ncp
        self.spl.remove_cpoint(2)
        assert self.spl.ncp == ncp_before - 1

    def test_remove_cpoint_preserves_endpoints(self):
        """remove_cpoint() keeps clamped endpoints intact."""
        self.spl.remove_cpoint(2)

        x0, y0 = self.spl.eval(0.0)
        xn, yn = self.spl.eval(1.0)
        np.testing.assert_allclose([x0, y0], [0.0, 0.0], atol=1e-10)
        np.testing.assert_allclose([xn, yn], [1.0, 0.0], atol=1e-10)

    def test_remove_cpoint_raises_on_too_few(self):
        """remove_cpoint() raises ValueError when below minimum control points."""
        spl = BSpline([0.0, 0.3, 0.7, 1.0], [0.0, 0.15, 0.08, 0.0], degree=3)
        with pytest.raises(ValueError):
            spl.remove_cpoint(1)
