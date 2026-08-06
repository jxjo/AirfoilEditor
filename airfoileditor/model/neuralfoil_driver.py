#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Bridge module between AirfoilEditor and vendored NeuralFoil-Core runtime.

Keep all app-facing integration logic here so vendored code can remain a
clean snapshot under `airfoileditor/model/neuralfoil_core/neuralfoil`.
"""

from typing import Any


class Neuralfoil_Driver:
    """Thin adapter entry point for future NeuralFoil integration."""

    def __init__(self, model_size: str = "large"):
        self.model_size = model_size

    def predict(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Placeholder API for upcoming integration work."""
        raise NotImplementedError("Neuralfoil_Driver.predict is not implemented yet")
