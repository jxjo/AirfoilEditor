#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ezdxf

from airfoileditor.model.airfoil import Airfoil_BSpline, Airfoil_Bezier, GEO_BASIC
from airfoileditor.model.airfoil_examples import Root_Example
from airfoileditor.model.airfoil_exports import Export_Airfoil


def _export_entity_types(airfoil, tmp_path, export_name: str) -> list[str]:
    exporter = Export_Airfoil(airfoil)
    exporter.set_export_dir(str(tmp_path / export_name))
    path = exporter.do_it()

    doc = ezdxf.readfile(path)
    return [entity.dxftype() for entity in doc.modelspace()]


def test_export_dat_airfoil_as_polyline(tmp_path):
    airfoil = Root_Example(geometry=GEO_BASIC)
    entity_types = _export_entity_types(airfoil, tmp_path, "dat_export")

    assert entity_types == ["LWPOLYLINE"]


def test_export_bezier_airfoil_as_splines(tmp_path):
    seed_airfoil = Root_Example(geometry=GEO_BASIC)
    airfoil = Airfoil_Bezier.on_airfoil(seed_airfoil)

    entity_types = _export_entity_types(airfoil, tmp_path, "bezier_export")

    assert entity_types == ["SPLINE", "SPLINE"]


def test_export_bspline_airfoil_as_splines(tmp_path):
    seed_airfoil = Root_Example(geometry=GEO_BASIC)
    airfoil = Airfoil_BSpline.on_airfoil(seed_airfoil)

    entity_types = _export_entity_types(airfoil, tmp_path, "bspline_export")

    assert entity_types == ["SPLINE", "SPLINE"]