#!/usr/bin/env python
# -*- coding: utf-8 -*-

import numpy as np
import pytest

from airfoileditor.model.nf_driver import Airfoil_As_CST, Neuralfoil_Evaluator
from airfoileditor.model.polar_dto import Polar_File_Meta


def test_T2_secant_solves_cl_at_fixed_target_reynolds(monkeypatch):
    calls = []

    def predict(**kwargs):
        alpha = kwargs["alpha"]
        reynolds = kwargs["Re"]
        calls.append((alpha.copy(), reynolds.copy()))
        lift = 0.2 + 0.1 * alpha + 0.000001 * reynolds
        return {"CL": lift, "CD": 0.01 + lift ** 2 * 0.02,
                "panels": np.column_stack((lift, lift))}

    monkeypatch.setattr("airfoileditor.model.nf_driver.get_aero_from_kulfan_parameters", predict)
    meta = Polar_File_Meta(polar_type="T2", spec_var="cl", re=100000,
                           val_range=(0.1, 1.0, 0.1), auto_range=False)

    alpha, result = Neuralfoil_Evaluator._predict_T2({}, meta, "xlarge")

    target = np.arange(0.1, 1.05, 0.1)
    np.testing.assert_allclose(result["CL"], target, atol=Neuralfoil_Evaluator.T2_CL_TOLERANCE)
    np.testing.assert_allclose(result["CL"], 0.2 + 0.1 * alpha + 0.1 / np.sqrt(target))
    assert result["panels"].shape == (len(target), 2)
    expected_reynolds = meta.re / np.sqrt(target)
    for alpha_call, reynolds in calls:
        assert alpha_call.shape == reynolds.shape
        assert len(alpha_call) in (1, 2)
        np.testing.assert_array_equal(reynolds, np.full(len(alpha_call), reynolds[0]))
        assert np.any(np.isclose(reynolds[0], expected_reynolds))
    for index, reynolds in enumerate(expected_reynolds):
        point_calls = [alpha_call for alpha_call, re_call in calls
                       if np.isclose(re_call[0], reynolds)]
        expected_pair = [0.0, 2.0] if index == 0 else [alpha[index - 1],
                         alpha[index - 1] + Neuralfoil_Evaluator.T2_SEED_ALPHA_STEP]
        np.testing.assert_allclose(point_calls[0], expected_pair)
        assert all(len(alpha_call) == 1 for alpha_call in point_calls[1:])
        assert len(point_calls) >= 2


@pytest.mark.parametrize("val_range", [(0.0, 1.0, 0.1), (-0.1, 1.0, 0.1),
                                      (0.1, 1.0, 0.0), (1.0, 0.1, 0.1)])
def test_T2_rejects_invalid_cl_ranges(val_range):
    meta = Polar_File_Meta(polar_type="T2", spec_var="cl", re=100000,
                           val_range=val_range, auto_range=False)

    with pytest.raises(RuntimeError, match="positive cl range"):
        Neuralfoil_Evaluator._predict_T2({}, meta, "xlarge")


@pytest.mark.parametrize("val_range, step", [(None, Neuralfoil_Evaluator.CL_AUTO_STEP),
                                             ((0.4, 0.9, 0.2), 0.2)])
def test_T2_auto_range_uses_driver_bounds_and_configured_step(monkeypatch, val_range, step):
    targets = []

    def solve(cls, kulfan_parameters, meta, model_size, cl_target, alpha_guess=None,
              seed_alpha_step=None):
        targets.append(cl_target)
        return cl_target * 10.0, {"CL": np.array([cl_target])}

    monkeypatch.setattr(Neuralfoil_Evaluator, "_solve_T2_point", classmethod(solve))
    meta = Polar_File_Meta(polar_type="T2", spec_var="cl", re=100000,
                           val_range=val_range, auto_range=True)

    Neuralfoil_Evaluator._predict_T2({}, meta, "xlarge")

    auto_min = 1.0 / Neuralfoil_Evaluator.T2_AUTO_RE_FACTOR ** 2
    expected = np.arange(auto_min,
                         Neuralfoil_Evaluator.CL_AUTO_MAX + step * 0.5, step)
    expected = expected[expected <= Neuralfoil_Evaluator.CL_AUTO_MAX + 1e-12]
    np.testing.assert_allclose(targets, expected)
    assert targets[0] == pytest.approx(0.01)
    assert meta.re / np.sqrt(targets[0]) == pytest.approx (
        Neuralfoil_Evaluator.T2_AUTO_RE_FACTOR * meta.re)


