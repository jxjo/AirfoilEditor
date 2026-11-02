import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QStyle, QStyleFactory, QStyleOptionSpinBox, QVBoxLayout, QWidget
from PyQt6.QtTest import QTest

from PyQt6.QtGui import QPalette

from airfoileditor.base.widgets import Field, FieldF, FieldI, Label, Widget, style


@pytest.fixture(params=QStyleFactory.keys())
def qt_style(qapp, request):
    previous_style = qapp.style().objectName()
    qapp.setStyle(request.param)
    try:
        yield
    finally:
        qapp.setStyle(previous_style)


@pytest.mark.parametrize("field_class", [FieldF, FieldI])
def test_spinbox_palette_refresh_is_idempotent(qapp, monkeypatch, field_class):
    window = QWidget()
    layout = QVBoxLayout(window)
    field = field_class(layout, get=12, disable=False, width=80,
                        style=style.GOOD, styleRole=QPalette.ColorRole.Base)
    try:
        window.show()
        qapp.processEvents()
        updates = []
        monkeypatch.setattr(field, "update", lambda: updates.append(True))
        palette = QPalette(field.palette())
        editor_palette = QPalette(field.lineEdit().palette())

        field.refresh()
        assert field.palette() == palette
        assert field.lineEdit().palette() == editor_palette
        assert not updates

        field.lineEdit().setAutoFillBackground(True)
        field.refresh()
        assert not field.lineEdit().autoFillBackground()
        assert field.palette() == palette
    finally:
        window.close()


@pytest.mark.parametrize("field_class", [FieldF, FieldI])
def test_spinbox_text_style_preserves_selection_and_restores_background(qapp, field_class):
    window = QWidget()
    layout = QVBoxLayout(window)
    field = field_class(layout, get=12, disable=False, width=80)
    try:
        window.show()
        qapp.processEvents()
        normal_editor = QPalette(field.lineEdit().palette())
        normal_frame = QPalette(field.palette())
        field._set_Qwidget_style_color(style.GOOD, QPalette.ColorRole.Base)
        field._set_Qwidget_style_color(style.ERROR, QPalette.ColorRole.Text)

        assert field.palette() == normal_frame
        editor_palette = field.lineEdit().palette()
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive,
                      QPalette.ColorGroup.Disabled):
            assert editor_palette.color(group, QPalette.ColorRole.Text).name() == "#ff0000"
            for role in (QPalette.ColorRole.Highlight, QPalette.ColorRole.HighlightedText):
                assert editor_palette.brush(group, role) == normal_editor.brush(group, role)
            assert editor_palette.color(group, QPalette.ColorRole.Base).alpha() == 0

        field._set_Qwidget_style_color(style.NORMAL, QPalette.ColorRole.Text)
        assert field.lineEdit().palette() == normal_editor
        assert field.palette() == normal_frame
    finally:
        window.close()


@pytest.mark.parametrize("field_class", [FieldF, FieldI])
def test_numeric_paint_adjustment_preserves_spin_button_interaction(qapp, qt_style, field_class):
    window = QWidget()
    layout = QVBoxLayout(window)
    field = field_class(layout, get=12, disable=False, step=1, width=100)
    try:
        window.show()
        qapp.processEvents()
        field.setFocus()
        option = QStyleOptionSpinBox()
        field.initStyleOption(option)
        for button, expected in ((QStyle.SubControl.SC_SpinBoxUp, 13),
                                 (QStyle.SubControl.SC_SpinBoxDown, 12)):
            rect = field.style().subControlRect(
                QStyle.ComplexControl.CC_SpinBox, option, button, field)
            QTest.mouseMove(field, rect.center())
            QTest.mousePress(field, Qt.MouseButton.LeftButton, pos=rect.center())
            assert not field.grab().isNull()
            QTest.mouseRelease(field, Qt.MouseButton.LeftButton, pos=rect.center())
            assert field.value() == expected
        assert field.height() == 24
    finally:
        window.close()


@pytest.mark.parametrize("field_class", [FieldF, FieldI])
@pytest.mark.parametrize("disabled", [False, True])
def test_numeric_field_tint_covers_frame_without_double_painting(qapp, field_class, disabled):
    previous_style = qapp.style().objectName()
    qapp.setStyle("Fusion")
    window = QWidget()
    layout = QVBoxLayout(window)
    field = field_class(layout, get=12, disable=disabled, step=1, width=80,
                        style=style.GOOD, styleRole=QPalette.ColorRole.Base)
    try:
        window.show()
        qapp.processEvents()
        editor = field.lineEdit()
        assert not editor.autoFillBackground()
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive,
                      QPalette.ColorGroup.Disabled):
            assert editor.palette().color(group, QPalette.ColorRole.Base).alpha() == 0

        image = field.grab().toImage()
        x = 10
        assert image.pixelColor(x, 2) == image.pixelColor(x, 8)
        tint = field.palette().color(QPalette.ColorRole.Base)
        field.refresh()
        assert field.palette().color(QPalette.ColorRole.Base) == tint
        field._set_Qwidget_style_color(style.NORMAL, QPalette.ColorRole.Base)
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive,
                      QPalette.ColorGroup.Disabled):
            assert field.palette().color(group, QPalette.ColorRole.Base) == field._spinbox_base_palette.color(
                group, QPalette.ColorRole.Base)
        assert field.height() == 24
    finally:
        window.close()
        qapp.setStyle(previous_style)


