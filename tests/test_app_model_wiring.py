import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QDialog

from airfoileditor import app_modes
from airfoileditor.app_model import App_Model, Mode_Id
from airfoileditor.app_modes import Mode_Optimize
from airfoileditor.base.app_utils import Settings
from airfoileditor.model.xo2_driver import Xoptfoil2


@pytest.fixture
def model(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "_pathFileName", str(tmp_path / "settings.json"))
    return App_Model(workingDir_default=str(tmp_path), start_watchdog=False)


def accepted_dialog(**attributes):
    return Mock(return_value=Mock(exec=Mock(return_value=QDialog.DialogCode.Accepted), **attributes))


def optimize_mode(app_model):
    mode = Mode_Optimize(app_model)
    mode._stacked_panel = Mock()                    # do not build the real panels
    return mode


def test_watchdog_is_a_public_optional_property(model):
    assert model.watchdog is None
    watchdog = object()
    model._watchdog = watchdog
    assert model.watchdog is watchdog


def test_matcher_is_initialised_and_a_finished_signal_without_matcher_is_harmless(model):
    assert model._matcher is None
    model._on_match_finished(Mock())


def test_optimize_asks_for_a_new_input_file_with_the_public_watchdog(monkeypatch):
    monkeypatch.setattr(Xoptfoil2, "ready", True)
    watchdog = object()
    app_model = SimpleNamespace(watchdog=watchdog, airfoil_after_case=Mock(pathName_abs="airfoil_dir"))
    mode = optimize_mode(app_model)
    select = accepted_dialog(input_fileName="")                         # no existing file - create a new one
    new = accepted_dialog(workingDir="airfoil_dir", input_fileName="new.xo2")
    monkeypatch.setattr(app_modes, "Xo2_Select_Dialog", select)
    monkeypatch.setattr(app_modes, "Xo2_New_Dialog", new)

    assert mode.prepare_check_enter(None) == os.path.join("airfoil_dir", "new.xo2")
    assert new.call_args.kwargs["watchdog"] is watchdog


def test_optimize_new_version_dialog_gets_the_public_watchdog(monkeypatch):
    watchdog = object()
    app_model = SimpleNamespace(watchdog=watchdog, airfoil_seed=Mock(), workingDir="dir", case=None)
    mode = optimize_mode(app_model)
    mode.switch_mode = Mock()
    new = accepted_dialog(workingDir="dir", input_fileName="next.xo2")
    monkeypatch.setattr(app_modes, "Xo2_New_Dialog", new)

    mode.new()

    assert new.call_args.kwargs["watchdog"] is watchdog
    mode.switch_mode.assert_called_once_with(Mode_Id.OPTIMIZE, os.path.join("dir", "next.xo2"))
