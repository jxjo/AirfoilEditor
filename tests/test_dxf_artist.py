#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Lean tests for airfoileditor.base.dxf_artist."""

from pathlib import Path

import pytest

from airfoileditor.base.dxf_artist import (
    Cad_Line,
    Cad_PolyLine,
    Cad_Spline,
    Cad_Text,
    Dxf_Artist,
)
from airfoileditor.base.spline import Bezier


class Dummy_Artist(Dxf_Artist):
    def plot(self, **kwargs):
        return


def test_cad_line_requires_two_points():
    with pytest.raises(ValueError, match="exactly two points"):
        Cad_Line([(0.0, 0.0)])


def test_cad_polyline_requires_at_least_two_points():
    with pytest.raises(ValueError, match="at least two points"):
        Cad_PolyLine([(0.0, 0.0)])


def test_entities_add_to_modelspace():
    artist = Dummy_Artist()

    Cad_Line.from_x_y([0.0, 10.0], [0.0, 5.0]).add_to(artist.msp)
    Cad_PolyLine.from_x_y([0.0, 5.0, 10.0], [0.0, 2.0, 0.0]).add_to(artist.msp)

    bezier = Bezier([0.0, 5.0, 10.0], [0.0, 3.0, 0.0])
    Cad_Spline.from_bezier(bezier).add_to(artist.msp)

    Cad_Text("DXF", (1.0, 1.0), 2.5).add_to(artist.msp)

    assert len(artist.msp.query("LINE")) == 1
    assert len(artist.msp.query("LWPOLYLINE")) == 1
    assert len(artist.msp.query("SPLINE")) == 1
    assert len(artist.msp.query("TEXT")) == 1


def test_artist_save_writes_file(tmp_path: Path):
    artist = Dummy_Artist()
    out_file = tmp_path / "artist_test.dxf"

    artist.save(str(out_file))

    assert out_file.exists()
    assert out_file.stat().st_size > 0
