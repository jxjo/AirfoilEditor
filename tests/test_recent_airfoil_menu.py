from unittest.mock import Mock
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QStyle, QStyleOptionToolButton
from PyQt6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from airfoileditor import app_modes
from airfoileditor.base.app_utils import Recent_Files, Settings
from airfoileditor.model.airfoil import Airfoil
from airfoileditor.model.airfoil_examples import Example, Root_Example
from airfoileditor.ui.ae_widgets import Airfoil_Select_Open_Widget, QFileDialog, MessageBox


@pytest.fixture
def saved_airfoil(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "_pathFileName", str(tmp_path / "settings.json"))
    airfoil = Root_Example()
    airfoil.set_pathName(str(tmp_path))
    airfoil.save()
    loaded = Airfoil.onFileType(airfoil.pathFileName_abs)
    loaded.load()
    return loaded


def selector(airfoil, **kwargs):
    parent = QWidget()
    layout = QHBoxLayout(parent)
    widget = Airfoil_Select_Open_Widget(layout, get=lambda: airfoil, **kwargs)
    return parent, widget


def test_recent_labels_show_only_filename_and_keep_full_path_tooltip(qapp, saved_airfoil, tmp_path):
    history = Recent_Files()
    first = tmp_path / "first" / "foil&test.dat"
    second = tmp_path / "second" / first.name
    for path in (first, second):
        path.parent.mkdir()
        path.touch()
        history.add(path)
    parent, widget = selector(saved_airfoil, set=Mock(), recent_files=history)
    try:
        widget._fill_recent_menu()
        actions = widget._recent_menu.actions()
        assert [action.text() for action in actions] == ["foil&&test.dat", "foil&&test.dat"]
        assert [action.toolTip() for action in actions] == [str(second), str(first)]
    finally:
        parent.close()


def test_recent_action_uses_open_callback_and_main_click_still_opens(qapp, saved_airfoil, monkeypatch):
    history = Recent_Files()
    history.add(saved_airfoil.pathFileName_abs)
    opened, selected = Mock(), Mock()
    parent, widget = selector(Example(), set=selected, set_open=opened, recent_files=history)
    try:
        assert widget._icon_widget.popupMode() == QToolButton.ToolButtonPopupMode.MenuButtonPopup
        widget._fill_recent_menu()
        action = widget._recent_menu.actions()[0]
        assert action.toolTip() == saved_airfoil.pathFileName_abs
        action.trigger()
        assert opened.call_count == 1
        assert opened.call_args.args[0].isLoaded
        selected.assert_not_called()
        file_dialog = Mock(return_value=(saved_airfoil.pathFileName_abs, ""))
        monkeypatch.setattr(QFileDialog, "getOpenFileName", file_dialog)
        widget._icon_widget.click()
        file_dialog.assert_called_once()
        assert opened.call_count == 2
        assert len(history.paths) == 1
    finally:
        parent.close()


def test_example_state_has_text_split_button_and_empty_history(qapp, saved_airfoil):
    history = Recent_Files()
    history.add(saved_airfoil.pathFileName_abs)
    parent, widget = selector(Example(), recent_files=history)
    try:
        assert widget.no_files_here()
        assert not widget._button_widget.isHidden()
        assert widget._button_widget.popupMode() == QToolButton.ToolButtonPopupMode.MenuButtonPopup
        widget._fill_recent_menu()
        assert len(widget._recent_menu.actions()) == 1
        history.clear()
        widget._fill_recent_menu()
        assert not widget._recent_menu.actions()[0].isEnabled()
    finally:
        parent.close()