@pytest.mark.parametrize("dark", [False, True])
def test_label_background_is_blended_once(qapp, monkeypatch, dark):
    previous_style = qapp.style().objectName()
    previous_scheme = qapp.styleHints().colorScheme()
    qapp.setStyle("Fusion")
    qapp.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    monkeypatch.setattr(Widget, "light_mode", not dark)
    window = QWidget()
    layout = QVBoxLayout(window)
    label = Label(layout, get="Good", width=100, style=style.GOOD,
                  styleRole=QPalette.ColorRole.Window)
    try:
        window.show()
        qapp.processEvents()
        color = label.palette().color(QPalette.ColorRole.Window)
        assert color.alpha() == 255
        assert label.grab().toImage().pixelColor(90, 12) == color
        label.refresh()
        assert label.palette().color(QPalette.ColorRole.Window) == color
        label._set_Qwidget_style_color(style.NORMAL, QPalette.ColorRole.Window)
        assert label.palette().color(QPalette.ColorRole.Window) == label._palette_normal.color(
            QPalette.ColorRole.Window)
    finally:
        window.close()
        qapp.styleHints().setColorScheme(previous_scheme)
        qapp.setStyle(previous_style)


@pytest.mark.parametrize("color_style", [style.COMMENT, style.HINT, style.WARNING,
                                        style.GOOD, style.ERROR])
@pytest.mark.parametrize("disabled", [False, True])
@pytest.mark.parametrize("dark", [False, True])
def test_text_and_numeric_field_backgrounds_match(qapp, monkeypatch, color_style, disabled, dark):
    previous_style = qapp.style().objectName()
    previous_scheme = qapp.styleHints().colorScheme()
    qapp.setStyle("Fusion")
    qapp.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    monkeypatch.setattr(Widget, "light_mode", not dark)
    window = QWidget()
    layout = QVBoxLayout(window)
    fields = [cls(layout, get=12, disable=disabled, width=80,
                  style=color_style, styleRole=QPalette.ColorRole.Base)
              for cls in (Field, FieldI, FieldF)]
    try:
        window.show()
        qapp.processEvents()
        backgrounds = [field.grab().toImage().pixelColor(10, 12) for field in fields]
        assert backgrounds[0] == backgrounds[1] == backgrounds[2]
        for field in fields:
            field.refresh()
        assert [field.grab().toImage().pixelColor(10, 12) for field in fields] == backgrounds
    finally:
        window.close()
        qapp.styleHints().setColorScheme(previous_scheme)
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
            assert field.height() == field.minimumHeight() == field.maximumHeight() == 24
    finally:
        window.close()


@pytest.mark.parametrize("field_class", [FieldF, FieldI])
@pytest.mark.parametrize("disabled", [False, True])
@pytest.mark.parametrize("spin", [False, True])
@pytest.mark.parametrize("dark", [False, True])
def test_fusion_numeric_field_paints_full_height(qapp, monkeypatch, field_class,
                                                disabled, spin, dark):
    previous_style = qapp.style().objectName()
    previous_scheme = qapp.styleHints().colorScheme()
    qapp.setStyle("Fusion")
    qapp.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    monkeypatch.setattr(Widget, "light_mode", not dark)
    window = QWidget()
    layout = QVBoxLayout(window)
    field = field_class(layout, get=12, disable=disabled,
                        step=1 if spin else None, width=80)
    try:
        window.show()
        qapp.processEvents()
        geometry = field.geometry()
        editor_geometry = field.lineEdit().geometry()
        layout_minimum = layout.minimumSize()

        image = field.grab().toImage()
        x = image.width() // 2
        assert image.pixelColor(x, 0) == image.pixelColor(x, image.height() - 1)
        assert image.pixelColor(x, 0) != window.palette().window().color()
        assert field.height() == 24
        assert field.geometry() == geometry
        assert field.lineEdit().geometry() == editor_geometry
        assert layout.minimumSize() == layout_minimum
    finally:
        window.close()
        qapp.styleHints().setColorScheme(previous_scheme)
        qapp.setStyle(previous_style)
