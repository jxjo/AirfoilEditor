import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from airfoileditor.app_model import App_Model, Airfoil_Settings
from airfoileditor.base.app_utils import Settings
from airfoileditor.model.airfoil import Airfoil
from airfoileditor.model.airfoil_examples import Root_Example
from airfoileditor.model.geometry_bezier import Paneling_Bezier
from airfoileditor.model.geometry_bspline import Paneling_BSpline
from airfoileditor.model.geometry_cst import Paneling_CST
from airfoileditor.model.geometry_spline import Paneling_Spline
from airfoileditor.model.polar_set import Polar_Definition


@pytest.fixture(autouse=True)
def restore_paneling(monkeypatch):
    """ paneling values are class state - undo whatever a test loads """
    for cls in (Paneling_Spline, Paneling_Bezier, Paneling_BSpline, Paneling_CST):
        for name in ("_nPanels", "_le_bunch", "_te_bunch"):
            monkeypatch.setattr(cls, name, getattr(cls, name))


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "app.settings"
    monkeypatch.setattr(Settings, "_pathFileName", str(path))
    return path


@pytest.fixture
def model(qapp, tmp_path, settings_file):
    return App_Model(workingDir_default=str(tmp_path), start_watchdog=False)


def saved_airfoil(directory, name):
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


def reference_paths(model):
    return [Path(airfoil.pathFileName_abs).name for airfoil in model.airfoils_ref]


def write_json(path, data):
    Path(path).write_text(json.dumps(data))


def individual_file(airfoil):
    return Path(Airfoil_Settings.settings_pathFileName(airfoil))


def test_global_roundtrip_of_references_polars_and_extra_key(model, tmp_path, settings_file):
    current, reference = saved_airfoil(tmp_path, "current"), saved_airfoil(tmp_path, "ref")
    model.set_airfoil(current)
    reference.set_property("show", False)
    reference.set_scale_factor(1.25)
    model.set_airfoil_ref(None, reference, silent=True)
    model._polar_definitions = [polar_def(300000), polar_def(150000)]

    model.save_settings(to_app_settings=True, add_key="diagram", add_value={"x": 1})

    data = json.loads(settings_file.read_text())
    assert data["diagram"] == {"x": 1}
    assert data["reference_airfoils"] == [{"path": reference.pathFileName_abs, "show": False, "scale": 1.25}]
    assert [d["re"] for d in data["polar_definitions"]] == [300000, 150000]
    assert "export_dxf" not in data                         # default exporter has nothing to store
    assert not model.airfoil_settings_loaded

    other = App_Model(workingDir_default=str(tmp_path), start_watchdog=False)
    slot = Mock()
    other.sig_settings_loaded.connect(slot)
    other.set_airfoil(current)
    other.load_settings()

    slot.assert_called_once()
    assert reference_paths(other) == ["ref.dat"]
    loaded = other.airfoils_ref[0]
    assert loaded.get_property("show", True) is False
    assert loaded.scale_factor == 1.25
    assert [d.re for d in other.polar_definitions] == [150000, 300000]
    assert other.settings.get("diagram") == {"x": 1}
    assert not other.airfoil_settings_loaded


def test_individual_settings_file_roundtrip_and_flags(model, tmp_path, settings_file):
    current, reference = saved_airfoil(tmp_path, "current"), saved_airfoil(tmp_path, "ref")
    model.set_airfoil(current)
    model.set_airfoil_ref(None, reference, silent=True)
    assert not model.airfoil_settings_exist

    model.save_settings(add_key="diagram", add_value={"y": 2})

    assert individual_file(current).is_file()
    assert not settings_file.exists()
    assert json.loads(individual_file(current).read_text())["diagram"] == {"y": 2}
    assert model.airfoil_settings_exist and model.airfoil_settings_loaded
    assert isinstance(model.settings, Airfoil_Settings)

    other = App_Model(workingDir_default=str(tmp_path), start_watchdog=False)
    other.set_airfoil(current, load_settings=True)
    assert other.airfoil_settings_loaded
    assert isinstance(other.settings, Airfoil_Settings)
    assert reference_paths(other) == ["ref.dat"]


def test_individual_settings_win_over_global_settings(model, tmp_path, settings_file):
    current = saved_airfoil(tmp_path, "current")
    saved_airfoil(tmp_path, "global_ref")
    saved_airfoil(tmp_path, "own_ref")
    write_json(settings_file, {"reference_airfoils": [str(tmp_path / "global_ref.dat")]})
    write_json(individual_file(current), {"reference_airfoils": [str(tmp_path / "own_ref.dat")]})

    model.set_airfoil(current, load_settings=True)
    assert reference_paths(model) == ["own_ref.dat"]

    model.set_airfoil(saved_airfoil(tmp_path, "plain"))
    model.load_settings()
    assert reference_paths(model) == ["global_ref.dat"]
    assert not model.airfoil_settings_loaded