def test_current_file_is_hidden_without_changing_history(qapp, saved_airfoil, tmp_path):
    history = Recent_Files()
    history.add(saved_airfoil.pathFileName_abs)
    current_path = history.paths[0]
    other_path = tmp_path / "other" / current_path.name
    other_path.parent.mkdir()
    other_path.touch()
    history.add(other_path)
    current = [saved_airfoil]
    parent = QWidget()
    widget = Airfoil_Select_Open_Widget(
        QHBoxLayout(parent), get=lambda: current[0], set=Mock(), recent_files=history)
    try:
        widget._fill_recent_menu()
        assert [action.toolTip() for action in widget._recent_menu.actions()] == [str(other_path)]
        assert history.paths == [other_path, current_path]
        history.remove(other_path)
        widget._fill_recent_menu()
        action = widget._recent_menu.actions()[0]
        assert action.text() == "No other recent airfoils"
        assert not action.isEnabled()
        assert history.paths == [current_path]
        current[0] = Example()
        widget.refresh()
        widget._fill_recent_menu()
        assert widget._recent_menu.actions()[0].toolTip() == str(current_path)
        assert widget._recent_menu.actions()[0].isEnabled()
    finally:
        parent.close()


def test_missing_recent_file_notifies_and_removes(qapp, saved_airfoil, monkeypatch):
    history = Recent_Files()
    history.add(saved_airfoil.pathFileName_abs)
    path = history.paths[0]
    path.unlink()
    callback = Mock()
    error = Mock()
    monkeypatch.setattr(MessageBox, "error", error)
    parent, widget = selector(Example(), set_open=callback, recent_files=history)
    try:
        widget._open_recent(path)
        error.assert_called_once()
        callback.assert_not_called()
        assert history.paths == []
    finally:
        parent.close()


def test_directory_selection_tracks_only_when_opted_in(qapp, saved_airfoil):
    history = Recent_Files()
    callback = Mock()
    parent, widget = selector(saved_airfoil, set=callback, recent_files=history)
    other_parent, plain_widget = selector(saved_airfoil, set=callback)
    try:
        widget.set_airfoil_by_fileName(saved_airfoil.fileName)
        assert history.paths
        history.clear()
        plain_widget.set_airfoil_by_fileName(saved_airfoil.fileName)
        assert history.paths == []
        assert plain_widget._icon_widget.menu() is None
    finally:
        parent.close()
        other_parent.close()


