#!/usr/bin/env python
# -*- coding: utf-8 -*-

import numpy as np

from airfoileditor.model.nf_driver import Neuralfoil_Evaluator


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
