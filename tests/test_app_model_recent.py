from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QMenu
from airfoileditor import app_modes
from airfoileditor.app_model import App_Model
from airfoileditor.base.app_utils import Recent_Files, Settings
from airfoileditor.model.airfoil import Airfoil
from airfoileditor.model.airfoil_examples import Example, Root_Example
from airfoileditor.model.case import Case_Direct_Design
from airfoileditor.ui.ae_panels import Panel_File_View, Panel_File_View_Small
from airfoileditor.ui.ae_widgets import Airfoil_Select_Open_Widget


@pytest.fixture
def model(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "_pathFileName", str(tmp_path / "settings.json"))
    return App_Model(workingDir_default=str(tmp_path), start_watchdog=False)


def saved_airfoil(directory, name="Root_Example"):
    example = Root_Example()
    example.set_pathName(str(directory))
    example.set_fileName(name + ".dat")
    example.save()
    airfoil = Airfoil.onFileType(example.pathFileName_abs)
    airfoil.load()
    return airfoil


def test_model_owns_one_shared_recent_files(model):
    assert isinstance(model.recent_files, Recent_Files)
    assert model.recent_files is model.recent_files


def test_remember_adds_saved_airfoils_only(model, tmp_path):
    airfoil = saved_airfoil(tmp_path)
    model.remember_airfoil(None)
    model.remember_airfoil(Example())
    assert model.recent_files.paths == []
    model.remember_airfoil(airfoil)
    assert [str(path) for path in model.recent_files.paths] == [airfoil.pathFileName_abs]


def test_forget_removes_by_path_for_str_and_path(model, tmp_path):
    first, second = saved_airfoil(tmp_path, "first"), saved_airfoil(tmp_path, "second")
    model.remember_airfoil(first)
    model.remember_airfoil(second)
    model.forget_airfoil_file(first.pathFileName_abs)
    assert [path.name for path in model.recent_files.paths] == ["second.dat"]
    model.forget_airfoil_file(tmp_path / "second.dat")
    assert model.recent_files.paths == []


def test_open_airfoil_sets_and_remembers(model, tmp_path):
    airfoil = saved_airfoil(tmp_path)
    model.open_airfoil(airfoil)
    assert model.airfoil is airfoil
    assert [str(path) for path in model.recent_files.paths] == [airfoil.pathFileName_abs]


def test_open_airfoil_passes_load_settings_on(model, tmp_path, monkeypatch):
    set_airfoil = Mock()
    monkeypatch.setattr(model, "set_airfoil", set_airfoil)
    airfoil = saved_airfoil(tmp_path)
    model.open_airfoil(airfoil, load_settings=True)
    set_airfoil.assert_called_once_with(airfoil, load_settings=True)


def test_open_example_is_not_remembered(model):
    model.open_airfoil(Example())
    assert model.recent_files.paths == []


def test_open_missing_file_is_not_remembered_but_still_set(model, tmp_path):
    airfoil = saved_airfoil(tmp_path)
    (tmp_path / airfoil.fileName).unlink()
    model.open_airfoil(airfoil)
    assert model.airfoil is airfoil
    assert model.recent_files.paths == []


def test_notify_geo_changing_resets_polars_and_signals_the_source(model, monkeypatch):
    design = Mock()
    monkeypatch.setattr(App_Model, "airfoil_design", property(lambda self: design))
    slot = Mock()
    model.sig_geo_changing.connect(slot)
    model.notify_geo_changing(source="artist")
    design.polarSet.reset_polars.assert_called_once()
    slot.assert_called_once_with("artist")


def test_notify_geo_changing_without_design_does_nothing(model):
    slot = Mock()
    model.sig_geo_changing.connect(slot)
    model.notify_geo_changing()
    slot.assert_not_called()


class Owner:
    """ minimal stand-in for a View panel: the selector lambdas only need app_model, airfoil and _more_menu """

    def __init__(self, model):
        self.app_model = model
        self.sig_modify = self.sig_exit = self.sig_toggle_panel_size = Mock()

    @property
    def airfoil(self):
        return self.app_model.airfoil

    def _more_menu(self):
        return QMenu()


@pytest.mark.parametrize("panel_cls", [Panel_File_View, Panel_File_View_Small])
def test_view_selectors_use_the_model_history_and_record_through_it(model, tmp_path, panel_cls):
    airfoil = saved_airfoil(tmp_path, "current")
    other = saved_airfoil(tmp_path, "other")
    model.open_airfoil(airfoil)
    model.recent_files.clear()
    layout = panel_cls._init_layout(Owner(model))
    selector = layout.itemAt(0).widget()
    assert isinstance(selector, Airfoil_Select_Open_Widget)
    assert selector._recent_files is model.recent_files

    selector.set_airfoil_by_fileName(other.fileName)
    assert [path.name for path in model.recent_files.paths] == ["other.dat"]
    assert model.airfoil.fileName == "other.dat"

    model.recent_files.clear()
    selector._load_open_airfoil(tmp_path / "current.dat")
    assert [path.name for path in model.recent_files.paths] == ["current.dat"]
    assert model.airfoil.fileName == "current.dat"