def test_T2_omits_unreachable_lift_and_keeps_prediction_arrays_aligned(monkeypatch):
    def predict(**kwargs):
        lift = np.tanh(0.1 * kwargs["alpha"])
        return {"CL": lift, "CD": 0.01 + lift ** 2,
                "panels": np.column_stack((lift, lift)), "constant": 1.0}

    monkeypatch.setattr("airfoileditor.model.nf_driver.get_aero_from_kulfan_parameters", predict)
    meta = Polar_File_Meta(polar_type="T2", spec_var="cl", re=100000,
                           val_range=(0.5, 1.5, 0.5), auto_range=False)

    alpha, result = Neuralfoil_Evaluator._predict_T2({}, meta, "xlarge")

    assert result["CL"][0] == pytest.approx(0.5, abs=Neuralfoil_Evaluator.T2_CL_TOLERANCE)
    assert result["CL"][-1] > 0.9
    assert result["CL"][-1] <= np.tanh(2.0) + Neuralfoil_Evaluator.T2_CL_TOLERANCE
    assert np.all(np.diff(result["CL"]) > 0.0)
    np.testing.assert_allclose(result["CL"], np.tanh(0.1 * alpha))
    np.testing.assert_allclose(result["panels"], np.column_stack((result["CL"], result["CL"])))
    assert result["constant"] == 1.0


@pytest.mark.parametrize("curve", ["flat", "falling", "nonfinite"])
def test_T2_rejects_non_rising_or_nonfinite_lift_curve(monkeypatch, curve):
    def predict(**kwargs):
        alpha = kwargs["alpha"]
        if curve == "falling":
            return {"CL": 0.7 - 0.1 * alpha}
        return {"CL": np.full(len(alpha), np.nan if curve == "nonfinite" else 0.5)}

    monkeypatch.setattr("airfoileditor.model.nf_driver.get_aero_from_kulfan_parameters", predict)
    meta = Polar_File_Meta(polar_type="T2", spec_var="cl", re=100000,
                           val_range=(0.5, 1.0, 0.5), auto_range=False)

    with pytest.raises(RuntimeError, match="first point"):
        Neuralfoil_Evaluator._predict_T2({}, meta, "xlarge")


def test_T2_point_solver_accepts_alpha_guess_and_keeps_target_reynolds(monkeypatch):
    calls = []

    def predict(**kwargs):
        calls.append((kwargs["alpha"].copy(), kwargs["Re"].copy()))
        return {"CL": 0.2 + 0.1 * kwargs["alpha"]}

    monkeypatch.setattr("airfoileditor.model.nf_driver.get_aero_from_kulfan_parameters", predict)
    meta = Polar_File_Meta(re=100000, ncrit=7.0)

    solution = Neuralfoil_Evaluator._solve_T2_point({}, meta, "xlarge", 0.7, alpha_guess=4.0,
                                                    seed_alpha_step=0.25)

    assert solution is not None
    alpha, prediction = solution
    assert alpha == pytest.approx(5.0)
    assert prediction["CL"].item() == pytest.approx(0.7)
    np.testing.assert_array_equal(calls[0][0], [4.0, 4.25])
    for angle, reynolds in calls:
        np.testing.assert_allclose(reynolds, meta.re / np.sqrt(0.7))


