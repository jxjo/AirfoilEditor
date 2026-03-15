#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""

    Bezier pytest classes

"""

import numpy as np 
from airfoileditor.base.spline import *

class Test_Bezier:

    def setup_method(self):
        # Cubic Bezier (degree 3, 4 control points)
        self.bez = Bezier([0.0, 0.0, 0.6, 1.0], [0.0, 0.15, 0.12, 0.0])

    def test_eval_endpoints(self):
        """Bezier curve starts and ends exactly at the first and last control points."""
        x0, y0 = self.bez.eval(0.0)
        xn, yn = self.bez.eval(1.0)

        np.testing.assert_allclose([x0, y0], [0.0, 0.0], atol=1e-10)
        np.testing.assert_allclose([xn, yn], [1.0, 0.0], atol=1e-10)

    def test_eval_scalar_vs_array(self):
        """eval() returns identical values for scalar and array inputs."""
        u = np.linspace(0.0, 1.0, 21)
        x_arr, y_arr = self.bez.eval(u)

        x_scalar = np.array([self.bez.eval(ui)[0] for ui in u])
        y_scalar = np.array([self.bez.eval(ui)[1] for ui in u])

        np.testing.assert_allclose(x_arr, x_scalar, atol=1e-10)
        np.testing.assert_allclose(y_arr, y_scalar, atol=1e-10)

    def test_eval_derivatives_finite_difference(self):
        """First and second derivatives from eval() agree with central finite differences."""
        h = 1e-6
        u = np.array([0.2, 0.4, 0.6, 0.8])

        x_fwd, y_fwd = self.bez.eval(u + h)
        x_bwd, y_bwd = self.bez.eval(u - h)
        dx_fd = (x_fwd - x_bwd) / (2 * h)
        dy_fd = (y_fwd - y_bwd) / (2 * h)

        dx, dy = self.bez.eval(u, der=1)
        np.testing.assert_allclose(dx, dx_fd, rtol=1e-4)
        np.testing.assert_allclose(dy, dy_fd, rtol=1e-4)

        dx_fwd, dy_fwd = self.bez.eval(u + h, der=1)
        dx_bwd, dy_bwd = self.bez.eval(u - h, der=1)
        ddx_fd = (dx_fwd - dx_bwd) / (2 * h)
        ddy_fd = (dy_fwd - dy_bwd) / (2 * h)

        ddx, ddy = self.bez.eval(u, der=2)
        np.testing.assert_allclose(ddx, ddx_fd, rtol=1e-4)
        np.testing.assert_allclose(ddy, ddy_fd, rtol=1e-4)

    def test_curvature_consistent_with_derivatives(self):
        """curvature() matches the standard formula applied to eval() derivatives."""
        u = np.linspace(0.1, 0.9, 9)

        dx,  dy  = self.bez.eval(u, der=1)
        ddx, ddy = self.bez.eval(u, der=2)

        kappa_expected = (dx * ddy - dy * ddx) / (dx**2 + dy**2)**1.5
        kappa = self.bez.curvature(u)

        np.testing.assert_allclose(kappa, kappa_expected, atol=1e-10)

    def test_set_cpoint_invalidates_cache(self):
        """set_cpoint() changes the curve shape and clears cached evaluations."""
        u = np.linspace(0.0, 1.0, 21)
        _, y_before = self.bez.eval(u)

        self.bez.set_cpoint(2, (0.5, 0.20))
        _, y_after = self.bez.eval(u)

        assert not np.allclose(y_before, y_after), "Curve shape must change after set_cpoint"

        # Endpoints must still hold after the update
        x0, y0 = self.bez.eval(0.0)
        xn, yn = self.bez.eval(1.0)
        np.testing.assert_allclose([x0, y0], [0.0, 0.0], atol=1e-10)
        np.testing.assert_allclose([xn, yn], [1.0, 0.0], atol=1e-10)

    def test_elevate_degree_preserves_shape(self):
        """elevate_degree() increases ncp by 1 but keeps the curve identical."""
        u = np.linspace(0.0, 1.0, 51)
        x_before, y_before = self.bez.eval(u)
        ncp_before = self.bez.ncp

        self.bez.elevate_degree()

        assert self.bez.ncp == ncp_before + 1
        x_after, y_after = self.bez.eval(u)
        np.testing.assert_allclose(x_after, x_before, atol=1e-10)
        np.testing.assert_allclose(y_after, y_before, atol=1e-10)
