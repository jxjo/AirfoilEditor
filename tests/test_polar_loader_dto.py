#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pytest

from airfoileditor.model.polar_dto import (
    Polar_Bubble_Range,
    Polar_Data_Row,
    Polar_Data_Set,
    Polar_File_Meta,
)
from airfoileditor.model.polar_set import Polar
from airfoileditor.model.xo2_driver import XfoilPolarParser


def _write_polar_file(path, body: str):
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_xfoil_parser_reads_header_and_basic_rows(tmp_path):
    file_path = _write_polar_file(
        tmp_path / "basic.txt",
        "\n".join(
            [
                "Calculated polar for: TEST_AIRFOIL",
                "",
                "Re = 0.500 e 6     Ncrit = 7.0     Mach = 0.03",
                "",
                " alpha    CL       CD      CDp      CM    Top_Xtr Bot_Xtr",
                " ------- ------- -------- -------- ------- ------- -------",
                "  0.000  0.1000  0.01000  0.00500 -0.0200  0.7000  0.8000",
                "  1.000  0.2000  0.01100  0.00550 -0.0300  0.6500  0.7800",
            ]
        ),
    )

    data_set = XfoilPolarParser.parse_file(file_path)

    assert data_set.meta.source == "xfoil"
    assert data_set.meta.airfoil_name == "TEST_AIRFOIL"
    assert data_set.meta.re == 500000.0
    assert data_set.meta.ncrit == 7.0
    assert data_set.meta.ma == 0.03
    assert len(data_set.rows) == 2
    assert data_set.rows[0].cdp == 0.005


def test_xfoil_parser_reads_cp_min_variant(tmp_path):
    file_path = _write_polar_file(
        tmp_path / "cpmin.txt",
        "\n".join(
            [
                "Calculated polar for: TEST_AIRFOIL",
                "",
                "Re = 0.500 e 6     Ncrit = 7.0",
                "",
                " alpha    CL       CD      CDp      CM    Top_Xtr Bot_Xtr Cpmin",
                " ------- ------- -------- -------- ------- ------- ------- -------",
                "  0.000  0.1000  0.01000  0.00500 -0.0200  0.7000  0.8000 -0.4500",
            ]
        ),
    )

    data_set = XfoilPolarParser.parse_file(file_path)

    assert len(data_set.rows) == 1
    assert data_set.rows[0].cp_min == -0.45
    assert data_set.rows[0].bubble_top is None
    assert data_set.rows[0].bubble_bot is None


def test_xfoil_parser_reads_legacy_bubble_variant(tmp_path):
    file_path = _write_polar_file(
        tmp_path / "bubble_legacy.txt",
        "\n".join(
            [
                "Calculated polar for: TEST_AIRFOIL",
                "",
                "Re = 0.500 e 6     Ncrit = 7.0",
                "",
                " alpha    CL       CD      CDp      CM    Top_Xtr Bot_Xtr bts bte bbs bbe",
                " ------- ------- -------- -------- ------- ------- ------- ---- ---- ---- ----",
                "  0.000  0.1000  0.01000  0.00500 -0.0200  0.7000  0.8000 0.20 0.30 0.40 0.50",
            ]
        ),
    )

    data_set = XfoilPolarParser.parse_file(file_path)

    row = data_set.rows[0]
    assert row.cp_min is None
    assert row.bubble_top == Polar_Bubble_Range(0.2, 0.3)
    assert row.bubble_bot == Polar_Bubble_Range(0.4, 0.5)


def test_xfoil_parser_reads_extended_bubble_variant(tmp_path):
    file_path = _write_polar_file(
        tmp_path / "bubble_extended.txt",
        "\n".join(
            [
                "Calculated polar for: TEST_AIRFOIL",
                "",
                "Re = 0.500 e 6     Ncrit = 7.0",
                "",
                " alpha    CL       CD      CDp      CM    Top_Xtr Bot_Xtr Cpmin bts bte bbs bbe",
                " ------- ------- -------- -------- ------- ------- ------- ----- ---- ---- ---- ----",
                "  0.000  0.1000  0.01000  0.00500 -0.0200  0.7000  0.8000 -0.55 0.21 0.31 0.41 0.51",
            ]
        ),
    )

    data_set = XfoilPolarParser.parse_file(file_path)

    row = data_set.rows[0]
    assert row.cp_min == -0.55
    assert row.bubble_top == Polar_Bubble_Range(0.21, 0.31)
    assert row.bubble_bot == Polar_Bubble_Range(0.41, 0.51)


def test_polar_import_from_data_set_maps_rows_to_points():
    polar = Polar(mypolarSet=None)
    polar.set_re(500000)
    polar.set_ncrit(7.0)

    data_set = Polar_Data_Set(
        meta=Polar_File_Meta(source="xfoil", re=500000.0, ncrit=7.0),
        rows=[
            Polar_Data_Row(
                alpha=0.0,
                cl=0.1,
                cd=0.01,
                cdp=0.005,
                cm=-0.02,
                xtrt=0.7,
                xtrb=0.8,
                cp_min=-0.45,
                bubble_top=Polar_Bubble_Range(0.2, 0.3),
                bubble_bot=Polar_Bubble_Range(0.4, 0.5),
            )
        ],
    )

    polar._import_from_data_set(data_set)

    assert len(polar.polar_points) == 1
    op = polar.polar_points[0]
    assert op.alpha == 0.0
    assert op.cl == 0.1
    assert op.cd == 0.01
    assert op.cdp == 0.005
    assert op.cm == -0.02
    assert op.xtrt == 0.7
    assert op.xtrb == 0.8
    assert op.cp_min == -0.45
    assert op.bubble_top == (0.2, 0.3)
    assert op.bubble_bot == (0.4, 0.5)


def test_polar_import_from_data_set_validates_re():
    polar = Polar(mypolarSet=None)
    polar.set_re(500000)
    polar.set_ncrit(7.0)

    data_set = Polar_Data_Set(
        meta=Polar_File_Meta(source="xfoil", re=400000.0, ncrit=7.0),
        rows=[
            Polar_Data_Row(
                alpha=0.0,
                cl=0.1,
                cd=0.01,
                cdp=0.005,
                cm=-0.02,
                xtrt=0.7,
                xtrb=0.8,
            )
        ],
    )

    with pytest.raises(RuntimeError, match="Re Number"):
        polar._import_from_data_set(data_set)


def test_polar_import_from_data_set_validates_ncrit():
    polar = Polar(mypolarSet=None)
    polar.set_re(500000)
    polar.set_ncrit(7.0)

    data_set = Polar_Data_Set(
        meta=Polar_File_Meta(source="xfoil", re=500000.0, ncrit=8.0),
        rows=[
            Polar_Data_Row(
                alpha=0.0,
                cl=0.1,
                cd=0.01,
                cdp=0.005,
                cm=-0.02,
                xtrt=0.7,
                xtrb=0.8,
            )
        ],
    )

    with pytest.raises(RuntimeError, match="Ncrit"):
        polar._import_from_data_set(data_set)
