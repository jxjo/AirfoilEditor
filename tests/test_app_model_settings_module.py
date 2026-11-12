import json
from pathlib import Path

import pytest

from airfoileditor.app_model_settings import (
    Airfoil_Settings, Reference_Entry, load_reference_airfoil, read_paneling, read_polar_definitions,
    read_reference_entries, settings_for, write_paneling, write_polar_definitions, write_reference_airfoils)
from airfoileditor.base.app_utils import Settings
from airfoileditor.model.airfoil import Airfoil
from airfoileditor.model.airfoil_examples import Root_Example
from airfoileditor.model.geometry_bezier import Paneling_Bezier
from airfoileditor.model.geometry_bspline import Paneling_BSpline
from airfoileditor.model.geometry_cst import Paneling_CST
from airfoileditor.model.geometry_spline import Paneling_Spline
from airfoileditor.model.polar_set import Polar_Definition


PANELING = {"spline": Paneling_Spline, "bezier": Paneling_Bezier, "bspline": Paneling_BSpline, "cst": Paneling_CST}


@pytest.fixture(autouse=True)
def restore_paneling(monkeypatch):
    for cls in PANELING.values():
        for name in ("_nPanels", "_le_bunch", "_te_bunch"):
            monkeypatch.setattr(cls, name, getattr(cls, name))


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "app.settings"
    monkeypatch.setattr(Settings, "_pathFileName", str(path))
    return path


def saved_airfoil(directory, name="current"):
    example = Root_Example()
    example.set_pathName(str(directory))
    example.set_fileName(name + ".dat")
    example.save()
    airfoil = Airfoil.onFileType(example.pathFileName_abs)
    airfoil.load()
    return airfoil


def polar_def(re):
    definition = Polar_Definition()
    definition.set_re(re)
    return definition


# ---- where settings live


def test_airfoil_settings_file_lives_next_to_the_airfoil(tmp_path):
    airfoil = saved_airfoil(tmp_path)
    expected = tmp_path / "current.ae"
    assert Path(Airfoil_Settings.settings_pathFileName(airfoil)) == expected
    assert not Airfoil_Settings.exists_for(airfoil)
    expected.write_text("{}")
    assert Airfoil_Settings.exists_for(airfoil)
    assert Path(Airfoil_Settings(airfoil).pathFileName) == expected


@pytest.mark.parametrize("not_an_airfoil", [None, "current.dat", object()])
def test_airfoil_settings_need_an_airfoil(not_an_airfoil):
    assert not Airfoil_Settings.exists_for(not_an_airfoil)
    with pytest.raises(ValueError):
        Airfoil_Settings(not_an_airfoil)


def test_settings_for_prefers_the_individual_file(tmp_path, settings_file):
    airfoil = saved_airfoil(tmp_path)
    assert not isinstance(settings_for(airfoil), Airfoil_Settings)
    assert not isinstance(settings_for(None), Airfoil_Settings)
    (tmp_path / "current.ae").write_text("{}")
    assert isinstance(settings_for(airfoil), Airfoil_Settings)
    assert not isinstance(settings_for(None), Airfoil_Settings)


# ---- reference airfoils


def test_reference_entries_understand_old_and_new_format(settings_file):
    s = Settings()
    s["reference_airfoils"] = ["old.dat", {"path": "new.dat"}, {"path": "own.dat", "show": False, "scale": 1.5}]
    assert read_reference_entries(s) == [Reference_Entry("old.dat", True, None),
                                         Reference_Entry("new.dat", True, None),
                                         Reference_Entry("own.dat", False, 1.5)]


def test_reference_entries_skip_what_has_no_path(settings_file):
    s = Settings()
    s["reference_airfoils"] = [{"show": False}, 42, None, {"path": None}, {"path": "ok.dat"}]
    assert read_reference_entries(s) == [Reference_Entry("ok.dat", True, None)]


def test_reference_entries_of_empty_settings(settings_file):
    assert read_reference_entries(Settings()) == []


