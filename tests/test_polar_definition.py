from airfoileditor.base.common_utils import fromDict
from airfoileditor.model.polar_set import Polar, Polar_Definition


def test_from_dict_returns_copy_of_list_default_for_none_value():
    default = [1, 2, 3]

    value = fromDict({"valRange": None}, "valRange", default)

    assert value == default
    assert value is not default


def test_val_range_step_change_is_detected_by_equality_check():
    polar_def_a = Polar_Definition()
    polar_def_b = Polar_Definition()

    polar_def_a.set_valRange_step(0.5)

    assert polar_def_a.valRange_step == 0.5
    assert polar_def_b.valRange_step == 0.3
    assert not polar_def_a.is_equal_to(polar_def_b)


def test_polar_constructor_preserves_custom_val_range_from_definition():
    polar_def = Polar_Definition()
    polar_def.set_is_xfoil(True)
    polar_def.set_type("T2")
    polar_def.set_specVar("cl")
    polar_def.set_valRange([1.0, 2.0, 0.1])

    polar = Polar(None, polar_def)

    assert polar.valRange == [1.0, 2.0, 0.1]


def test_neuralfoil_T2_always_uses_auto_range():
    polar_def = Polar_Definition({"nf_model_size": "xlarge"})
    polar_def.set_type("T2")

    assert polar_def.type == "T2"
    assert polar_def.specVar == "cl"
    assert polar_def.valRange == Polar_Definition.VAL_RANGE_CL_T2
    assert polar_def.autoRange
    polar_def.set_valRange_step(0.08)
    polar_def.set_autoRange(False)
    assert polar_def.autoRange
    assert polar_def.valRange_step == 0.08


def test_neuralfoil_T2_restores_saved_auto_range_without_saved_bounds():
    polar_def = Polar_Definition({"nf_model_size": "xlarge", "type": "T2",
                                  "specVar": "cl", "autoRange": True})

    assert polar_def.autoRange
    assert polar_def.valRange == Polar_Definition.VAL_RANGE_CL_T2
    polar_def.set_valRange_step(0.08)
    saved = polar_def._as_dict()
    assert "valRange" not in saved
    assert saved["valRangeStep"] == 0.08
    copied = polar_def.as_copy()
    assert copied.autoRange
    assert copied.valRange_step == 0.08


def test_neuralfoil_T2_uses_saved_cl_step_but_driver_bounds():
    polar_def = Polar_Definition({"nf_model_size": "xlarge", "type": "T2",
                                  "specVar": "cl", "valRangeStep": 0.1})

    for definition in (polar_def, polar_def.as_copy(), Polar(None, polar_def)):
        assert definition.type == "T2"
        assert definition.specVar == "cl"
        assert definition.autoRange
        assert definition.valRange[:2] == Polar_Definition.VAL_RANGE_CL_T2[:2]
        assert definition.valRange_step == 0.1


def test_xfoil_T2_still_uses_explicit_range(monkeypatch):
    monkeypatch.setattr("airfoileditor.model.polar_set.Worker.ready", True)
    polar_def = Polar_Definition()
    polar_def.set_type("T2")
    polar_def.set_autoRange(False)
    polar_def.set_valRange([0.2, 1.0, 0.1])

    assert not polar_def.autoRange
    assert polar_def.valRange == [0.2, 1.0, 0.1]


def test_switching_xfoil_T2_to_neuralfoil_enables_auto_range(monkeypatch):
    monkeypatch.setattr("airfoileditor.model.polar_set.Worker.ready", True)
    polar_def = Polar_Definition()
    polar_def.set_type("T2")
    polar_def.set_autoRange(False)

    polar_def.set_nf_model_size("xlarge")

    assert polar_def.autoRange


def test_neuralfoil_T1_defaults_remain_unchanged():
    polar_def = Polar_Definition({"nf_model_size": "xlarge"})

    assert polar_def.type == "T1"
    assert polar_def.specVar == "alpha"
    assert polar_def.valRange == Polar_Definition.VAL_RANGE_ALPHA
    assert polar_def.autoRange