@pytest.mark.parametrize("step", [0.1, 0.01, 0.005])
def test_T2_first_failure_stops_coarse_sweep_and_refines_without_retries(monkeypatch, step):
    calls = []

    seed_steps = []

    def solve(cls, kulfan_parameters, meta, model_size, cl_target, alpha_guess=None,
              seed_alpha_step=None):
        calls.append((cl_target, alpha_guess))
        seed_steps.append(seed_alpha_step)
        if cl_target > 0.135 + 1e-12:
            return None
        return cl_target * 10, {"CL": np.array([cl_target]),
                               "panels": np.array([[cl_target, cl_target]]), "constant": 1.0}

    monkeypatch.setattr(Neuralfoil_Evaluator, "_solve_T2_point", classmethod(solve))
    meta = Polar_File_Meta(polar_type="T2", spec_var="cl", re=100000,
                           val_range=(0.1, 0.3, step), auto_range=False)

    alpha, prediction = Neuralfoil_Evaluator._predict_T2({}, meta, "xlarge")

    if step == 0.1:
        np.testing.assert_allclose([target for target, guess in calls],
                                   [0.1, 0.2, 0.11, 0.12, 0.13, 0.14])
        np.testing.assert_allclose([guess for target, guess in calls[1:]],
                                   [1.0, 1.0, 1.1, 1.2, 1.3])
        assert seed_steps == [None, None, 0.05, 0.05, 0.05, 0.05]
    else:
        np.testing.assert_allclose([target for target, guess in calls],
                                   np.arange(0.1, 0.14 + step * 0.5, step))
    assert calls[0][1] is None
    assert len({round(target, 8) for target, guess in calls}) == len(calls)
    expected_targets = np.arange(0.1, 0.135 + min(0.01, step) * 0.5, min(0.01, step))
    expected_targets = expected_targets[expected_targets <= 0.135 + 1e-12]
    np.testing.assert_allclose(prediction["CL"], expected_targets)
    np.testing.assert_allclose(alpha, np.array(expected_targets) * 10)
    np.testing.assert_allclose(prediction["panels"], np.column_stack((expected_targets, expected_targets)))
    assert prediction["constant"] == 1.0


def test_T2_first_point_failure_does_not_start_refinement(monkeypatch):
    calls = []

    def solve(cls, kulfan_parameters, meta, model_size, cl_target, alpha_guess=None):
        calls.append(cl_target)
        return None

    monkeypatch.setattr(Neuralfoil_Evaluator, "_solve_T2_point", classmethod(solve))
    meta = Polar_File_Meta(polar_type="T2", spec_var="cl", re=100000,
                           val_range=(0.1, 0.3, 0.1), auto_range=False)

    with pytest.raises(RuntimeError, match="first point"):
        Neuralfoil_Evaluator._predict_T2({}, meta, "xlarge")
    assert calls == [0.1]


def test_T2_explicit_upper_bound_does_not_trigger_refinement(monkeypatch):
    calls = []

    def solve(cls, kulfan_parameters, meta, model_size, cl_target, alpha_guess=None):
        calls.append(cl_target)
        return cl_target, {"CL": np.array([cl_target])}

    monkeypatch.setattr(Neuralfoil_Evaluator, "_solve_T2_point", classmethod(solve))
    meta = Polar_File_Meta(polar_type="T2", spec_var="cl", re=100000,
                           val_range=(0.1, 0.26, 0.1), auto_range=False)

    alpha, prediction = Neuralfoil_Evaluator._predict_T2({}, meta, "xlarge")

    np.testing.assert_allclose(calls, [0.1, 0.2])
    np.testing.assert_allclose(prediction["CL"], calls)


