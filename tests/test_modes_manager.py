from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from airfoileditor import app_modes
from airfoileditor.app_model import App_Model, Mode_Id
from airfoileditor.app_modes import Mode_Optimize, Mode_View, Modes_Manager
from airfoileditor.base.app_utils import Settings
from airfoileditor.model.airfoil_examples import Example
from airfoileditor.model.xo2_driver import Xoptfoil2


def fake_mode(calls, mode_id, prepared="arg"):
    mode = Mock()
    mode.mode_id = mode_id
    mode.prepare_check_enter.side_effect = lambda arg=None: calls.append((mode_id, "prepare")) or prepared
    mode.on_leave.side_effect = lambda: calls.append((mode_id, "leave"))
    mode.on_enter.side_effect = lambda arg: calls.append((mode_id, "enter"))
    return mode


@pytest.fixture
def manager(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "_pathFileName", str(tmp_path / "settings.json"))
    model = SimpleNamespace(mode_id=Mode_Id.MODIFY)
    manager = Modes_Manager(model)
    manager._switch_mode_panel = Mock()
    return manager


def test_switch_prepares_new_mode_before_leaving_current_mode(manager):
    calls = []
    manager.add_mode(fake_mode(calls, Mode_Id.MODIFY))
    manager.add_mode(fake_mode(calls, Mode_Id.VIEW))
    manager.switch_mode(Mode_Id.VIEW)
    assert calls == [(Mode_Id.VIEW, "prepare"), (Mode_Id.MODIFY, "leave"), (Mode_Id.VIEW, "enter")]


def test_refused_entry_keeps_current_mode_untouched(manager):
    calls = []
    current = fake_mode(calls, Mode_Id.MODIFY)
    manager.add_mode(current)
    manager.add_mode(fake_mode(calls, Mode_Id.OPTIMIZE, prepared=None))
    manager.switch_mode(Mode_Id.OPTIMIZE)
    assert calls == [(Mode_Id.OPTIMIZE, "prepare")]
    current.on_leave.assert_not_called()
    manager._switch_mode_panel.assert_not_called()
    assert manager._app_model.mode_id == Mode_Id.MODIFY


def test_optimize_cannot_be_entered_without_xoptfoil2(monkeypatch):
    monkeypatch.setattr(Xoptfoil2, "ready", False)
    mode = Mode_Optimize(SimpleNamespace())
    assert mode.prepare_check_enter(None) is None
    assert mode.prepare_check_enter("case.xo2") is None


def test_set_mode_reports_refused_initial_mode(manager):
    manager._app_model.mode_id = None
    calls = []
    manager.add_mode(fake_mode(calls, Mode_Id.OPTIMIZE, prepared=None))
    manager.add_mode(fake_mode(calls, Mode_Id.VIEW))
    assert manager.set_mode(Mode_Id.OPTIMIZE, "case.xo2") is False
    assert calls == [(Mode_Id.OPTIMIZE, "prepare")]
    assert manager.set_mode(Mode_Id.VIEW, "airfoil") is True
    assert calls[-1] == (Mode_Id.VIEW, "enter")


def case_model(final=None):
    seed, design = object(), object()
    case = SimpleNamespace(airfoil_seed=seed, airfoil_final=final)
    return SimpleNamespace(case=case, airfoil=design), seed, design


@pytest.mark.parametrize("has_final", [False, True])
def test_airfoil_after_case_is_the_airfoil_on_leave(has_final):
    final = object() if has_final else None
    model, seed, design = case_model(final)
    expected = final if has_final else seed
    assert App_Model.airfoil_after_case.fget(model) is expected
    assert expected is not design


def test_airfoil_after_case_without_case_is_current_airfoil():
    airfoil = object()
    model = SimpleNamespace(case=None, airfoil=airfoil)
    assert App_Model.airfoil_after_case.fget(model) is airfoil


@pytest.mark.parametrize("mode_cls", [Mode_View, app_modes.Mode_As_Bezier])
def test_entering_from_a_case_uses_airfoil_after_case_not_the_design(qapp, mode_cls):
    model, seed, design = case_model()
    model.airfoil_after_case = seed
    mode = mode_cls(model)
    assert mode.prepare_check_enter(None) is seed


@pytest.fixture
def real_manager(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "_pathFileName", str(tmp_path / "settings.json"))
    model = App_Model(workingDir_default=str(tmp_path), start_watchdog=False)
    manager = Modes_Manager(model)
    manager._switch_mode_panel = Mock()
    for mode_cls in (Mode_View, app_modes.Mode_Modify):
        manager.add_mode(mode_cls(model))
    airfoil = Example()
    assert manager.set_mode(Mode_Id.VIEW, airfoil)
    return manager, model, airfoil


def test_modify_and_back_to_view_continues_with_seed_airfoil(real_manager):
    manager, model, seed = real_manager
    manager.switch_mode(Mode_Id.MODIFY)
    assert model.mode_id == Mode_Id.MODIFY
    assert model.case is not None and model.airfoil is not seed
    assert model.airfoil_after_case is seed

    manager.switch_mode(Mode_Id.VIEW)
    assert model.mode_id == Mode_Id.VIEW
    assert model.case is None
    assert model.airfoil is seed


def test_cancelled_modify_confirmation_stays_in_view(real_manager, monkeypatch):
    manager, model, seed = real_manager
    monkeypatch.setattr(type(seed.geo), "isProbablyFlapped", property(lambda self: True))
    monkeypatch.setattr(app_modes.MessageBox, "confirm",
                        Mock(return_value=app_modes.QMessageBox.StandardButton.Cancel))
    manager.switch_mode(Mode_Id.MODIFY)
    assert model.mode_id == Mode_Id.VIEW
    assert model.case is None
    assert model.airfoil is seed
    manager._switch_mode_panel.assert_not_called()


def test_initial_optimize_without_xoptfoil2_is_refused_and_view_can_start(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "_pathFileName", str(tmp_path / "settings.json"))
    monkeypatch.setattr(Xoptfoil2, "ready", False)
    model = App_Model(workingDir_default=str(tmp_path), start_watchdog=False)
    manager = Modes_Manager(model)
    manager.add_mode(Mode_View(model))
    manager.add_mode(Mode_Optimize(model))
    assert manager.set_mode(Mode_Id.OPTIMIZE, "case.xo2") is False
    assert model.mode_id is None and model.case is None
    assert manager.set_mode(Mode_Id.VIEW, Example()) is True
    assert model.mode_id == Mode_Id.VIEW
