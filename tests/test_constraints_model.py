#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Model tests for GeoConstraint_Definition and Nml_constraints."""

import io

import numpy as np
import pytest
import airfoileditor.model.xo2_input as xo2_input_module

from airfoileditor.model.xo2_input import Input_File, GeoConstraint_Definition


@pytest.fixture
def input_file(tmp_path):
    """Create a fresh temporary input file model."""
    return Input_File(fileName="tmp_case.xo2", workingDir=str(tmp_path), is_new=True)


class Test_GeoConstraints_Model:

    def test_obsolete_unquoted_description_has_no_special_fallback(self, tmp_path, monkeypatch):
        path = tmp_path / "legacy_description.xo2"
        path.write_text(
            "&info\n"
            "  description = Optimize min cd legacy text without quotes\n"
            "  description(1) = 'Line 1'\n"
            "  description(2) = 'Line 2'\n"
            "/\n",
            encoding="utf-8",
        )

        fallback2_calls = {"count": 0}

        def _reads_should_not_be_used(*args, **kwargs):
            fallback2_calls["count"] += 1
            raise AssertionError("f90nml.reads fallback should not be used")

        monkeypatch.setattr(xo2_input_module.f90nml, "reads", _reads_should_not_be_used)

        model = Input_File(fileName=path.name, workingDir=str(tmp_path), is_new=False)

        assert fallback2_calls["count"] == 0
        assert model.pop_migration_warnings() == []

    def test_invalid_namelist_file_does_not_crash_on_init(self, tmp_path):
        bad_file = tmp_path / "bad_case.xo2"
        bad_file.write_text("&constraints\nmin_thickness_at_x = (0.5, 0.0677)\n", encoding="utf-8")

        model = Input_File(fileName=bad_file.name, workingDir=str(tmp_path), is_new=False)

        assert model.has_parse_error is True
        assert model.parse_error_text is not None
        assert model.nml_file is not None

    def test_issue_messages_reports_categories(self, input_file):
        input_file.add_migration_warning("legacy setting was skipped")

        issues = input_file.get_issue_messages()

        assert issues["errors"] == []
        assert issues["warnings"] == ["legacy setting was skipped"]

    def test_property_returns_same_instance(self, input_file):
        constraints = input_file.nml_constraints

        c1 = constraints.max_thickness
        c2 = constraints.max_thickness

        assert isinstance(c1, GeoConstraint_Definition)
        assert c1 is c2

    def test_is_min_is_max_flags(self, input_file):
        constraints = input_file.nml_constraints

        assert constraints.min_thickness.is_min is True
        assert constraints.min_thickness.is_max is False

        assert constraints.max_thickness.is_max is True
        assert constraints.max_thickness.is_min is False

    def test_max_thickness_uses_seed_effective_lower_limit(self, input_file):
        constraints = input_file.nml_constraints
        seed_thickness = input_file.airfoil_seed.geo.max_thick

        con = constraints.max_thickness
        lo, hi = con.effective_limits

        assert lo == pytest.approx(max(0.001, seed_thickness + con.SEED_SAFETY_EPSILON))
        assert hi == pytest.approx(0.30)

        con.set_value(0.001)
        assert con.value >= lo - 1e-6

    def test_set_is_active_uses_seed_default_value(self, input_file):
        constraints = input_file.nml_constraints

        con = constraints.max_thickness
        assert con.value is None

        con.set_is_active(True)

        assert con.value is not None
        lo, hi = con.effective_limits
        assert lo - 1e-6 <= con.value <= hi + 1e-6

    def test_min_thickness_at_x_applies_tuple_limits(self, input_file):
        constraints = input_file.nml_constraints

        con = constraints.min_thickness_at_x
        con.set_value((0.5, 0.30))

        x_lim, t_lim = con.effective_limits

        assert x_lim == (0.0, 1.0)
        assert t_lim is not None
        assert con.value is not None
        assert con.value[0] == pytest.approx(0.5)
        t_lo = min(t_lim[0], t_lim[1])
        t_hi = max(t_lim[0], t_lim[1])
        assert t_lo - 1e-4 <= con.value[1] <= t_hi + 1e-4

    def test_min_thickness_at_x_can_be_activated(self, input_file):
        constraints = input_file.nml_constraints

        con = constraints.min_thickness_at_x
        assert con.is_active is False

        con.set_is_active(True)

        assert con.is_active is True
        assert con.value is not None
        assert isinstance(con.value, tuple)
        assert len(con.value) == 2

    def test_min_thickness_at_x_seed_value_is_scalar(self, input_file):
        constraints = input_file.nml_constraints

        con = constraints.min_thickness_at_x
        assert isinstance(con.seed_value, (int, float))

        default_val = con.default
        assert isinstance(default_val, tuple)
        assert len(default_val) == 2

    def test_min_thickness_at_x_value_x_returns_scalar_fallback(self, input_file):
        constraints = input_file.nml_constraints

        con = constraints.min_thickness_at_x
        con.set_value(None)

        assert isinstance(con.value_x, (int, float))
        assert con.value_x == pytest.approx(0.5)

    def test_min_thickness_at_x_reclips_t_when_x_changes(self, input_file):
        constraints = input_file.nml_constraints

        con = constraints.min_thickness_at_x
        con.set_value((0.4, 0.30))
        old_t = con.value_t

        con.set_value_x(0.95)

        _, t_lim = con.effective_limits
        assert t_lim is not None
        assert con.value_t is not None

        expected_t = max(t_lim[0], min(old_t, t_lim[1]))
        expected_t = round(expected_t, 4)
        assert con.value_t == pytest.approx(expected_t)

    def test_disabled_rules_follow_symmetry_only(self, input_file):
        constraints = input_file.nml_constraints

        assert constraints.min_thickness.disabled is False
        assert constraints.min_camber.disabled is False
        assert constraints.min_te_top_angle.disabled is False
        assert constraints.max_te_bot_angle.disabled is False

        constraints.set_symmetrical(True)

        assert constraints.min_thickness.disabled is False
        assert constraints.min_te_angle.disabled is False
        assert constraints.min_camber.disabled is True
        assert constraints.max_camber.disabled is True
        assert constraints.min_te_top_angle.disabled is True
        assert constraints.max_te_bot_angle.disabled is True

    def test_is_active_is_false_while_disabled(self, input_file):
        constraints = input_file.nml_constraints
        con = constraints.min_camber

        con.set_is_active(True)
        assert con.value is not None
        assert con.is_active is True

        constraints.set_symmetrical(True)
        assert con.disabled is True
        assert con.is_active is False

        constraints.set_symmetrical(False)
        assert con.disabled is False
        assert con.is_active is True

    def test_check_geometry_is_derived_from_active_constraints(self, input_file):
        constraints = input_file.nml_constraints

        assert constraints.check_geometry is False

        constraints.max_thickness.set_is_active(True)
        assert constraints.check_geometry is True

        constraints.max_thickness.set_is_active(False)
        assert constraints.check_geometry is False

    def test_set_check_geometry_false_clears_all_constraints(self, input_file):
        constraints = input_file.nml_constraints

        constraints.max_thickness.set_is_active(True)
        constraints.min_te_angle.set_is_active(True)
        assert constraints.check_geometry is True

        constraints.set_check_geometry(False)

        assert constraints.max_thickness.value is None
        assert constraints.min_te_angle.value is None
        assert constraints.check_geometry is False

    def test_symmetrical_is_independent_of_check_geometry(self, input_file):
        constraints = input_file.nml_constraints

        constraints.set_symmetrical(True)
        assert constraints.symmetrical is True

        constraints.max_thickness.set_is_active(True)
        assert constraints.check_geometry is True
        assert constraints.symmetrical is True

    def test_write_syncs_check_geometry_entry(self, input_file):
        constraints = input_file.nml_constraints

        constraints._set('check_geometry', True)
        constraints.max_thickness.set_is_active(False)

        stream = io.StringIO()
        constraints.write_to_stream(stream)

        assert constraints.nml.get('check_geometry') is False

    def test_tuple_constraint_serializes_without_tuple_error(self, input_file):
        constraints = input_file.nml_constraints

        constraints.min_thickness_at_x.set_value((0.5, np.float64(0.06771604074845575)))

        # Must not raise ValueError from f90nml tuple conversion.
        rendered = str(input_file._nml_file_dict)
        assert isinstance(rendered, str)
        assert rendered

    def test_constraint_values_are_rounded_by_semantics(self, input_file):
        constraints = input_file.nml_constraints

        constraints.min_thickness.set_value(0.085082)
        lo, hi = constraints.min_thickness.effective_limits
        expected = round(max(lo, min(0.085082, hi)), 4)
        assert constraints.min_thickness.value == pytest.approx(expected)

        constraints.min_camber.set_value(0.015817)
        assert constraints.min_camber.value == pytest.approx(0.0158)

        constraints.min_te_angle.set_value(4.409858)
        assert constraints.min_te_angle.value == pytest.approx(4.41)

        constraints.min_thickness_at_x.set_value((0.5, 0.06771604074845575))
        _, t_lim = constraints.min_thickness_at_x.effective_limits
        t_lo = min(t_lim[0], t_lim[1])
        t_hi = max(t_lim[0], t_lim[1])
        expected_t = round(max(t_lo, min(0.06771604074845575, t_hi)), 4)
        assert constraints.min_thickness_at_x.value_t == pytest.approx(expected_t)

    def test_te_side_angles_keep_one_degree_safety_gap_when_setting_top(self, input_file):
        constraints = input_file.nml_constraints

        constraints.max_te_bot_angle.set_value(2.0)
        constraints.min_te_top_angle.set_value(2.4)

        assert constraints.min_te_top_angle.value == pytest.approx(3.0)
        assert constraints.min_te_top_angle.value >= constraints.max_te_bot_angle.value + 1.0 - 1e-6

    def test_te_side_angles_keep_one_degree_safety_gap_when_setting_bottom(self, input_file):
        constraints = input_file.nml_constraints

        constraints.min_te_top_angle.set_value(5.0)
        constraints.max_te_bot_angle.set_value(4.8)

        assert constraints.max_te_bot_angle.value == pytest.approx(4.0)
        assert constraints.min_te_top_angle.value >= constraints.max_te_bot_angle.value + 1.0 - 1e-6
