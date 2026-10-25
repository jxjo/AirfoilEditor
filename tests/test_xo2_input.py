from unittest.mock import Mock

import pytest

from airfoileditor.model.polar_set import var
from airfoileditor.model.xo2_input import OPT_MIN, OPT_TARGET, OpPoint_Definition, OpPoint_Definitions


@pytest.mark.parametrize("opt_var, target, variable, expected", [
    (var.GLIDE, 50.0, var.CD, 0.01),
    (var.CD, 0.01, var.GLIDE, 50.0),
    (var.CD, 0.01, var.CD, 0.01),
    (var.GLIDE, 50.0, var.GLIDE, 50.0),
])
@pytest.mark.parametrize("cl", [0.5, 0.0, -0.5])
def test_target_values_do_not_require_seed_polar(opt_var, target, variable, expected, cl):
    definitions = Mock(spec=OpPoint_Definitions)
    point = OpPoint_Definition(definitions, specVar=var.CL, specValue=cl,
                               optVar=opt_var, optType=OPT_TARGET, optValue=target)

    if variable != opt_var:
        expected *= cl / 0.5
    assert point.get_polar_value(variable, or_target=True) == pytest.approx(expected)
    definitions.get_seed_polar.assert_not_called()


@pytest.mark.parametrize("opt_var, target, variable", [
    (var.GLIDE, 0.0, var.CD),
    (var.GLIDE, None, var.CD),
    (var.CD, None, var.GLIDE),
])
def test_undefined_target_conversion_is_logged(opt_var, target, variable, caplog):
    definitions = Mock(spec=OpPoint_Definitions)
    definitions.index.return_value = 0
    point = OpPoint_Definition(definitions, specVar=var.CL, specValue=0.5,
                               optVar=opt_var, optType=OPT_TARGET, optValue=target)

    assert point.get_polar_value(variable, or_target=True) is None
    assert "cannot derive" in caplog.text
    definitions.get_seed_polar.assert_not_called()


@pytest.mark.parametrize("spec_var, opt_var, opt_type, variable, or_target", [
    (var.CL, var.GLIDE, OPT_TARGET, var.CD, False),
    (var.CL, var.CD, OPT_TARGET, var.GLIDE, False),
    (var.ALPHA, var.GLIDE, OPT_TARGET, var.CD, True),
    (var.ALPHA, var.CD, OPT_TARGET, var.GLIDE, True),
    (var.CL, var.CD, OPT_MIN, var.GLIDE, True),
    (var.CL, var.GLIDE, OPT_TARGET, var.CM, True),
])
def test_other_values_still_use_seed_polar(spec_var, opt_var, opt_type, variable, or_target):
    definitions = Mock(spec=OpPoint_Definitions)
    polar = definitions.get_seed_polar.return_value
    polar.isLoaded = True
    polar.get_interpolated.return_value = 0.123
    point = OpPoint_Definition(definitions, specVar=spec_var, specValue=0.5,
                               optVar=opt_var, optType=opt_type, optValue=50.0)

    assert point.get_polar_value(variable, or_target=or_target) == 0.123
    polar.get_interpolated.assert_called_once_with(
        spec_var, 0.5, variable, allow_outside_range=True)
