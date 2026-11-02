import pytest
from PyQt6.QtWidgets import QStyleFactory, QVBoxLayout, QWidget

from airfoileditor.base.widgets import FieldF, FieldI, Widget


@pytest.fixture(params=QStyleFactory.keys())
def qt_style(qapp, request):
    previous_style = qapp.style().objectName()
    qapp.setStyle(request.param)
    try:
        yield
    finally:
        qapp.setStyle(previous_style)


@pytest.mark.parametrize("field_class", [FieldF, FieldI])
@pytest.mark.parametrize("disabled", [False, True])
@pytest.mark.parametrize("spin", [False, True])
@pytest.mark.parametrize("light_mode", [False, True])
def test_numeric_field_text_area(qapp, qt_style, monkeypatch, field_class, disabled, spin, light_mode):
    monkeypatch.setattr(Widget, "light_mode", light_mode)
    window = QWidget()
    layout = QVBoxLayout(window)
    disabled_state = {"value": disabled}
    field = field_class(layout, get=12, disable=lambda: disabled_state["value"],
                        step=1 if spin else None, width=80)
    try:
        window.show()
        qapp.processEvents()

        for state in (disabled, not disabled):
            disabled_state["value"] = state
            field.refresh()
            qapp.processEvents()

            editor = field.lineEdit()
            text_rect = editor.geometry()
            assert field.value() == 12
            assert editor.text() == field.text()
            assert editor.isEnabled() == (not state)
            assert text_rect.left() > 0
            margins = editor.textMargins()
            available_width = editor.contentsRect().width() - margins.left() - margins.right() - 4
            assert available_width >= editor.fontMetrics().horizontalAdvance(editor.text())
            assert field.rect().contains(text_rect)
    finally:
        window.close()
