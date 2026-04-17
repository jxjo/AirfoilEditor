#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    pytest classes for Match_Airfoil, Match_Result and the Matcher workers.
"""

import pytest

from airfoileditor.match_runner         import Match_Airfoil, Match_Result, Matcher_Bezier, Matcher_BSpline
from airfoileditor.model.airfoil        import Airfoil, Airfoil_Bezier, Airfoil_BSpline
from airfoileditor.model.airfoil_examples import Root_Example, Tip_Example
from airfoileditor.model.geometry_spline import Geometry_Splined
from airfoileditor.model.case           import Match_Targets
from airfoileditor.model.geometry import Line
from airfoileditor.base.widgets         import style


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def seed_airfoil(qapp):
    """A normalised spline airfoil used as the matching target."""
    return Root_Example(geometry=Geometry_Splined)


@pytest.fixture(scope="module")
def match_airfoil_bezier(qapp, seed_airfoil) -> Match_Airfoil:
    """Match_Airfoil configured for Bezier (no optimisation run)."""
    return Match_Airfoil(seed_airfoil, Airfoil_Bezier)


@pytest.fixture(scope="module")
def match_airfoil_bspline(qapp, seed_airfoil) -> Match_Airfoil:
    """Match_Airfoil configured for BSpline (no optimisation run)."""
    return Match_Airfoil(seed_airfoil, Airfoil_BSpline)


# ── Match_Result ──────────────────────────────────────────────────────────────


class Test_Match_Result:
    """Tests for the Match_Result data class."""

    def test_rms_is_float(self, match_airfoil_bezier: Match_Airfoil):
        result = match_airfoil_bezier.get_result_upper()
        assert isinstance(result.rms, float)

    def test_ncp_matches_curve(self, match_airfoil_bezier: Match_Airfoil):
        result = match_airfoil_bezier.get_result_upper()
        assert result.ncp == match_airfoil_bezier.airfoil.geo.upper.ncp

    def test_le_curvature_positive(self, match_airfoil_bezier: Match_Airfoil):
        result = match_airfoil_bezier.get_result_upper()
        assert result.le_curvature > 0

    def test_max_dy_and_position(self, match_airfoil_bezier: Match_Airfoil):
        result = match_airfoil_bezier.get_result_upper()
        assert result.max_dy is not None
        assert result.max_dy_position is not None
        assert 0.0 <= result.max_dy_position <= 1.0

    def test_nreversals_is_int(self, match_airfoil_bezier: Match_Airfoil):
        result = match_airfoil_bezier.get_result_upper()
        assert isinstance(result.nreversals, int)
        assert result.nreversals >= 0

    def test_style_properties_are_style_enum(self, match_airfoil_bezier: Match_Airfoil):
        result = match_airfoil_bezier.get_result_upper()
        assert result.style_deviation   in (style.GOOD, style.NORMAL, style.WARNING)
        assert result.style_curv_le     in (style.GOOD, style.NORMAL, style.WARNING)
        assert result.style_curv_te     in (style.GOOD, style.NORMAL, style.WARNING)
        assert result.style_max_dy      in (style.GOOD, style.NORMAL, style.WARNING)
        assert result.style_nreversals  in (style.GOOD, style.NORMAL, style.WARNING)

    def test_is_good_enough_bool(self, match_airfoil_bezier: Match_Airfoil):
        result = match_airfoil_bezier.get_result_upper()
        assert isinstance(result.is_good_enough(), bool)

    def test_side_and_targets_accessible(self, match_airfoil_bezier: Match_Airfoil):
        result = match_airfoil_bezier.get_result_upper()
        assert result.side    is not None
        assert result.targets is not None
        assert isinstance(result.targets, Match_Targets)

    def test_upper_and_lower_give_different_results(self, match_airfoil_bezier: Match_Airfoil):
        upper = match_airfoil_bezier.get_result_upper()
        lower = match_airfoil_bezier.get_result_lower()
        # Upper and lower sides have different geometry, so rms won't be identical
        assert upper.side is not lower.side


# ── Match_Airfoil – initialisation ───────────────────────────────────────────


class Test_Match_Airfoil_Init:
    """Tests for Match_Airfoil construction and basic properties."""

    def test_invalid_class_raises(self, qapp, seed_airfoil):
        """Passing a plain Airfoil class must raise ValueError."""
        with pytest.raises(ValueError):
            Match_Airfoil(seed_airfoil, Airfoil)

    def test_creates_bezier_airfoil(self, match_airfoil_bezier: Match_Airfoil):
        assert isinstance(match_airfoil_bezier.airfoil, Airfoil_Bezier)

    def test_creates_bspline_airfoil(self, match_airfoil_bspline: Match_Airfoil):
        assert isinstance(match_airfoil_bspline.airfoil, Airfoil_BSpline)

    def test_airfoil_target_is_normalized(self, match_airfoil_bezier: Match_Airfoil):
        assert match_airfoil_bezier.airfoil_target.isNormalized

    def test_bezier_default_ncp(self, match_airfoil_bezier: Match_Airfoil):
        """Bezier uses 6 control points by default."""
        assert match_airfoil_bezier.targets_upper.ncp == 6
        assert match_airfoil_bezier.targets_lower.ncp == 6

    def test_bspline_default_ncp(self, match_airfoil_bspline: Match_Airfoil):
        """BSpline uses 8 control points by default."""
        assert match_airfoil_bspline.targets_upper.ncp == 8
        assert match_airfoil_bspline.targets_lower.ncp == 8

    def test_targets_upper_is_match_targets(self, match_airfoil_bezier: Match_Airfoil):
        assert isinstance(match_airfoil_bezier.targets_upper, Match_Targets)

    def test_targets_lower_is_match_targets(self, match_airfoil_bezier: Match_Airfoil):
        assert isinstance(match_airfoil_bezier.targets_lower, Match_Targets)

    def test_targets_le_curvature_positive(self, match_airfoil_bezier: Match_Airfoil):
        assert match_airfoil_bezier.targets_upper.le_curvature > 0
        assert match_airfoil_bezier.targets_lower.le_curvature > 0

    def test_initial_result_has_positive_rms(self, match_airfoil_bezier: Match_Airfoil):
        """Before optimisation the initial curve deviates from the target."""
        upper = match_airfoil_bezier.get_result_upper()
        lower = match_airfoil_bezier.get_result_lower()
        assert upper.rms > 0
        assert lower.rms > 0


# ── Match_Airfoil – interrupt ─────────────────────────────────────────────────


class Test_Match_Airfoil_Interrupt:
    """Tests for the interrupt() mechanism."""

    def test_interrupt_does_not_raise(self, qapp, seed_airfoil):
        """interrupt() must be callable without raising an exception."""
        ma = Match_Airfoil(seed_airfoil, Airfoil_Bezier)
        ma.interrupt()  # should not raise

    def test_interrupted_flag_false_before_run(self, qapp, seed_airfoil):
        """_interrupted flag starts False before any match has been executed."""
        ma = Match_Airfoil(seed_airfoil, Airfoil_Bezier)
        assert ma._interrupted is False

    def test_requestInterruption_callable_on_matchers(self, qapp, seed_airfoil):
        """requestInterruption() can be called on each matcher without error."""
        ma = Match_Airfoil(seed_airfoil, Airfoil_Bezier)
        ma._matcher_upper.requestInterruption()
        ma._matcher_lower.requestInterruption()


# ── Match_Airfoil – optimisation (slow) ───────────────────────────────────────


class Test_Match_Airfoil_Sequential:
    """End-to-end matching tests – marked slow because the optimiser is involved."""

    @pytest.mark.slow
    def test_do_match_sequential_bezier_returns_true(self, qapp, seed_airfoil):
        """Successful sequential match for Bezier returns True."""
        ma = Match_Airfoil(seed_airfoil, Airfoil_Bezier)
        success = ma.do_match_sequential()
        assert success is True

    @pytest.mark.slow
    def test_do_match_sequential_improves_rms(self, qapp, seed_airfoil):
        """Upper-side RMS must improve after matching."""
        ma = Match_Airfoil(seed_airfoil, Airfoil_Bezier)
        rms_before = ma.get_result_upper().rms
        ma.do_match_sequential()
        rms_after = ma.get_result_upper().rms
        assert rms_after < rms_before

    @pytest.mark.slow
    def test_do_match_sequential_bspline_returns_true(self, qapp, seed_airfoil):
        """Successful sequential match for BSpline returns True."""
        ma = Match_Airfoil(seed_airfoil, Airfoil_BSpline)
        success = ma.do_match_sequential()
        assert success is True

    @pytest.mark.slow
    def test_matched_airfoil_result_is_good_enough(self, qapp, seed_airfoil):
        """After matching, the result should qualify as good enough."""
        ma = Match_Airfoil(seed_airfoil, Airfoil_Bezier)
        ma.do_match_sequential()
        assert ma.get_result_upper().is_good_enough()
        assert ma.get_result_lower().is_good_enough()
