from unittest.mock import Mock

import pytest

from airfoileditor.ui import ae_panels
from airfoileditor.ui.ae_panels import Panel_File_View, Panel_File_View_Small

HELP_ENTRIES = [("Readme", "https://github.com/jxjo/AirfoilEditor"),
                ("About Version 5.0", "https://github.com/jxjo/AirfoilEditor/blob/main/doc/ABOUT_5.0.md"),
                ("Releases", "https://github.com/jxjo/AirfoilEditor/releases")]


@pytest.fixture(params=[Panel_File_View, Panel_File_View_Small])
def panel(request, qapp):
    panel = request.param(None, Mock(), lazy=True, has_head=False)
    yield panel
    panel.deleteLater()


def texts(menu):
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def help_menu(menu):
    actions = [action for action in menu.actions() if action.menu() is not None]
    assert [action.text() for action in actions] == ["Help on Github"]
    return actions[0].menu()


def test_more_menu_has_one_help_submenu_instead_of_github_entries(panel):
    menu = panel._more_menu()
    assert "Readme on Github" not in texts(menu)
    assert "Releases on Github" not in texts(menu)
    assert [text for text, _ in HELP_ENTRIES] == texts(help_menu(menu))


def test_more_menu_keeps_its_other_entries(panel):
    entries = texts(panel._more_menu())
    for text in ("As Bezier based", "As B-Spline based", "As CST based", "Optimize...", "Save as...",
                 "Export DXF...", "Rename...", "Delete", "Delete temp files"):
        assert text in entries
    assert entries.index("Help on Github") == len(entries) - 1
    assert (entries[0] == "&Modify") == isinstance(panel, Panel_File_View_Small)


def test_help_entries_have_tooltips(panel):
    menu = panel._more_menu()                       # keep the parent alive - it owns the submenu
    submenu = help_menu(menu)
    assert submenu.toolTipsVisible()
    assert all(action.toolTip() for action in submenu.actions())


@pytest.mark.parametrize("text, url", HELP_ENTRIES)
def test_help_entries_open_their_page(panel, monkeypatch, text, url):
    open_url = Mock()
    monkeypatch.setattr(ae_panels.QDesktopServices, "openUrl", open_url)
    menu = panel._more_menu()
    action = next(a for a in help_menu(menu).actions() if a.text() == text)
    action.trigger()
    open_url.assert_called_once()
    assert open_url.call_args.args[0].toString() == url
