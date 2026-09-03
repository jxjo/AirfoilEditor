#!/usr/bin/env python
# -*- coding: utf-8 -*-

from airfoileditor.model.nf_driver import Neuralfoil_Evaluator


def test_neuralfoil_evaluator_exposes_polar_api():
    assert Neuralfoil_Evaluator.NAME == "NeuralFoil"
    assert callable(Neuralfoil_Evaluator.get_polar_data_set)
