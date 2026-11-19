#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math

import ezdxf
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from airfoileditor.base.dxf_artist import DASHED_LINETYPE
from airfoileditor.model.airfoil import Airfoil_BSpline, Airfoil_Bezier, GEO_BASIC
from airfoileditor.model.airfoil_examples import Root_Example
from airfoileditor.model.airfoil_exports import Dxf_Airfoil_Artist, Export_Airfoil_Dxf


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


def _artist_texts(**kwargs) -> tuple[list, list]:
    """ plot a 200 mm airfoil at (10, 20) and return its TEXT and SPLINE entities - texts from bottom to top"""

    artist = Dxf_Airfoil_Artist(Root_Example(geometry=GEO_BASIC), chord_mm=200.0, xy_pos_mm=(10.0, 20.0), **kwargs)
    artist.plot()
    return list(artist.msp.query("TEXT")), list(artist.msp.query("SPLINE"))


def test_blended_airfoil_is_dashed_with_third_text_line():
    texts, splines = _artist_texts(is_blended=True)

    assert len(texts) == 3
    assert texts[0].dxf.text == Dxf_Airfoil_Artist.TEXT_BLENDED
    assert splines and all(s.dxf.linetype == DASHED_LINETYPE for s in splines)
    assert all(s.dxf.ltscale == pytest.approx(2.0) for s in splines)            # chord 200 mm / 100 mm


def test_normal_airfoil_is_solid_with_two_text_lines():
    texts, splines = _artist_texts()

    assert len(texts) == 2
    assert all(s.dxf.linetype != DASHED_LINETYPE for s in splines)


def test_text_keeps_gap_to_airfoil():
    texts, _ = _artist_texts()

    assert texts[0].dxf.insert.x == pytest.approx(10.0)
    assert texts[0].dxf.insert.y == pytest.approx(20.0 + Dxf_Airfoil_Artist.TEXT_GAP * 200.0)


@pytest.mark.parametrize("angle", [0.0, 30.0, 45.0])
def test_text_lines_stay_aligned_when_rotated(angle):
    texts, _ = _artist_texts(is_blended=True, text_angle=angle)
    a = math.radians(angle)

    along  = [t.dxf.insert.x * math.cos(a) + t.dxf.insert.y * math.sin(a) for t in texts]
    across = [-t.dxf.insert.x * math.sin(a) + t.dxf.insert.y * math.cos(a) for t in texts]

    assert along == pytest.approx([along[0]] * 3, abs=1e-6)                     # all lines start at the same position
    assert across == sorted(across) and len(set(across)) == 3                   # stacked perpendicular to the text
    assert all(t.dxf.rotation == pytest.approx(angle) for t in texts)


def test_export_dialog_passes_alternate_filename():
    from airfoileditor.ui.ae_dialogs import Airfoil_Export_DXF_Dialog

    exporter = Mock()
    exporter.do_it.return_value = "alternate.dxf"
    dialog = SimpleNamespace(export_filename="alternate", exporter_airfoil=exporter,
                             close=Mock(), _toast_message=Mock())

    Airfoil_Export_DXF_Dialog._export_dxf(dialog)

    exporter.do_it.assert_called_once_with(filename="alternate.dxf")
    dialog.close.assert_called_once()