@pytest.mark.parametrize("use_example", [False, True])
@pytest.mark.parametrize("open_below", [False, True])
def test_arrow_opens_menu_without_opening_file_dialog(qapp, saved_airfoil, monkeypatch, use_example, open_below):
    history = Recent_Files()
    history.add(saved_airfoil.pathFileName_abs)
    parent, widget = selector(Example() if use_example else saved_airfoil,
                              set=Mock(), recent_files=history, openBelow=open_below)
    file_dialog = Mock(return_value=("", ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", file_dialog)
    try:
        parent.show()
        qapp.processEvents()
        button = widget._button_widget if use_example or open_below else widget._icon_widget
        assert button.isEnabled()
        option = QStyleOptionToolButton()
        button.initStyleOption(option)
        arrow = button.style().subControlRect(
            QStyle.ComplexControl.CC_ToolButton, option, QStyle.SubControl.SC_ToolButtonMenu, button)
        assert arrow.width() > 0
        assert button.rect().contains(arrow.center())
        visible = []

        def close_menu():
            visible.append(widget._recent_menu.isVisible())
            widget._recent_menu.close()

        QTimer.singleShot(20, close_menu)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton, pos=arrow.center())
        QTest.qWait(30)
        assert visible == [True]
        file_dialog.assert_not_called()
    finally:
        parent.close()


@pytest.mark.parametrize("with_history", [False, True])
def test_open_below_layout_refresh_and_main_click(qapp, saved_airfoil, monkeypatch, with_history):
    current = [saved_airfoil]
    parent = QWidget()
    opened = Mock()
    widget = Airfoil_Select_Open_Widget(
        QHBoxLayout(parent), get=lambda: current[0], set=Mock(), set_open=opened,
        openBelow=True, widthOpen=90,
        recent_files=Recent_Files() if with_history else None)
    file_dialog = Mock(return_value=(saved_airfoil.pathFileName_abs, ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", file_dialog)
    try:
        parent.show()
        qapp.processEvents()
        assert widget._icon_widget is None
        assert not widget._button_widget.isHidden()
        assert not widget._combo_widget.isHidden()
        assert widget._button_widget.y() - widget._combo_widget.geometry().bottom() - 1 == 4
        assert widget._button_widget.x() == widget._combo_widget.x()
        assert widget._button_widget.width() == 90
        widget._button_widget.click()
        file_dialog.assert_called_once()
        opened.assert_called_once()
        current[0] = Example()
        widget.refresh()
        qapp.processEvents()
        assert widget._combo_widget.isHidden()
        assert not widget._button_widget.isHidden()
        current[0] = saved_airfoil
        widget.refresh()
        qapp.processEvents()
        assert not widget._combo_widget.isHidden()
        assert not widget._button_widget.isHidden()
        assert widget._button_widget.y() - widget._combo_widget.geometry().bottom() - 1 == 4
    finally:
        parent.close()


@pytest.mark.parametrize("operation", ["save_as", "rename"])
@pytest.mark.parametrize("accepted", [False, True])
def test_saved_main_airfoil_history(qapp, saved_airfoil, tmp_path, monkeypatch, operation, accepted):
    history = Recent_Files()
    old_path = saved_airfoil.pathFileName_abs
    history.add(old_path)
    new_path = tmp_path / "new.dat"
    model = SimpleNamespace(airfoil=saved_airfoil, set_airfoil=Mock())
    mode = SimpleNamespace(_app_model=model, stacked_panel=QWidget(),
                           _toast_message=Mock(), _delete_temp_files=Mock())

    def save():
        if accepted:
            saved_airfoil.set_pathFileName(str(new_path), noCheck=True)
            saved_airfoil.save()
        return accepted

    dialog = Mock(exec=Mock(side_effect=save), remove_designs=False)
    monkeypatch.setattr(app_modes, "Airfoil_Save_Dialog", Mock(return_value=dialog))
    try:
        getattr(app_modes.Mode_View, operation)(mode)
        if accepted:
            assert history.paths[0] == new_path
            assert (tmp_path / saved_airfoil.fileName).is_file()
            assert (str(history.paths[-1]) == old_path) == (operation == "save_as")
            model.set_airfoil.assert_called_once_with(saved_airfoil)
        else:
            assert [str(path) for path in history.paths] == [old_path]
            assert not new_path.exists()
            model.set_airfoil.assert_not_called()
    finally:
        mode.stacked_panel.close()


def test_failed_load_does_not_call_setter_or_add_history(qapp, saved_airfoil, tmp_path, monkeypatch):
    invalid = tmp_path / "invalid.dat"
    invalid.write_text("not an airfoil\n")
    callback = Mock()
    error = Mock()
    monkeypatch.setattr(MessageBox, "error", error)
    history = Recent_Files()
    parent, widget = selector(saved_airfoil, set=callback, set_open=callback, recent_files=history)
    try:
        widget._load_open_airfoil(invalid)
        error.assert_called_once()
        callback.assert_not_called()
        assert history.paths == []
        widget.set_airfoil(Example())
        assert history.paths == []
    finally:
        parent.close()


def test_deletion_removes_history_entry(qapp, saved_airfoil, monkeypatch):
    history = Recent_Files()
    history.add(saved_airfoil.pathFileName_abs)
    old_path = history.paths[0]
    model = SimpleNamespace(airfoil=saved_airfoil, set_airfoil=Mock())
    mode = SimpleNamespace(_app_model=model, stacked_panel=QWidget(),
                           _toast_message=Mock(), delete_temp_files=Mock())
    monkeypatch.setattr(app_modes.MessageBox, "warning",
                        Mock(return_value=app_modes.QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(app_modes.MessageBox, "info", Mock())
    monkeypatch.setattr(app_modes, "get_next_airfoil_in_dir", Mock(return_value=Example()))
    try:
        app_modes.Mode_View.delete(mode)
        assert not old_path.exists()
        assert history.paths == []
        model.set_airfoil.assert_called_once()
    finally:
        mode.stacked_panel.close()
