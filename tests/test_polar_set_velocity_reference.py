import numpy as np
import pytest

from airfoileditor.model.polar_set import AIR_RHO, q_dyn_from_load, vtas_from_q_dyn



class TestQDynFromLoad:

    def test_derives_q_dyn_for_level_flight(self):
        # q_dyn = g * load / cl
        assert q_dyn_from_load(8.0, 0.5) == pytest.approx(9.81 * 8.0 / 0.5)

    def test_returns_none_for_zero_cl(self):
        assert q_dyn_from_load(8.0, 0.0) is None

    def test_returns_none_for_non_finite_cl(self):
        assert q_dyn_from_load(8.0, np.nan) is None


class TestVtasFromQDyn:

    def test_derives_vtas_from_q_dyn(self):
        q_dyn = 1.225 / 2.0 * 20.0 ** 2
        assert vtas_from_q_dyn(q_dyn) == pytest.approx(20.0)

    def test_returns_none_for_none_q_dyn(self):
        assert vtas_from_q_dyn(None) is None

    def test_returns_none_for_negative_q_dyn(self):
        assert vtas_from_q_dyn(-1.0) is None

    def test_round_trips_with_q_dyn_from_load(self):
        # a T2 opPoint's q_dyn/vtas implied by a wing load and its converged cl
        load, cl = 8.0, 0.65
        q_dyn = q_dyn_from_load(load, cl)
        vtas = vtas_from_q_dyn(q_dyn)

        # Lift = Weight: cl * q_dyn * area == load * area * g  (area cancels)
        assert cl * q_dyn == pytest.approx(9.81 * load)
        assert q_dyn == pytest.approx(AIR_RHO / 2.0 * vtas ** 2)
