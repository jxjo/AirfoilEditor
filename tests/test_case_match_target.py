#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    pytest classes for Case_Match_Target and Match_Targets
"""

import pytest
import os

from airfoileditor.model.case        import Case_Match_Target, Match_Targets
from airfoileditor.model.airfoil     import Airfoil, Airfoil_Bezier, Airfoil_BSpline, GEO_SPLINE
from airfoileditor.model.airfoil_examples import Root_Example
from airfoileditor.model.airfoil_geometry import Line


@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def seed_airfoil(temp_dir) -> Airfoil:
    """A real .dat airfoil saved to a temp dir, used as the target to match"""
    airfoil = Root_Example(geometry=GEO_SPLINE)
    airfoil_path = airfoil.saveAs(dir=str(temp_dir), destName="test_seed")
    airfoil_copied = Airfoil(pathFileName=airfoil_path, workingDir=str(temp_dir))
    airfoil_copied.load()
    return airfoil_copied


# ─────────────────────────────────────────────────────────────────────────────


class Test_Match_Targets:
    """Tests for the Match_Targets helper class"""

    def test_from_airfoil_invalid_airfoil(self, seed_airfoil):
        """from_airfoil raises ValueError when not given an Airfoil"""
        with pytest.raises(ValueError):
            Match_Targets.from_airfoil("not_an_airfoil", Line.Type.UPPER, ncp=6)

    def test_from_airfoil_invalid_side(self, seed_airfoil):
        """from_airfoil raises ValueError for an unsupported side type"""
        with pytest.raises(ValueError):
            Match_Targets.from_airfoil(seed_airfoil, "INVALID", ncp=6)

    def test_from_airfoil_upper(self, seed_airfoil):
        """Creates Match_Targets for the upper side"""
        mt = Match_Targets.from_airfoil(seed_airfoil, Line.Type.UPPER, ncp=6)

        assert mt is not None
        assert mt.ncp == 6
        assert mt.side is not None
        assert mt.le_curvature is not None
        assert mt.le_curvature > 0

    def test_from_airfoil_lower(self, seed_airfoil):
        """Creates Match_Targets for the lower side"""
        mt = Match_Targets.from_airfoil(seed_airfoil, Line.Type.LOWER, ncp=6)

        assert mt is not None
        assert mt.ncp == 6
        assert mt.side is not None

    def test_default_flags(self, seed_airfoil):
        """ncp_auto and min_rms are True by default"""
        mt = Match_Targets.from_airfoil(seed_airfoil, Line.Type.UPPER, ncp=6)

        assert mt.ncp_auto is True
        assert mt.min_rms  is True

    def test_set_ncp(self, seed_airfoil):
        """set_ncp updates the ncp value"""
        mt = Match_Targets.from_airfoil(seed_airfoil, Line.Type.UPPER, ncp=6)
        mt.set_ncp(9)
        assert mt.ncp == 9

    def test_set_le_curvature(self, seed_airfoil):
        """set_le_curvature updates the stored value"""
        mt = Match_Targets.from_airfoil(seed_airfoil, Line.Type.UPPER, ncp=6)
        mt.set_le_curvature(12.5)
        assert mt.le_curvature == pytest.approx(12.5)

    def test_set_max_te_curvature(self, seed_airfoil):
        """set_max_te_curvature overrides the computed value"""
        mt = Match_Targets.from_airfoil(seed_airfoil, Line.Type.UPPER, ncp=6)
        mt.set_max_te_curvature(0.5)
        assert mt.max_te_curvature == pytest.approx(0.5)

    def test_set_max_nreversals_updates_te_curvature(self, seed_airfoil):
        """Setting max_nreversals=0 forces a low max_te_curvature; =1 allows a higher value"""
        mt = Match_Targets.from_airfoil(seed_airfoil, Line.Type.UPPER, ncp=6)

        mt.set_max_nreversals(0)
        te_curv_zero = mt.max_te_curvature

        mt.set_max_nreversals(1)
        te_curv_one = mt.max_te_curvature

        # With no allowed reversals, TE curvature must be tightly constrained (capped at 1.0)
        assert te_curv_zero <= 1.0
        # With one allowed reversal, the limit is relaxed (sentinel value -2.0 means unconstrained)
        assert te_curv_one < te_curv_zero


# ─────────────────────────────────────────────────────────────────────────────


class Test_Case_Match_Target:
    """Tests for Case_Match_Target creation and core properties"""

    def test_invalid_class_raises(self, seed_airfoil):
        """Passing an unsupported airfoil class raises ValueError"""
        with pytest.raises(ValueError):
            Case_Match_Target(seed_airfoil, Airfoil)

    def test_bezier_creation(self, seed_airfoil):
        """Case_Match_Target can be created with Airfoil_Bezier"""
        case = Case_Match_Target(seed_airfoil, Airfoil_Bezier)
        assert case is not None

    def test_bspline_creation(self, seed_airfoil):
        """Case_Match_Target can be created with Airfoil_BSpline"""
        case = Case_Match_Target(seed_airfoil, Airfoil_BSpline)
        assert case is not None

    def test_design_dir_created(self, seed_airfoil):
        """A fresh design directory is created on init"""
        case = Case_Match_Target(seed_airfoil, Airfoil_Bezier)
        assert os.path.isdir(case.design_dir_abs)

    def test_one_initial_design(self, seed_airfoil):
        """Exactly one initial design is present after creation"""
        case = Case_Match_Target(seed_airfoil, Airfoil_Bezier)
        assert len(case.airfoil_designs) == 1

    def test_targets_created(self, seed_airfoil):
        """Both targets_upper and targets_lower are set"""
        case = Case_Match_Target(seed_airfoil, Airfoil_Bezier)

        assert case.targets_upper is not None
        assert case.targets_lower is not None

    def test_targets_are_match_targets(self, seed_airfoil):
        """targets_upper and targets_lower are Match_Targets instances"""
        case = Case_Match_Target(seed_airfoil, Airfoil_Bezier)

        assert isinstance(case.targets_upper, Match_Targets)
        assert isinstance(case.targets_lower, Match_Targets)

    def test_bezier_initial_ncp(self, seed_airfoil):
        """Bezier case starts with ncp=6 in both targets"""
        case = Case_Match_Target(seed_airfoil, Airfoil_Bezier)

        assert case.targets_upper.ncp == 6
        assert case.targets_lower.ncp == 6

    def test_bspline_initial_ncp(self, seed_airfoil):
        """BSpline case starts with ncp=8 in both targets"""
        case = Case_Match_Target(seed_airfoil, Airfoil_BSpline)

        assert case.targets_upper.ncp == 8
        assert case.targets_lower.ncp == 8

    def test_targets_le_curvature_positive(self, seed_airfoil):
        """le_curvature is a positive value derived from the target airfoil"""
        case = Case_Match_Target(seed_airfoil, Airfoil_Bezier)

        assert case.targets_upper.le_curvature > 0
        assert case.targets_lower.le_curvature > 0

    def test_initial_airfoil_design_returns_copy(self, seed_airfoil):
        """initial_airfoil_design returns a usable Airfoil copy"""
        case = Case_Match_Target(seed_airfoil, Airfoil_Bezier)
        design = case.initial_airfoil_design()

        assert design is not None
        assert isinstance(design, Airfoil)
        # Must not be the same object as the stored design
        assert design is not case.airfoil_designs[0]

    def test_initial_airfoil_design_is_bezier(self, seed_airfoil):
        """initial_airfoil_design for Bezier case is an Airfoil_Bezier"""
        case = Case_Match_Target(seed_airfoil, Airfoil_Bezier)
        design = case.initial_airfoil_design()

        assert isinstance(design, Airfoil_Bezier)

    def test_initial_airfoil_design_is_bspline(self, seed_airfoil):
        """initial_airfoil_design for BSpline case is an Airfoil_BSpline"""
        case = Case_Match_Target(seed_airfoil, Airfoil_BSpline)
        design = case.initial_airfoil_design()

        assert isinstance(design, Airfoil_BSpline)


# ─────────────────────────────────────────────────────────────────────────────


class Test_Case_Match_Target_AddDesign:
    """Tests for add_design ncp-synchronisation logic"""

    def test_add_design_keeps_design_count(self, seed_airfoil, temp_dir):
        """Adding a design increments the stored design list"""
        case = Case_Match_Target(seed_airfoil, Airfoil_Bezier)
        initial_design = case.initial_airfoil_design()
        count_before = len(case.airfoil_designs)

        case.add_design(initial_design)

        assert len(case.airfoil_designs) == count_before + 1

    def test_add_design_syncs_targets_ncp(self, seed_airfoil, temp_dir):
        """After add_design the targets ncp reflects the design ncp"""
        case = Case_Match_Target(seed_airfoil, Airfoil_Bezier)
        design = case.initial_airfoil_design()

        # Manually override targets to a different value, then re-add the design
        case.targets_upper.set_ncp(99)
        case.targets_lower.set_ncp(99)

        case.add_design(design)

        # Targets must now match the actual design ncp again
        geo = design.geo
        assert case.targets_upper.ncp == geo.upper.ncp
        assert case.targets_lower.ncp == geo.lower.ncp


# ─────────────────────────────────────────────────────────────────────────────


class Test_Case_Match_Target_GetFinal:
    """Tests for get_final_from_design in Case_Match_Target"""

    def test_get_final_not_edited(self, seed_airfoil):
        """Final airfoil has isEdited=False"""
        case   = Case_Match_Target(seed_airfoil, Airfoil_Bezier)
        design = case.initial_airfoil_design()

        final = case.get_final_from_design(design)

        assert not final.isEdited

    def test_get_final_uses_seed_name(self, seed_airfoil):
        """Final airfoil name contains the seed name and the Bezier suffix"""
        case   = Case_Match_Target(seed_airfoil, Airfoil_Bezier)
        design = case.initial_airfoil_design()

        final = case.get_final_from_design(design)

        assert seed_airfoil.name in final.name
        assert Airfoil_Bezier.NAME_SUFFIX in final.name

    def test_get_final_bspline_uses_seed_name(self, seed_airfoil):
        """Final BSpline airfoil name contains the seed name and the BSpline suffix"""
        case   = Case_Match_Target(seed_airfoil, Airfoil_BSpline)
        design = case.initial_airfoil_design()

        final = case.get_final_from_design(design)

        assert seed_airfoil.name in final.name
        assert Airfoil_BSpline.NAME_SUFFIX in final.name

    def test_get_final_path_points_to_seed(self, seed_airfoil):
        """Final airfoil pathName points back to the seed airfoil location"""
        case   = Case_Match_Target(seed_airfoil, Airfoil_Bezier)
        design = case.initial_airfoil_design()

        final = case.get_final_from_design(design)

        assert final.pathName == seed_airfoil.pathName
