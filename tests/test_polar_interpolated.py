import unittest
from types import SimpleNamespace

import numpy as np

from airfoileditor.model.polar_set import Polar, Polar_Interpolated, _compute_pre_stall_branch, var



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
        polar._pre_stall_branch = _compute_pre_stall_branch(polar)
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


    def test_post_stall_cl_collapse_does_not_break_pre_stall_branch_detection(self):
        """A real polar's cl commonly crashes below its low-alpha cl once deep into post-
        stall - the global argmin(cl) must not be mis-picked from that region, which would
        put index_min after index_max and wrongly reject an otherwise valid polar."""
        alpha = np.array([-4, -2, 0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20], dtype=float)
        cl_realistic = np.array([-.2, .0, .2, .4, .6, .8, 1.0, 1.1, .9, .3, -.3, -.6, -.9])
        left = self.make_polar(alpha, cl_realistic)
        right = self.make_polar(alpha, cl_realistic)

        polar = Polar_Interpolated(left, right, .132, .04, .08)

        self.assertAlmostEqual(polar.cl_max, 1.1)


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


    def test_ofVars_returns_direct_properties(self):
        polar = self.interpolate(.5)
        x, y = polar.ofVars((var.ALPHA, var.CD))
        np.testing.assert_allclose(x, polar.alpha)
        np.testing.assert_allclose(y, polar.cd)

    def test_ofVars_computes_derived_glide_and_sink(self):
        polar = self.interpolate(.5)
        glide = polar._ofVar(var.GLIDE)
        np.testing.assert_allclose(glide, polar.cl / polar.cd)
        sink = polar._ofVar(var.SINK)
        valid = (polar.cd > 0.0) & (polar.cl >= 0.0)
        np.testing.assert_allclose(sink[valid], np.abs(polar.cl[valid]) ** 1.5 / polar.cd[valid])

    def test_ofVar_unknown_variable_returns_empty_array(self):
        polar = self.interpolate(.5)
        np.testing.assert_array_equal(polar._ofVar(var.NF_CONFIDENCE), np.array([]))

    def test_is_loaded_and_error_free_so_it_can_nest_as_a_polar_like_input(self):
        """A Polar_Interpolated must itself satisfy the Polar_Interpolated constructor's
        sanity check (isLoaded), so bracket-interpolated results can be chord-interpolated
        again (e.g. T2's per-section Re-bracket feeding the spanwise chord blend)."""
        polar = self.interpolate(.5)
        self.assertTrue(polar.isLoaded)
        self.assertFalse(polar.error_occurred)
        self.assertIsNone(polar.error_reason)

        nested = Polar_Interpolated(polar, self.right, .5, 1.0, .75)
        self.assertTrue(nested.isLoaded)


    def test_raises_a_clear_error_for_a_non_finite_bracket_value(self):
        """A NaN bracket value always originates further upstream (e.g. a NaN cl feeding
        a Re-from-cl calculation) - it must fail fast here with an actionable message,
        not propagate into alpha/cl and fail deep inside _build_alpha_mapping instead."""
        for value_left, value_right, value_target in (
                (float("nan"), .04, .06), (.132, float("nan"), .06), (.132, .04, float("nan"))):
            with self.subTest(left=value_left, right=value_right, target=value_target):
                with self.assertRaises(ValueError):
                    Polar_Interpolated(self.left, self.right, value_left, value_right, value_target)



class TestFromGrid(unittest.TestCase):

    @staticmethod
    def make_grid_polar(re, scale):
        alpha = [-6, -5, -2, 0, 6, 11.2, 12.1]
        cl = (scale * np.array([-.4, -.5, 0, .2, .8, 1.24336, 1.2])).tolist()
        polar = TestPolarInterpolated.make_polar(alpha, cl)
        polar.re = re
        return polar

    def setUp(self):
        self.grid = [self.make_grid_polar(re, scale) for re, scale in (
            (100_000, 1.0), (200_000, 1.1), (400_000, 1.2), (800_000, 1.3))]

    def test_raises_with_fewer_than_two_polars(self):
        with self.assertRaises(ValueError):
            Polar_Interpolated.from_grid([self.grid[0]], 150_000)

    def test_exposes_the_chosen_bracket_polars(self):
        polar = Polar_Interpolated.from_grid(self.grid, 300_000)
        self.assertIs(polar.polar_left, self.grid[1])
        self.assertIs(polar.polar_right, self.grid[2])

    def test_exact_grid_point_matches_that_polar_unblended(self):
        polar = Polar_Interpolated.from_grid(self.grid, 200_000)
        self.assertFalse(polar.clamped)
        self.assertAlmostEqual(polar.cl_max, self.grid[1].cl.max())

    def test_between_grid_points_uses_log_fraction_of_the_correct_bracket(self):
        polar = Polar_Interpolated.from_grid(self.grid, 300_000)
        self.assertFalse(polar.clamped)
        fraction_log = (np.log(300_000) - np.log(200_000)) / (np.log(400_000) - np.log(200_000))
        expected_cl_max = (self.grid[1].cl.max()
                           + fraction_log * (self.grid[2].cl.max() - self.grid[1].cl.max()))
        self.assertAlmostEqual(polar.cl_max, expected_cl_max, places=6)

    def test_below_range_clamps_to_lowest_polar(self):
        polar = Polar_Interpolated.from_grid(self.grid, 10_000)
        self.assertTrue(polar.clamped)
        self.assertAlmostEqual(polar.cl_max, self.grid[0].cl.max())

    def test_above_range_clamps_to_highest_polar(self):
        polar = Polar_Interpolated.from_grid(self.grid, 5_000_000)
        self.assertTrue(polar.clamped)
        self.assertAlmostEqual(polar.cl_max, self.grid[-1].cl.max())

    def test_unsorted_input_still_resolves_correctly(self):
        shuffled = [self.grid[2], self.grid[0], self.grid[3], self.grid[1]]
        polar = Polar_Interpolated.from_grid(shuffled, 200_000)
        self.assertFalse(polar.clamped)
        self.assertAlmostEqual(polar.cl_max, self.grid[1].cl.max())