def test_T2_point_nonfinite_failure_logs_reason_and_operating_conditions(monkeypatch, caplog):
    def predict(**kwargs):
        return {"CL": np.full(len(kwargs["alpha"]), np.nan)}

    monkeypatch.setattr("airfoileditor.model.nf_driver.get_aero_from_kulfan_parameters", predict)

    solution = Neuralfoil_Evaluator._solve_T2_point({}, Polar_File_Meta(re=100000), "xlarge", 0.7)

    assert solution is None
    record = caplog.records[-1]
    assert record.levelname == "ERROR"
    assert "non-finite lift prediction" in record.message
    assert "cl=0.7000" in record.message
    assert "Re=119523" in record.message
    assert "alpha=2.0000" in record.message


@pytest.mark.skipif(not Neuralfoil_Evaluator.ready, reason="NeuralFoil unavailable")
def test_T2_real_neuralfoil_matches_targets_and_final_operating_conditions():
    from airfoileditor.model.neuralfoil_core.neuralfoil.core_api import get_aero_from_kulfan_parameters

    foil = Airfoil_As_CST(np.full(8, 0.15), np.full(8, -0.15), 0.0, 0.0,
                          derotation_angle=1.5)
    meta = Polar_File_Meta(polar_type="T2", spec_var="cl", re=200000, ncrit=7.0,
                           val_range=(0.1, 0.8, 0.1), auto_range=False)

    result = Neuralfoil_Evaluator.get_polar_data_set(foil, meta, model_size="small",
                                                    min_confidence=None)

    target = np.arange(0.1, 0.85, 0.1)
    np.testing.assert_allclose([row.cl for row in result.rows], target,
                               atol=Neuralfoil_Evaluator.T2_CL_TOLERANCE)
    direct = get_aero_from_kulfan_parameters(
        {"upper_weights": foil.upper_weights, "lower_weights": foil.lower_weights,
         "leading_edge_weight": foil.le_weight, "TE_thickness": foil.te_thickness},
        alpha=np.array([row.alpha for row in result.rows]) + foil.derotation_angle,
        Re=meta.re / np.sqrt(target), n_crit=meta.ncrit, model_size="small")

    for column, key in (("cl", "CL"), ("cd", "CD"), ("cm", "CM"),
                        ("xtrt", "Top_Xtr"), ("xtrb", "Bot_Xtr")):
        np.testing.assert_allclose([getattr(row, column) for row in result.rows], direct[key])
    assert result.meta.polar_type == "T2"
    assert result.meta.re == meta.re
    assert result.meta.spec_var == "cl"


@pytest.mark.skipif(not Neuralfoil_Evaluator.ready, reason="NeuralFoil unavailable")
def test_T1_real_neuralfoil_retains_fixed_re_alpha_sweep():
    from airfoileditor.model.neuralfoil_core.neuralfoil.core_api import get_aero_from_kulfan_parameters

    foil = Airfoil_As_CST(np.full(8, 0.15), np.full(8, -0.15), 0.0, 0.0)
    meta = Polar_File_Meta(polar_type="T1", spec_var="alpha", re=200000, ncrit=7.0,
                           val_range=(-2.0, 6.0, 2.0), auto_range=False)

    result = Neuralfoil_Evaluator.get_polar_data_set(foil, meta, model_size="small",
                                                    min_confidence=None)
    alpha = np.arange(-2.0, 7.0, 2.0)
    direct = get_aero_from_kulfan_parameters(
        {"upper_weights": foil.upper_weights, "lower_weights": foil.lower_weights,
         "leading_edge_weight": foil.le_weight, "TE_thickness": foil.te_thickness},
        alpha=alpha, Re=meta.re, n_crit=meta.ncrit, model_size="small")

    np.testing.assert_array_equal([row.alpha for row in result.rows], alpha)
    np.testing.assert_allclose([row.cl for row in result.rows], direct["CL"])
    np.testing.assert_allclose([row.cd for row in result.rows], direct["CD"])


