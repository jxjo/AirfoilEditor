from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt

from airfoileditor import app


@pytest.mark.parametrize("requested", list(Qt.ColorScheme))
@pytest.mark.parametrize("effective", list(Qt.ColorScheme))
def test_window_style_resolves_system_scheme_without_overriding_explicit_choice(
        qapp, monkeypatch, requested, effective):
    applied = []
    hints = SimpleNamespace(setColorScheme=applied.append, colorScheme=lambda: effective)
    monkeypatch.setattr(app, "QGuiApplication", SimpleNamespace(styleHints=lambda: hints))
    monkeypatch.setattr(app, "Settings", lambda: {"color_scheme": requested.name})
    monkeypatch.setattr(app, "Icon", lambda **kwargs: None)
    monkeypatch.setattr(app.Widget, "light_mode", True)
    window = SimpleNamespace(setWindowIcon=lambda icon: None)

    app.Main._set_win_style(window, None, "test.png")

    expected = effective if requested == Qt.ColorScheme.Unknown else requested
    assert app.Widget.light_mode == (expected != Qt.ColorScheme.Dark)
    assert applied == [requested]
