#!/usr/bin/env python
# -*- coding: utf-8 -*-

import numpy as np
import pytest

from airfoileditor.base.spline import CST
from airfoileditor.model.airfoil import Airfoil, Airfoil_CST, GEO_BASIC
from airfoileditor.model.airfoil_examples import Root_Example
from airfoileditor.model.geometry_cst import Geometry_CST


def test_cst_curve_eval_and_endpoints():
    w = [0.16, 0.14, 0.12, 0.10, 0.08, 0.06, 0.04, 0.02]

    cst_up = CST(weights=w, le_weight=0.02, te_gap=0.005)
    cst_lo = CST(weights=w, le_weight=-0.02, te_gap=-0.005)

    y0_up = cst_up.eval_y(0.0)
    y0_lo = cst_lo.eval_y(0.0)
    y1_up = cst_up.eval_y(1.0)
    y1_lo = cst_lo.eval_y(1.0)

    assert y0_up == 0.0
    assert y0_lo == 0.0
    assert y1_up == 0.005
    assert y1_lo == -0.005


def test_cst_le_curvature_special_case():
    cst = CST(weights=[0.2, 0.15, 0.1, 0.05], le_weight=0.0, te_gap=0.0, n1=0.5, n2=1.0)
    kappa_le = cst.curvature(0.0)

    # For y ~ a*sqrt(x) near LE, curvature limit is -2/a^2 for positive a.
    assert np.isclose(kappa_le, -2.0 / (0.2 * 0.2), atol=1e-8)


def test_cst_derivatives_match_finite_difference():
    cst = CST(weights=[0.22, 0.18, 0.13, 0.09, 0.06], le_weight=0.01, te_gap=0.003)
    x = np.linspace(0.05, 0.95, 41)
    h = 1e-6

    y_plus = cst.eval_y(x + h)
    y = cst.eval_y(x)
    y_minus = cst.eval_y(x - h)

    _, dy = cst.eval(x, der=1)
    _, ddy = cst.eval(x, der=2)

    dy_fd = (y_plus - y_minus) / (2.0 * h)
    ddy_fd = (y_plus - 2.0 * y + y_minus) / (h * h)

    np.testing.assert_allclose(dy, dy_fd, rtol=1e-6, atol=2e-6)
    np.testing.assert_allclose(ddy, ddy_fd, rtol=1e-4, atol=2e-3)


def test_cst_eval_scalar_matches_array():
    cst = CST(weights=[0.19, 0.16, 0.11, 0.07], le_weight=0.01, te_gap=0.003)

    x_scalar, y_scalar = cst.eval(0.37, der=0)
    x_array, y_array = cst.eval(np.array([0.37]), der=0)

    assert np.isclose(x_scalar, x_array[0], atol=1e-14)
    assert np.isclose(y_scalar, y_array[0], atol=1e-14)

    dx_scalar, dy_scalar = cst.eval(0.37, der=1)
    dx_array, dy_array = cst.eval(np.array([0.37]), der=1)

    assert np.isclose(dx_scalar, dx_array[0], atol=1e-14)
    assert np.isclose(dy_scalar, dy_array[0], atol=1e-14)

    ddx_scalar, ddy_scalar = cst.eval(0.37, der=2)
    ddx_array, ddy_array = cst.eval(np.array([0.37]), der=2)

    assert np.isclose(ddx_scalar, ddx_array[0], atol=1e-14)
    assert np.isclose(ddy_scalar, ddy_array[0], atol=1e-14)


def test_airfoil_cst_default_geometry():
    airfoil = Airfoil_CST(
        weights_upper=Geometry_CST.DEFAULT_WEIGHTS_UPPER,
        weights_lower=Geometry_CST.DEFAULT_WEIGHTS_LOWER)
    geo: Geometry_CST = airfoil.geo

    assert airfoil.nPoints == 161
    assert airfoil.nPanels == 160
    assert airfoil.isNormalized
    assert geo.isCST
    assert abs(geo.te_gap) < 1e-10


def test_airfoil_cst_save_load_roundtrip(tmp_path):
    path = tmp_path / "cst_roundtrip.cst"

    weights_upper = [0.17, 0.16, 0.14, 0.11, 0.09, 0.07, 0.05, 0.03]
    weights_lower = [-0.15, -0.14, -0.12, -0.10, -0.08, -0.06, -0.04, -0.02]

    airfoil = Airfoil_CST(
        name="CST_Roundtrip",
        pathFileName=str(path),
        weights_upper=weights_upper,
        weights_lower=weights_lower,
        le_weight=0.012,
        te_thickness=0.004,
    )

    airfoil.save()

    loaded = Airfoil.onFileType(str(path))
    loaded.load()

    assert isinstance(loaded, Airfoil_CST)
    assert loaded.name == "CST_Roundtrip"
    assert np.allclose(loaded.geo.upper.cst.weights, np.array(weights_upper, dtype=float))
    assert np.allclose(loaded.geo.lower.cst.weights, np.array(weights_lower, dtype=float))
    assert abs(loaded.geo.upper.cst.le_weight - 0.012) < 1e-12
    assert abs(loaded.geo.te_gap - 0.004) < 1e-12


