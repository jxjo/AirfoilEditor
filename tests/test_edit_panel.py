import pytest
from PyQt6.QtWidgets import QLabel, QVBoxLayout

from airfoileditor.base.panels import Edit_Panel
from airfoileditor.base.widgets import CheckBox


@pytest.mark.parametrize("initial_state", [True, False])
def test_switchable_edit_panel_checkbox_controls_linked_diagram(qapp, initial_state):
    content = QLabel("Panel content")
    layout = QVBoxLayout()
    layout.addWidget(content)
    diagram_state = {"visible": initial_state}
    panel = Edit_Panel(title="Test panel", layout=layout, switchable=True,
                       switched_on=initial_state,
                       on_switched=lambda switched_on: diagram_state.__setitem__("visible", switched_on))

    checkbox = next(widget for widget in panel.header_widgets if isinstance(widget, CheckBox))
    assert panel._head.layout().itemAt(0).widget() is checkbox
    assert checkbox.text() == "Test panel"
    assert checkbox.isChecked() is initial_state
    assert panel._panel.isHidden() is not initial_state
    if initial_state:
        assert panel.maximumHeight() > 35
    else:
        assert panel.maximumHeight() == 35

    checkbox.click()

    switched_state = not initial_state
    assert panel.switched_on is switched_state
    assert panel._panel.isHidden() is not switched_state
    assert checkbox.isChecked() is switched_state
    assert diagram_state["visible"] is switched_state

    panel.set_switched_on(initial_state)
    assert checkbox.isChecked() is initial_state
    assert diagram_state["visible"] is initial_state


def test_switchable_edit_panel_checkbox_tracks_callable_state(qapp):
    state = {"open": True}
    layout = QVBoxLayout()
    layout.addWidget(QLabel("Panel content"))
    panel = Edit_Panel(title="Test panel", layout=layout, switchable=True,
                       switched_on=lambda: state["open"],
                       on_switched=lambda switched_on: state.__setitem__("open", switched_on))

    checkbox = next(widget for widget in panel.header_widgets if isinstance(widget, CheckBox))
    checkbox.click()

    assert panel.switched_on is False
    assert checkbox.isChecked() is False
    assert state["open"] is False
