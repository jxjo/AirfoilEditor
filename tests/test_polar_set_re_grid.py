import pytest

from airfoileditor.model.polar_set import Polar_Definition, Polar_Set, RE_GRID_T2, re_grid_values



class TestReGridValues:

    def test_returns_inside_points_plus_nearest_edge_points(self):
        assert re_grid_values(120_000, 450_000) == [100_000, 200_000, 400_000, 800_000]

    def test_adds_nearest_edge_points_outside_range(self):
        assert re_grid_values(150_000, 150_000) == [100_000, 200_000]

    def test_handles_swapped_bounds(self):
        assert re_grid_values(450_000, 120_000) == [100_000, 200_000, 400_000, 800_000]

    def test_range_below_grid_returns_lowest_point_only(self):
        assert re_grid_values(100, 5_000) == [10_000]

    def test_range_above_grid_returns_highest_point_only(self):
        assert re_grid_values(10_000_000, 20_000_000) == [3_200_000]

    def test_grid_is_sorted_and_strictly_increasing(self):
        assert RE_GRID_T2 == sorted(RE_GRID_T2)
        assert len(set(RE_GRID_T2)) == len(RE_GRID_T2)


class TestEnsureReValues:

    def _polar_set(self) -> Polar_Set:
        template = Polar_Definition()
        template.set_re(300_000)
        return Polar_Set(None, template)

    def test_creates_missing_and_reuses_existing_polars(self):
        polar_set = self._polar_set()
        existing = polar_set.polars[0]

        result = polar_set.ensure_re_values(existing, [300_000, 100_000, 200_000])

        assert result[0] is existing
        assert [polar.re for polar in result] == [300_000, 100_000, 200_000]
        assert len(polar_set.polars) == 3

    def test_newly_created_polars_are_inactive_but_existing_ones_are_untouched(self):
        """Grid polars must stay out of the normal 'active polar' display/definitions list."""
        polar_set = self._polar_set()
        existing = polar_set.polars[0]
        assert existing.active                 # sanity: the pre-existing polar is active

        result = polar_set.ensure_re_values(existing, [300_000, 100_000, 200_000])

        assert result[0].active                # the reused, pre-existing polar is untouched
        assert not result[1].active             # newly created grid polars are inactive
        assert not result[2].active

    def test_repeated_value_returns_same_polar_instance(self):
        polar_set = self._polar_set()
        existing = polar_set.polars[0]

        result = polar_set.ensure_re_values(existing, [100_000, 200_000, 100_000])

        assert result[0] is result[2]
        assert len(polar_set.polars) == 3

    def test_is_idempotent(self):
        polar_set = self._polar_set()
        existing = polar_set.polars[0]

        first = polar_set.ensure_re_values(existing, [100_000, 200_000])
        second = polar_set.ensure_re_values(existing, [100_000, 200_000])

        assert first == second
        assert len(polar_set.polars) == 3

    def test_result_order_matches_requested_re_values(self):
        polar_set = self._polar_set()
        existing = polar_set.polars[0]

        result = polar_set.ensure_re_values(existing, [400_000, 100_000, 200_000])

        assert [polar.re for polar in result] == [400_000, 100_000, 200_000]
