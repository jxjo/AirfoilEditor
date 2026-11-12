#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Shared pytest fixtures for the AirfoilEditor test suite.
"""

import sys

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication required by Qt classes (QThread, signals, …)."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def restore_example_working_dir(monkeypatch):
    """App_Model sets the working dir of Example airfoils as class state - undo it after each test."""
    from airfoileditor.model.airfoil_examples import Example
    monkeypatch.setattr(Example, "workingDir_default", Example.workingDir_default)
