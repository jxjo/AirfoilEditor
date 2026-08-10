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
