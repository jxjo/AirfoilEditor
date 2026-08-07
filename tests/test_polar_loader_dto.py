#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pytest

from airfoileditor.model.polar_dto import (
    Polar_Bubble_Range,
    Polar_Data_Row,
    Polar_Data_Set,
    Polar_File_Meta,
)
from airfoileditor.model.airfoil import Flap_Definition
from airfoileditor.model.polar_set import Polar, var
from airfoileditor.model.xo2_driver import Xfoil_Polar_Parser


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

    data_set = Xfoil_Polar_Parser.parse_file(file_path)

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

    data_set = Xfoil_Polar_Parser.parse_file(file_path)

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

    data_set = Xfoil_Polar_Parser.parse_file(file_path)

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

    data_set = Xfoil_Polar_Parser.parse_file(file_path)

    row = data_set.rows[0]
    assert row.cp_min == -0.55
    assert row.bubble_top == Polar_Bubble_Range(0.21, 0.31)
    assert row.bubble_bot == Polar_Bubble_Range(0.41, 0.51)


def test_polar_import_from_data_set_uses_dto_arrays_and_point_views():
    polar = Polar(mypolarSet=None)
    polar.set_re(500000)
    polar.set_ncrit(7.0)

    data_set = Polar_Data_Set(
        meta=Polar_File_Meta(source="xfoil", re=500000.0, ma=0.0, ncrit=7.0, polar_type="T1"),
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

    assert list(polar.alpha) == [0.0]
    assert list(polar.cl) == [0.1]
    assert list(polar.cd) == [0.01]
    assert list(polar.cdp) == [0.005]
    assert list(polar.cdf) == [0.005]

    op = polar.point_at(0)
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


def test_polar_point_at_returns_one_point_view():
    polar = Polar(mypolarSet=None)
    polar.set_re(500000)
    polar.set_ncrit(7.0)

    data_set = Polar_Data_Set(
        meta=Polar_File_Meta(source="xfoil", re=500000.0, ma=0.0, ncrit=7.0, polar_type="T1"),
        rows=[
            Polar_Data_Row(alpha=0.0, cl=0.1, cd=0.01, cdp=0.005, cm=-0.02, xtrt=0.7, xtrb=0.8),
            Polar_Data_Row(alpha=1.0, cl=0.2, cd=0.02, cdp=0.006, cm=-0.03, xtrt=0.6, xtrb=0.7),
        ],
    )

    polar._import_from_data_set(data_set)

    op = polar.point_at(1)

    assert op is not None
    assert op.alpha == 1.0
    assert op.cl == 0.2


def test_polar_bubble_access_stays_array_backed():
    polar = Polar(mypolarSet=None)
    polar.set_re(500000)
    polar.set_ncrit(7.0)

    data_set = Polar_Data_Set(
        meta=Polar_File_Meta(source="xfoil", re=500000.0, ma=0.0, ncrit=7.0, polar_type="T1"),
        rows=[
            Polar_Data_Row(
                alpha=0.0,
                cl=0.1,
                cd=0.01,
                cdp=0.005,
                cm=-0.02,
                xtrt=0.7,
                xtrb=0.8,
                bubble_top=Polar_Bubble_Range(0.2, 0.73),
                bubble_bot=Polar_Bubble_Range(0.4, 0.5),
            )
        ],
    )

    polar._import_from_data_set(data_set)

    assert polar.has_bubble_top is True
    assert polar.has_bubble_bot is True
    assert tuple(polar.bubble_top[0]) == (0.2, 0.73)
    assert polar.is_bubble_top_turbulent_separated_at(0)
    assert not polar.is_bubble_bot_turbulent_separated_at(0)


def test_get_interpolated_point_returns_point_view():
    polar = Polar(mypolarSet=None)
    polar.set_re(500000)
    polar.set_ncrit(7.0)

    data_set = Polar_Data_Set(
        meta=Polar_File_Meta(source="xfoil", re=500000.0, ma=0.0, ncrit=7.0, polar_type="T1"),
        rows=[
            Polar_Data_Row(alpha=0.0, cl=0.1, cd=0.01, cdp=0.005, cm=-0.02, xtrt=0.7, xtrb=0.8),
            Polar_Data_Row(alpha=1.0, cl=0.2, cd=0.02, cdp=0.006, cm=-0.03, xtrt=0.6, xtrb=0.7),
        ],
    )

    polar._import_from_data_set(data_set)

    op = polar.get_interpolated_point(var.ALPHA, 0.5)

    assert op is not None
    assert op.alpha == 0.5
    assert op.cl == 0.15
    assert op.cd == 0.015
    assert op.cdp == 0.006
    assert op.cm == -0.025
    assert op.xtrt == 0.65
    assert op.xtrb == 0.75


def test_polar_import_from_data_set_allows_missing_optional_flap_meta():
    polar = Polar(mypolarSet=None)
    polar.set_re(500000)
    polar.set_ncrit(7.0)

    flap = Flap_Definition()
    flap.set_flap_angle(2.2)
    flap.set_x_flap(0.75)
    flap.set_y_flap(0.0)
    polar.set_flap_def(flap)

    data_set = Polar_Data_Set(
        meta=Polar_File_Meta(source="xfoil", re=500000.0, ma=0.0, ncrit=7.0, polar_type="T1"),
        rows=[
            Polar_Data_Row(alpha=0.0, cl=0.1, cd=0.01, cdp=0.005, cm=-0.02, xtrt=0.7, xtrb=0.8),
        ],
    )

    polar._import_from_data_set(data_set)

    assert list(polar.cl) == [0.1]


def test_polar_import_from_data_set_validates_re():
    polar = Polar(mypolarSet=None)
    polar.set_re(500000)
    polar.set_ncrit(7.0)

    data_set = Polar_Data_Set(
        meta=Polar_File_Meta(source="xfoil", re=400000.0, ma=0.0, ncrit=7.0, polar_type="T1"),
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

    with pytest.raises(RuntimeError, match="Re 500000"):
        polar._import_from_data_set(data_set)


def test_polar_import_from_data_set_validates_ncrit():
    polar = Polar(mypolarSet=None)
    polar.set_re(500000)
    polar.set_ncrit(7.0)

    data_set = Polar_Data_Set(
        meta=Polar_File_Meta(source="xfoil", re=500000.0, ma=0.0, ncrit=8.0, polar_type="T1"),
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
