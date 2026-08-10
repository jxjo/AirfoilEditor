#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pytest

from airfoileditor.model.neuralfoil_driver import Neuralfoil_Driver


def test_neuralfoil_driver_placeholder_predict_raises():
    driver = Neuralfoil_Driver()

    with pytest.raises(NotImplementedError):
        driver.predict()
