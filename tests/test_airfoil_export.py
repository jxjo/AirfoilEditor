#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ezdxf
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from airfoileditor.model.airfoil import Airfoil_BSpline, Airfoil_Bezier, GEO_BASIC
from airfoileditor.model.airfoil_examples import Root_Example
from airfoileditor.model.airfoil_exports import Export_Airfoil_Dxf


def _export_entity_types(airfoil, tmp_path, export_name: str) -> list[str]:
    exporter = Export_Airfoil_Dxf(airfoil)
    exporter.set_export_dir(str(tmp_path / export_name))
    path = exporter.do_it()

    doc = ezdxf.readfile(path)
    return [entity.dxftype() for entity in doc.modelspace()]


def test_export_bezier_airfoil_as_splines(tmp_path):
    seed_airfoil = Root_Example(geometry=GEO_BASIC)
    airfoil = Airfoil_Bezier.on_airfoil(seed_airfoil)

    entity_types = _export_entity_types(airfoil, tmp_path, "bezier_export")

    assert entity_types == ["SPLINE", "SPLINE", "TEXT", "TEXT"]


def test_export_bspline_airfoil_as_splines(tmp_path):
    seed_airfoil = Root_Example(geometry=GEO_BASIC)
    airfoil = Airfoil_BSpline.on_airfoil(seed_airfoil)

    entity_types = _export_entity_types(airfoil, tmp_path, "bspline_export")

    assert entity_types == ["SPLINE", "SPLINE", "TEXT", "TEXT"]


@pytest.mark.parametrize("filename, expected", [
    (None, "Root_Example.dxf"),
    ("alternate.dxf", "alternate.dxf"),
    ("alternate", "alternate.dxf"),
    ("alternate.DXF", "alternate.DXF"),
])
def test_export_filename(tmp_path, filename, expected):
    exporter = Export_Airfoil_Dxf(Root_Example(geometry=GEO_BASIC))
    exporter.set_export_dir(str(tmp_path))

    path = exporter.do_it(filename=filename)

    assert Path(path) == tmp_path / expected
    assert ezdxf.readfile(path).modelspace().query("SPLINE")


@pytest.mark.parametrize("filename", ["", "..\\outside.dxf", "invalid?.dxf"])
def test_invalid_export_filename_does_not_clear_directory(tmp_path, filename):
    marker = tmp_path / "existing.txt"
    marker.touch()
    exporter = Export_Airfoil_Dxf(Root_Example(geometry=GEO_BASIC))
    exporter.set_export_dir(str(tmp_path))
    exporter.set_clear_export_dir(True)

    with pytest.raises(ValueError):
        exporter.do_it(filename=filename)

    assert marker.exists()


def test_export_into_existing_drawing_does_not_save(tmp_path):
    exporter = Export_Airfoil_Dxf(Root_Example(geometry=GEO_BASIC))
    exporter.set_export_dir(str(tmp_path / "unused"))
    drawing = ezdxf.new()

    assert exporter.do_it(drawing=drawing, filename="ignored") is None
    assert drawing.modelspace().query("SPLINE")
    assert not (tmp_path / "unused").exists()


def test_export_dialog_passes_alternate_filename():
    from airfoileditor.ui.ae_dialogs import Airfoil_Export_DXF_Dialog

    exporter = Mock()
    exporter.do_it.return_value = "alternate.dxf"
    dialog = SimpleNamespace(export_filename="alternate", exporter_airfoil=exporter,
                             close=Mock(), _toast_message=Mock())

    Airfoil_Export_DXF_Dialog._export_dxf(dialog)

    exporter.do_it.assert_called_once_with(filename="alternate.dxf")
    dialog.close.assert_called_once()