def test_fit_from_xy_recovers_known_weights_free_le_curvature():
    # weights_lower[0] must mirror weights_upper[0] (equal magnitude, opposite sign):
    # fit_from_xy ties the leading-edge weight of both sides to a single shared unknown.
    weights_upper = np.array([0.18, 0.16, 0.14, 0.11, 0.09, 0.07, 0.05, 0.03])
    weights_lower = np.array([-0.18, -0.14, -0.12, -0.10, -0.08, -0.06, -0.04, -0.02])
    le_weight = 0.015
    te_thickness = 0.006

    cst_upper = CST(weights=weights_upper, le_weight=le_weight, te_gap=0.5 * te_thickness)
    cst_lower = CST(weights=weights_lower, le_weight=le_weight, te_gap=-0.5 * te_thickness)

    x = np.linspace(0.0, 1.0, 100)
    y_upper = cst_upper.eval_y(x)
    y_lower = cst_lower.eval_y(x)

    fit_upper, fit_lower, fit_le_weight, fit_te_thickness = Geometry_CST.fit_from_xy(
        x, y_upper, x, y_lower, n_weights=len(weights_upper), le_curvature=-1.0)

    np.testing.assert_allclose(fit_upper, weights_upper, atol=1e-8)
    np.testing.assert_allclose(fit_lower, weights_lower, atol=1e-8)
    assert np.isclose(fit_le_weight, le_weight, atol=1e-8)
    assert np.isclose(fit_te_thickness, te_thickness, atol=1e-8)


def test_fit_from_xy_with_fixed_le_curvature():
    # weights_lower[0] must mirror weights_upper[0]: fixing le_curvature pins both sides'
    # leading-edge weight to the same magnitude (opposite sign), so the input data must match.
    weights_upper = np.array([0.2, 0.16, 0.13, 0.10, 0.08])
    weights_lower = np.array([-0.2, -0.15, -0.12, -0.09, -0.07])
    le_weight = -0.01
    te_thickness = 0.002

    cst_upper = CST(weights=weights_upper, le_weight=le_weight, te_gap=0.5 * te_thickness)
    cst_lower = CST(weights=weights_lower, le_weight=le_weight, te_gap=-0.5 * te_thickness)

    x = np.linspace(0.0, 1.0, 80)
    y_upper = cst_upper.eval_y(x)
    y_lower = cst_lower.eval_y(x)

    le_curvature = abs(cst_upper.curvature(0.0))

    fit_upper, fit_lower, fit_le_weight, fit_te_thickness = Geometry_CST.fit_from_xy(
        x, y_upper, x, y_lower, n_weights=len(weights_upper), le_curvature=le_curvature)

    # weights[0] is pinned exactly by the fixed le_curvature (equal magnitude, opposite sign)
    assert np.isclose(fit_upper[0], weights_upper[0], atol=1e-10)
    assert np.isclose(fit_lower[0], -weights_upper[0], atol=1e-10)

    np.testing.assert_allclose(fit_upper[1:], weights_upper[1:], atol=1e-8)
    np.testing.assert_allclose(fit_lower[1:], weights_lower[1:], atol=1e-8)
    assert np.isclose(fit_le_weight, le_weight, atol=1e-8)
    assert np.isclose(fit_te_thickness, te_thickness, atol=1e-8)


def test_fit_from_xy_invalid_arguments_raise():
    x = np.linspace(0.0, 1.0, 20)
    y = np.zeros_like(x)

    with pytest.raises(ValueError):
        Geometry_CST.fit_from_xy(x, y, x, y, n_weights=1)

    with pytest.raises(ValueError):
        Geometry_CST.fit_from_xy(x, y, x, y, le_curvature=0.0)

    with pytest.raises(ValueError):
        Geometry_CST.fit_from_xy(x, y, x, y, smooth_lambda=-1.0)


def test_fit_from_xy_smoothing_reduces_weight_second_difference_energy():
    seed_airfoil = Root_Example(geometry=GEO_BASIC)

    x_upper, y_upper = seed_airfoil.geo.upper.x, seed_airfoil.geo.upper.y
    x_lower, y_lower = seed_airfoil.geo.lower.x, seed_airfoil.geo.lower.y

    w_u_plain, w_l_plain, _, _ = Geometry_CST.fit_from_xy(
        x_upper, y_upper, x_lower, y_lower,
        n_weights=8, le_curvature=None, smooth_lambda=0.0)

    w_u_smooth, w_l_smooth, _, _ = Geometry_CST.fit_from_xy(
        x_upper, y_upper, x_lower, y_lower,
        n_weights=8, le_curvature=None, smooth_lambda=1e-3)

    def d2_energy(w: np.ndarray) -> float:
        return float(np.sum((w[2:] - 2.0 * w[1:-1] + w[:-2]) ** 2))

    e_plain = d2_energy(w_u_plain) + d2_energy(w_l_plain)
    e_smooth = d2_energy(w_u_smooth) + d2_energy(w_l_smooth)

    assert e_smooth < e_plain


def test_fit_from_xy_real_airfoil_roundtrip():
    seed_airfoil = Root_Example(geometry=GEO_BASIC)

    x_upper, y_upper = seed_airfoil.geo.upper.x, seed_airfoil.geo.upper.y
    x_lower, y_lower = seed_airfoil.geo.lower.x, seed_airfoil.geo.lower.y

    weights_upper, weights_lower, le_weight, te_thickness = Geometry_CST.fit_from_xy(
        x_upper, y_upper, x_lower, y_lower, n_weights=8, le_curvature=-1.0)

    geo = Geometry_CST(weights_upper, weights_lower, le_weight=le_weight, te_thickness=te_thickness)

    y_upper_fit = geo.upper.cst.eval_y(x_upper)
    y_lower_fit = geo.lower.cst.eval_y(x_lower)

    rms_upper = np.sqrt(np.mean((y_upper_fit - y_upper) ** 2))
    rms_lower = np.sqrt(np.mean((y_lower_fit - y_lower) ** 2))

    assert rms_upper < 0.001
    assert rms_lower < 0.001