def test_load_reference_airfoil_applies_show_and_scale(tmp_path):
    saved_airfoil(tmp_path, "ref")
    airfoil = load_reference_airfoil(Reference_Entry(str(tmp_path / "ref.dat"), False, 1.25))
    assert airfoil.isLoaded
    assert airfoil.get_property("show", True) is False
    assert airfoil.scale_factor == 1.25
    default = load_reference_airfoil(Reference_Entry(str(tmp_path / "ref.dat")))
    assert default.get_property("show", False) is True
    assert default.scale_factor == 1.0


def test_load_reference_airfoil_raises_for_a_missing_file(tmp_path):
    with pytest.raises(Exception):
        load_reference_airfoil(Reference_Entry(str(tmp_path / "missing.dat")))


def test_write_reference_airfoils_stores_only_non_defaults(tmp_path, settings_file):
    plain, hidden, scaled = (saved_airfoil(tmp_path, name) for name in ("plain", "hidden", "scaled"))
    hidden.set_property("show", False)
    scaled.set_scale_factor(2.0)
    s = Settings()
    write_reference_airfoils(s, [plain, hidden, scaled])
    assert s["reference_airfoils"] == [
        {"path": plain.pathFileName_abs},
        {"path": hidden.pathFileName_abs, "show": False},
        {"path": scaled.pathFileName_abs, "scale": 2.0}]


def test_write_then_read_reference_airfoils_roundtrip(tmp_path, settings_file):
    ref = saved_airfoil(tmp_path, "ref")
    ref.set_property("show", False)
    ref.set_scale_factor(1.5)
    s = Settings()
    write_reference_airfoils(s, [ref])
    s.save()
    entries = read_reference_entries(Settings())
    assert entries == [Reference_Entry(ref.pathFileName_abs, False, 1.5)]


def test_write_no_reference_airfoils_removes_the_key(settings_file):
    s = Settings()
    s["reference_airfoils"] = [{"path": "old.dat"}]
    write_reference_airfoils(s, [])
    assert "reference_airfoils" not in s


# ---- polar definitions


def test_read_polar_definitions_sorted_by_re(settings_file):
    s = Settings()
    s["polar_definitions"] = [polar_def(500000)._as_dict(), polar_def(100000)._as_dict()]
    assert [d.re for d in read_polar_definitions(s)] == [100000, 500000]
    assert read_polar_definitions(Settings()) == []


def test_write_polar_definitions_keeps_given_order(settings_file):
    s = Settings()
    write_polar_definitions(s, [polar_def(300000), polar_def(100000)])
    assert [d["re"] for d in s["polar_definitions"]] == [300000, 100000]


# ---- paneling


def test_paneling_values_roundtrip_through_a_dict_for_every_geometry_type():
    stored = {}
    defaults = {prefix: cls._nPanels for prefix, cls in PANELING.items()}

    for cls in PANELING.values():
        cls._nPanels += 5
    write_paneling(stored)
    assert stored == {f"{prefix}_nPanels": defaults[prefix] + 5 for prefix in PANELING}

    for prefix, cls in PANELING.items():
        cls._nPanels = defaults[prefix]
    read_paneling(stored)
    assert {prefix: cls._nPanels for prefix, cls in PANELING.items()} == {p: d + 5 for p, d in defaults.items()}

    for prefix, cls in PANELING.items():
        cls._nPanels = defaults[prefix]
    write_paneling(stored)
    assert stored == {}


@pytest.mark.parametrize("prefix", list(PANELING))
def test_paneling_of_one_geometry_type_does_not_touch_the_others(prefix):
    stored = {}
    PANELING[prefix]._le_bunch = 0.5
    write_paneling(stored)
    assert stored == {f"{prefix}_le_bunch": 0.5}


def test_read_paneling_ignores_a_dict_without_values():
    before = Paneling_Spline._nPanels
    read_paneling({})
    assert Paneling_Spline._nPanels == before
