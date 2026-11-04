import pytest
from PyQt6.QtWidgets import QWidget

from airfoileditor.base.panels import Disabled_Overlay


@pytest.mark.parametrize("enabled", [True, False])
def test_overlay_follows_parent_resize(qapp, enabled):
    parent = QWidget()
    parent.resize(640, 480)
    parent.show()
    overlay = Disabled_Overlay(parent, text_to_show="Editor running")
    parent.setEnabled(enabled)
    qapp.processEvents()

    try:
        assert overlay.geometry() == parent.rect()
        for width, height in [(900, 600), (400, 300), (1200, 800)]:
            parent.resize(width, height)
            qapp.processEvents()

            assert overlay.geometry() == parent.rect()
            center = overlay._label.geometry().center()
            assert abs(center.x() - overlay.rect().center().x()) <= 1
            assert abs(center.y() - overlay.rect().center().y()) <= 1
            assert parent.isEnabled() == enabled
    finally:
        parent.close()
        parent.deleteLater()
