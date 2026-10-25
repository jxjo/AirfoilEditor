from airfoileditor.base.common_utils import fromDict
from airfoileditor.model.nf_driver import Neuralfoil_Evaluator
from airfoileditor.model.polar_set import Polar, Polar_Definition, Polar_Set


def _make_neuralfoil_polar_set(monkeypatch):
    monkeypatch.setattr(Neuralfoil_Evaluator, "ready", True)
    monkeypatch.setattr(Neuralfoil_Evaluator, "available_model_sizes",
                        staticmethod(lambda: ["xlarge"]))
    polar_def = Polar_Definition({"nf_model_size": "xlarge"})
    return Polar_Set(None, polar_def)


def test_vlm_flag_is_runtime_metadata_not_transition_derived():
    polar_def = Polar_Definition()
    polar_def.set_xtript(Polar_Definition.XTRIP_VLM)
    polar_def.set_xtripb(Polar_Definition.XTRIP_VLM)

    assert not polar_def.is_VLM_polar

    polar_def.set_is_VLM_polar(True)

    assert polar_def.is_VLM_polar
    assert "is_VLM_polar" not in polar_def._as_dict()
    assert not Polar_Definition(polar_def._as_dict()).is_VLM_polar
    assert polar_def.as_copy().is_VLM_polar


def test_ensure_neuralfoil_vlm_sister_is_idempotent_and_removable(monkeypatch):
    polar_set = _make_neuralfoil_polar_set(monkeypatch)
    normal_polar = polar_set.polars[0]
    normal_polar.set_xtript(Polar_Definition.XTRIP_VLM)
    normal_polar.set_xtripb(Polar_Definition.XTRIP_VLM)

    polar_set.ensure_polars_VLM()

    assert len(polar_set.polars) == 2
    vlm_polar = polar_set.polars_VLM[0]
    assert polar_set.polars_normal == [normal_polar]
    assert vlm_polar.is_VLM_polar
    assert vlm_polar.is_neuralfoil
    assert vlm_polar.xtript == Polar_Definition.XTRIP_VLM
    assert vlm_polar.xtripb == Polar_Definition.XTRIP_VLM
    assert vlm_polar.name != normal_polar.name

    polar_set.ensure_polars_VLM()
    assert len(polar_set.polars) == 2

    polar_set.remove_polars_VLM()
    assert polar_set.polars == [normal_polar]
    assert vlm_polar.polar_set is None


def test_load_or_generate_selects_normal_and_vlm_neuralfoil_separately(monkeypatch):
    polar_set = _make_neuralfoil_polar_set(monkeypatch)
    polar_set.ensure_polars_VLM()
    normal_polar = polar_set.polars_normal[0]
    vlm_polar = polar_set.polars_VLM[0]
    loaded_polars = []

    def load_polar(polar):
        loaded_polars.append(polar)
        polar.set_error_reason("stub")

    monkeypatch.setattr(Polar, "load_polar", load_polar)

    polar_set.load_or_generate_polars(normal=True, VLM=False)
    assert loaded_polars == [normal_polar]

    normal_polar.unload()
    loaded_polars.clear()
    polar_set.load_or_generate_polars(normal=False, VLM=True)
    assert loaded_polars == [vlm_polar]


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
