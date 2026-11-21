import unittest
from types import SimpleNamespace

import numpy as np

from airfoileditor.model.polar_set import Polar, Polar_Interpolated, var



class TestPolarInterpolated(unittest.TestCase):

    def setUp(self):
        self.left = self.make_polar(
            [-6, -5, -2, 0, 6, 11.2, 12.1], [-.4, -.5, 0, .2, .8, 1.24336, 1.2])
        self.right = self.make_polar(
            [-5.3, -4, -1, 0, 5, 9.1, 10], [-.3, -.4, 0, .1, .7, 1.05033, 1.0])


    @staticmethod
    def make_polar(alpha, cl):
        alpha = np.asarray(alpha, dtype=float)
        polar = SimpleNamespace(
            isLoaded=True, alpha=alpha, cl=np.asarray(cl, dtype=float),
            cd=.02 + .001 * alpha, cm=-.05 + .002 * alpha)
        polar._values = {var.ALPHA: polar.alpha, var.CL: polar.cl,
                         var.CD: polar.cd, var.CM: polar.cm}
        polar._ofVar = lambda polar_var: Polar._ofVar(polar, polar_var)
        return polar


    def interpolate(self, fraction):
        value = .132 if fraction == 0 else .04 if fraction == 1 else (
            np.exp((1 - fraction) * np.log(.132) + fraction * np.log(.04)))
        return Polar_Interpolated(self.left, self.right, .132, .04, value)


    def test_lift_extrema_are_aligned(self):
        for fraction in (0.0, .0565, .5, 1.0):
            with self.subTest(fraction=fraction):
                polar = self.interpolate(fraction)
                self.assertAlmostEqual(polar.cl_max, (1 - fraction) * 1.24336 + fraction * 1.05033)
                self.assertAlmostEqual(polar.alpha_max, (1 - fraction) * 11.2 + fraction * 9.1)
                self.assertAlmostEqual(polar.cl_min, (1 - fraction) * -.5 + fraction * -.4)
                self.assertAlmostEqual(polar.alpha[0], (1 - fraction) * -5 + fraction * -4)
                self.assertTrue(np.all(np.diff(polar.alpha) > 0))


    def test_endpoints_recover_source_pre_stall_curves(self):
        for fraction, source in ((0.0, self.left), (1.0, self.right)):
            with self.subTest(fraction=fraction):
                polar = self.interpolate(fraction)
                pre_stall = slice(np.argmin(source.cl), np.argmax(source.cl) + 1)
                source_alpha = source.alpha[pre_stall]
                self.assertAlmostEqual(polar.alpha[0], source_alpha[0])
                self.assertAlmostEqual(polar.alpha[-1], source_alpha[-1])
                for polar_var in (var.CL, var.CD, var.CM):
                    np.testing.assert_allclose(
                        np.interp(source_alpha, polar.alpha, getattr(polar, polar_var.value)),
                        source._ofVar(polar_var)[pre_stall], atol=1e-14)


    def test_zero_lift_is_derived_from_blended_curve(self):
        polar = self.interpolate(.5)
        self.assertAlmostEqual(polar.alpha0, np.interp(0.0, polar.cl, polar.alpha))


    def test_lazy_coefficients_use_corresponding_source_alpha(self):
        polar = self.interpolate(.5)

        cm_left = np.interp(polar._alpha_left, self.left.alpha, self.left.cm)
        cm_right = np.interp(polar._alpha_right, self.right.alpha, self.right.cm)
        expected_cm = (cm_left + polar._fraction * (cm_right - cm_left))
        np.testing.assert_allclose(polar.cm, expected_cm)

        cd_left = np.interp(polar._alpha_left, self.left.alpha, self.left.cd)
        cd_right = np.interp(polar._alpha_right, self.right.alpha, self.right.cd)
        expected_cd = (cd_left + polar._fraction_log * (cd_right - cd_left))
        np.testing.assert_allclose(polar.cd, expected_cd)


    def test_missing_zero_crossing_and_tail_do_not_discard_peaks(self):
        self.left = self.make_polar([0, 5, 10], [.2, .8, 1.3])
        self.right = self.make_polar([1, 4, 8, 9], [.1, .6, 1.0, .9])
        polar = self.interpolate(.5)
        self.assertAlmostEqual(polar.cl_max, 1.15)
        self.assertAlmostEqual(polar.alpha_max, 9.0)
        self.assertTrue(np.all(np.diff(polar.alpha) > 0))
