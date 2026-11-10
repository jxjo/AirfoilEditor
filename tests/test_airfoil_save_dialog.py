from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QDialog, QWidget

from airfoileditor.model.airfoil_examples import Root_Example
from airfoileditor.ui.util_dialogs import Airfoil_Save_Dialog, MessageBox


@pytest.mark.parametrize("filename", ["", " ", "CON.dat", "bad?.dat", "..\\outside.dat"])
def test_invalid_filename_keeps_airfoil_unchanged(qapp, monkeypatch, tmp_path, filename):
    airfoil = Root_Example()
    airfoil.set_pathName(str(tmp_path))
    original_path = airfoil.pathFileName
    original_name = airfoil.name
    save = Mock()
    monkeypatch.setattr(airfoil, "save", save)
    error = Mock()
    monkeypatch.setattr(MessageBox, "error", error)
    parent = QWidget()
    dialog = Airfoil_Save_Dialog(parent, airfoil)
    try:
        dialog.airfoil.set_name("Changed")
        dialog.set_filename(filename)
        dialog.accept()
        error.assert_called_once()
        save.assert_not_called()
        assert airfoil.pathFileName == original_path
        assert airfoil.name == original_name
        assert dialog.result() != QDialog.DialogCode.Accepted
    finally:
        dialog.close()


def test_valid_filename_is_normalized_and_saved(qapp, monkeypatch, tmp_path):
    airfoil = Root_Example()
    airfoil.set_pathName(str(tmp_path))
    save = Mock()
    monkeypatch.setattr(airfoil, "save", save)
    parent = QWidget()
    dialog = Airfoil_Save_Dialog(parent, airfoil)
    try:
        dialog.set_filename("  New foil  ")
        dialog._use_filename()
        dialog.accept()
        assert airfoil.fileName == "New foil.dat"
        save.assert_called_once()
        assert dialog.result() == QDialog.DialogCode.Accepted
    finally:
        dialog.close()


def test_use_name_updates_filename(qapp):
    parent = QWidget()
    dialog = Airfoil_Save_Dialog(parent, Root_Example())
    try:
        dialog.airfoil.set_name("New name")
        dialog._use_name()
        assert dialog.filename == "New name.dat"
        assert dialog._names_are_equal()
    finally:
        dialog.close()