@pytest.mark.parametrize("operation", ["save_as", "rename"])
@pytest.mark.parametrize("accepted", [False, True])
def test_saved_main_airfoil_history(model, tmp_path, monkeypatch, operation, accepted):
    airfoil = saved_airfoil(tmp_path)
    model.open_airfoil(airfoil)
    old_path = airfoil.pathFileName_abs
    new_path = tmp_path / "new.dat"
    mode = SimpleNamespace(_app_model=model, stacked_panel=Mock(), _toast_message=Mock(),
                           _delete_temp_files=Mock())

    def save():
        if accepted:
            airfoil.set_pathFileName(str(new_path), noCheck=True)
            airfoil.save()
        return accepted

    dialog = Mock(exec=Mock(side_effect=save), remove_designs=False)
    monkeypatch.setattr(app_modes, "Airfoil_Save_Dialog", Mock(return_value=dialog))
    getattr(app_modes.Mode_View, operation)(mode)

    paths = [str(path) for path in model.recent_files.paths]
    if not accepted:
        assert paths == [old_path]
    elif operation == "save_as":
        assert paths == [str(new_path.resolve()), old_path]
    else:
        assert paths == [str(new_path.resolve())]


def test_deletion_forgets_the_file_and_remembers_the_next(model, tmp_path, monkeypatch):
    airfoil, following = saved_airfoil(tmp_path, "gone"), saved_airfoil(tmp_path, "next")
    model.open_airfoil(airfoil)
    old_path = model.recent_files.paths[0]
    mode = SimpleNamespace(_app_model=model, stacked_panel=Mock(), _toast_message=Mock(),
                           delete_temp_files=Mock())
    monkeypatch.setattr(app_modes.MessageBox, "warning",
                        Mock(return_value=app_modes.QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(app_modes, "get_next_airfoil_in_dir", Mock(return_value=following))
    app_modes.Mode_View.delete(mode)
    assert not old_path.exists()
    assert [path.name for path in model.recent_files.paths] == ["next.dat"]
    assert model.airfoil is following


def test_deletion_with_only_an_example_left_remembers_nothing(model, tmp_path, monkeypatch):
    airfoil = saved_airfoil(tmp_path)
    model.open_airfoil(airfoil)
    mode = SimpleNamespace(_app_model=model, stacked_panel=Mock(), _toast_message=Mock(),
                           delete_temp_files=Mock())
    monkeypatch.setattr(app_modes.MessageBox, "warning",
                        Mock(return_value=app_modes.QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(app_modes.MessageBox, "info", Mock())
    monkeypatch.setattr(app_modes, "get_next_airfoil_in_dir", Mock(return_value=Example()))
    app_modes.Mode_View.delete(mode)
    assert model.recent_files.paths == []


def test_finishing_a_case_remembers_the_final_airfoil(model, tmp_path, monkeypatch):
    final = saved_airfoil(tmp_path, "final")
    case = Mock(spec=Case_Direct_Design)
    case.get_final_from_design.return_value = final
    model._case = case
    model._airfoil = Mock(fileName="design.dat")
    mode = SimpleNamespace(_app_model=model, stacked_panel=Mock(), _toast_message=Mock(),
                           sig_leave_requested=Mock())
    monkeypatch.setattr(app_modes, "Airfoil_Save_Dialog",
                        Mock(return_value=Mock(exec=Mock(return_value=True), remove_designs=False)))
    app_modes.Mode_Abstract.finish(mode)
    assert [path.name for path in model.recent_files.paths] == ["final.dat"]


def test_cancelled_finish_remembers_nothing(model, tmp_path, monkeypatch):
    case = Mock(spec=Case_Direct_Design)
    case.get_final_from_design.return_value = saved_airfoil(tmp_path, "final")
    model._case = case
    model._airfoil = Mock(fileName="design.dat")
    mode = SimpleNamespace(_app_model=model, stacked_panel=Mock(), _toast_message=Mock(),
                           sig_leave_requested=Mock())
    monkeypatch.setattr(app_modes, "Airfoil_Save_Dialog",
                        Mock(return_value=Mock(exec=Mock(return_value=False))))
    app_modes.Mode_Abstract.finish(mode)
    assert model.recent_files.paths == []
