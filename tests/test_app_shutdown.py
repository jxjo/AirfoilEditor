from types import SimpleNamespace
from unittest.mock import Mock
import os

import pytest
from PyQt6.QtCore import QRect

from airfoileditor import app, app_modes
from airfoileditor.app_model import App_Model, Mode_Id
from airfoileditor.app_modes import Mode_Modify, Mode_View, Modes_Manager
from airfoileditor.base.app_utils import Settings
from airfoileditor.model.airfoil import Airfoil
from airfoileditor.model.airfoil_examples import Root_Example


@pytest.fixture
def running(qapp, tmp_path, monkeypatch):
    """ real model and modes manager in View mode on a saved airfoil """

    monkeypatch.setattr(Settings, "_pathFileName", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app.Win_Util, "screen_number_for_window", lambda window: 0)

    example = Root_Example()
    example.set_pathName(str(tmp_path))
    example.save()
    seed = Airfoil.onFileType(example.pathFileName_abs)
    seed.load()

    model = App_Model(workingDir_default=str(tmp_path), start_watchdog=False)
    manager = Modes_Manager(model)
    manager._switch_mode_panel = Mock()
    manager.add_mode(Mode_View(model))
    manager.add_mode(Mode_Modify(model))
    assert manager.set_mode(Mode_Id.VIEW, seed)

    main = SimpleNamespace(
        _modes_manager=manager, _app_model=model,
        _diagram=SimpleNamespace(name="diagram", settings=lambda: {"option": 1}),
        isMaximized=lambda: False, normalGeometry=lambda: QRect(0, 0, 10, 10))
    main._save_app_settings = lambda: app.Main._save_app_settings(main)
    return main, manager, model, seed


def close_window(main):
    event = Mock()
    app.Main.closeEvent(main, event)
    return event


def test_close_event_shuts_modes_down_before_saving_anything():
    parent = Mock()
    main = SimpleNamespace(_modes_manager=parent.manager, _app_model=parent.model,
                           _diagram=SimpleNamespace(name="diagram", settings=lambda: {}),
                           _save_app_settings=parent.save_app_settings)
    event = Mock()
    app.Main.closeEvent(main, event)
    names = [call[0] for call in parent.mock_calls]
    assert names == ["manager.shutdown", "model.save_settings", "model.close", "save_app_settings"]
    event.accept.assert_called_once()


def test_closing_the_window_in_modify_mode_leaves_the_mode_like_exit(running):
    main, manager, model, seed = running
    manager.switch_mode(Mode_Id.MODIFY)
    assert model.case is not None
    design_dir = model.case.design_dir_abs
    assert design_dir and os.path.isdir(design_dir)

    event = close_window(main)

    event.accept.assert_called_once()
    assert model.case is None
    assert model.airfoil is seed
    assert not os.path.exists(design_dir)
    saved = Settings()
    assert saved.get("last_opened") == seed.pathFileName_abs


def test_closing_the_window_saves_lower_panel_state(running):
    main, manager, model, seed = running
    manager._is_minimized = True
    close_window(main)
    assert Settings().get("lower_panel_minimized") is True


def test_exit_only_requests_close(running):
    main, manager, model, seed = running
    manager.switch_mode(Mode_Id.MODIFY)
    requested = Mock()
    manager.sig_close_requested.connect(requested)
    manager.exit()
    requested.assert_called_once()
    assert model.case is not None


def test_shutdown_is_idempotent(running):
    main, manager, model, seed = running
    manager.switch_mode(Mode_Id.MODIFY)
    manager.shutdown()
    manager.shutdown()
    assert model.case is None
    assert model.airfoil is seed


def test_exit_from_view_and_window_close_save_the_same(running):
    main, manager, model, seed = running
    manager.exit()
    close_window(main)
    saved = Settings()
    assert saved.get("last_opened") == seed.pathFileName_abs
    assert saved.get("window_maximize") is False
