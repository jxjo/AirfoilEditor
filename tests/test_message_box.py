from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox, QWidget

from airfoileditor.base import panels


@pytest.mark.parametrize("platform", ["darwin", "win32", "linux"])
def test_message_box_disables_native_dialog_only_on_macos(qapp, monkeypatch, platform):
    monkeypatch.setattr(panels, "sys", SimpleNamespace(platform=platform))
    parent = QWidget()
    message = panels.MessageBox(parent, "Test", "Test message", panels.Icon(panels.Icon.INFO))
    try:
        assert message.testOption(QMessageBox.Option.DontUseNativeDialog) == (platform == "darwin")
        assert message.windowTitle() == "Test"
        assert message.text() == "Test message"
    finally:
        message.close()
        parent.close()


@pytest.mark.parametrize("button", [QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Cancel])
def test_macos_confirmation_preserves_button_result(qapp, monkeypatch, button):
    monkeypatch.setattr(panels, "sys", SimpleNamespace(platform="darwin"))
    parent = QWidget()

    def click_button():
        message = next(child for child in parent.children() if isinstance(child, panels.MessageBox))
        assert message.testOption(QMessageBox.Option.DontUseNativeDialog)
        assert message.defaultButton() == message.button(QMessageBox.StandardButton.Ok)
        message.button(button).click()

    QTimer.singleShot(0, click_button)
    try:
        assert panels.MessageBox.confirm(parent, "Confirm", "Continue?") == button
    finally:
        parent.close()