@pytest.mark.parametrize("step", [1.0, 0.5])
def test_auto_range_uses_lowest_lower_cl_cd_point(step):
    alpha_samples = np.arange(-10.0, 5.0)
    cl_samples = np.array([-1.0, -0.9, -0.8, -0.7, -0.6, -0.5, -0.4,
                           -0.3, -0.2, -0.1, 0.0, 0.2, 0.4, 0.35, 0.3])
    efficiency = np.array([-15.0, -20.0, -25.0, -5.0, -10.0, -15.0, -18.0,
                           -15.0, -10.0, -5.0, 0.0, 10.0, 20.0, 15.0, 10.0])
    cd_samples = np.divide(cl_samples, efficiency, out=np.full(15, 0.02),
                           where=efficiency != 0.0)
    alpha = np.arange(-10.0, 4.0 + step * 0.5, step)
    predict = {
        "CL": np.interp(alpha, alpha_samples, cl_samples),
        "CD": np.interp(alpha, alpha_samples, cd_samples),
        "panels": np.arange(len(alpha) * 2).reshape(len(alpha), 2),
    }

    trimmed_alpha, trimmed_predict = Neuralfoil_Evaluator._apply_auto_range_mask(alpha, predict)

    expected_mask = (alpha >= -9.0) & (alpha <= 3.0)
    np.testing.assert_array_equal(trimmed_alpha, alpha[expected_mask])
    for key in predict:
        np.testing.assert_array_equal(trimmed_predict[key], predict[key][expected_mask])


def test_neuralfoil_evaluator_exposes_polar_api():
    assert Neuralfoil_Evaluator.NAME == "NeuralFoil"
    assert callable(Neuralfoil_Evaluator.get_polar_data_set)


def test_build_rows_uses_panel_values_to_compute_cp_min():
    predict = {
        "CL": np.array([0.1, 0.2, 0.3]),
        "CD": np.array([0.01, 0.02, 0.03]),
        "CM": np.array([0.0, 0.0, 0.0]),
        "Top_Xtr": np.array([0.3, 0.4, 0.5]),
        "Bot_Xtr": np.array([0.2, 0.3, 0.4]),
        "analysis_confidence": np.array([0.9, 0.8, 0.7]),
        "upper_bl_ue/vinf_0": np.array([0.5, 0.8, 0.7]),
        "upper_bl_ue/vinf_1": np.array([0.9, 0.6, 0.4]),
        "upper_bl_ue/vinf_2": np.array([0.7, 0.5, 0.3]),
        "lower_bl_ue/vinf_0": np.array([0.4, 0.6, 0.5]),
        "lower_bl_ue/vinf_1": np.array([0.8, 0.7, 0.6]),
        "lower_bl_ue/vinf_2": np.array([0.9, 0.5, 0.4]),
    }

    rows = Neuralfoil_Evaluator._build_rows(predict, np.array([-2.0, 0.0, 2.0]))

    assert len(rows) == 3
    np.testing.assert_allclose([row.cp_min for row in rows], [0.19, 0.36, 0.51])


def test_estimate_bubble_flags_separated_panels_before_transition():
    from airfoileditor.model.neuralfoil_core.neuralfoil.core_api import bl_x_points, N_BL_POINTS

    # separate the two panels closest to x/c = 0.375 and 0.625, transition just after
    H = np.zeros ((2, N_BL_POINTS))
    separated_idx = np.where ((bl_x_points > 0.3) & (bl_x_points < 0.7))[0]
    H[0, separated_idx] = 4.0
    xtr = np.array([0.7, 0.7])

    bubbles = Neuralfoil_Evaluator._estimate_bubble(H, xtr)

    assert bubbles[0] is not None
    assert bubbles[0].x_start == bl_x_points[separated_idx[0]]
    assert bubbles[0].x_end == xtr[0]
    assert bubbles[1] is None


def test_estimate_bubble_ignores_rows_without_transition():
    from airfoileditor.model.neuralfoil_core.neuralfoil.core_api import N_BL_POINTS

    H = np.full((1, N_BL_POINTS), 4.0)   # separated everywhere
    xtr = np.array([1.0])                # but no transition detected

    bubbles = Neuralfoil_Evaluator._estimate_bubble(H, xtr)

    assert bubbles[0] is None