def test_delete_airfoil_settings_falls_back_to_global_and_signals(model, tmp_path, settings_file):
    current = saved_airfoil(tmp_path, "current")
    saved_airfoil(tmp_path, "global_ref")
    write_json(settings_file, {"reference_airfoils": [str(tmp_path / "global_ref.dat")]})
    model.set_airfoil(current)
    model.save_settings()
    assert individual_file(current).is_file()
    slot = Mock()
    model.sig_settings_loaded.connect(slot)

    model.delete_airfoil_settings()

    assert not individual_file(current).exists()
    assert not model.airfoil_settings_exist and not model.airfoil_settings_loaded
    assert not isinstance(model.settings, Airfoil_Settings)
    assert reference_paths(model) == ["global_ref.dat"]
    slot.assert_called_once()


def test_delete_without_individual_settings_does_nothing(model, tmp_path):
    model.set_airfoil(saved_airfoil(tmp_path, "current"))
    slot = Mock()
    model.sig_settings_loaded.connect(slot)
    model.delete_airfoil_settings()
    slot.assert_not_called()


def test_load_skips_reference_airfoils_which_cannot_be_loaded(model, tmp_path, settings_file):
    saved_airfoil(tmp_path, "good")
    broken = tmp_path / "broken.dat"
    broken.write_text("not an airfoil\n")
    write_json(settings_file, {"reference_airfoils": [
        {"path": str(tmp_path / "missing.dat")}, {"path": str(broken)},
        {"path": str(tmp_path / "good.dat")}, {"show": False}, 42]})
    model.set_airfoil(saved_airfoil(tmp_path, "current"))
    model.load_settings()
    assert reference_paths(model) == ["good.dat"]


def test_load_accepts_legacy_string_entries(model, tmp_path, settings_file):
    saved_airfoil(tmp_path, "one")
    saved_airfoil(tmp_path, "two")
    write_json(settings_file, {"reference_airfoils": [str(tmp_path / "one.dat"), str(tmp_path / "two.dat")]})
    model.set_airfoil(saved_airfoil(tmp_path, "current"))
    model.load_settings()
    assert reference_paths(model) == ["one.dat", "two.dat"]
    assert all(airfoil.get_property("show", True) for airfoil in model.airfoils_ref)
    assert all(airfoil.scale_factor == 1.0 for airfoil in model.airfoils_ref)


def test_load_sorts_polar_definitions_by_re(model, tmp_path, settings_file):
    write_json(settings_file, {"polar_definitions": [polar_def(500000)._as_dict(), polar_def(100000)._as_dict(),
                                                    polar_def(250000)._as_dict()]})
    model.set_airfoil(saved_airfoil(tmp_path, "current"))
    model.load_settings()
    assert [d.re for d in model.polar_definitions] == [100000, 250000, 500000]


def test_load_replaces_the_previous_state_instead_of_appending(model, tmp_path, settings_file):
    saved_airfoil(tmp_path, "ref")
    write_json(settings_file, {"reference_airfoils": [str(tmp_path / "ref.dat")],
                               "polar_definitions": [polar_def(123000)._as_dict()]})
    model.set_airfoil(saved_airfoil(tmp_path, "current"))
    model.load_settings()
    model.load_settings()
    assert reference_paths(model) == ["ref.dat"]
    assert [d.re for d in model.polar_definitions] == [123000]


@pytest.mark.parametrize("paneling_cls, key", [(Paneling_Spline, "spline_nPanels"), (Paneling_Bezier, "bezier_nPanels"),
                                               (Paneling_BSpline, "bspline_nPanels"), (Paneling_CST, "cst_nPanels")])
def test_paneling_roundtrip_and_defaults_remove_stale_keys(model, tmp_path, settings_file, paneling_cls, key):
    model.set_airfoil(saved_airfoil(tmp_path, "current"))
    default_panels = paneling_cls._nPanels
    paneling_cls._nPanels = default_panels + 17
    model.save_settings(to_app_settings=True)
    assert json.loads(settings_file.read_text())[key] == default_panels + 17

    paneling_cls._nPanels = default_panels
    model.load_settings()
    assert paneling_cls._nPanels == default_panels + 17

    paneling_cls._nPanels = default_panels
    model.save_settings(to_app_settings=True)
    assert key not in json.loads(settings_file.read_text())


def test_global_save_keeps_unrelated_keys_but_individual_save_rebuilds(model, tmp_path, settings_file):
    current = saved_airfoil(tmp_path, "current")
    model.set_airfoil(current)
    write_json(settings_file, {"color_scheme": "dark"})
    write_json(individual_file(current), {"stale": True})

    model.save_settings(to_app_settings=True)
    assert json.loads(settings_file.read_text())["color_scheme"] == "dark"

    model.save_settings()
    assert "stale" not in json.loads(individual_file(current).read_text())
