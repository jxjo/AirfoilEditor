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
