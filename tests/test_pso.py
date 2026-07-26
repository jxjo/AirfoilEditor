#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Unit tests for PSO core module."""

import numpy as np

from airfoileditor.base.pso import Iteration_Result, Particle, Pso, Swarm, Pso_Options, pso


def sphere(x: np.ndarray) -> float:
    return float(np.sum(x * x))


class Test_Particle:

    def test_particle_updates_personal_best(self):
        p = Particle(np.array([1.0, 1.0]), np.array([0.0, 0.0]), particle_id=0)

        p.set_score(2.0, iteration=0)
        assert p.best_score == 2.0

        p.set_score(3.0, iteration=1)
        assert p.best_score == 2.0

        p.set_score(1.0, iteration=2)
        assert p.best_score == 1.0


class Test_Swarm:

    def test_swarm_initializes_with_start_particle(self):
        bounds = [(-2.0, 2.0), (-2.0, 2.0)]
        options = Pso_Options(pop_size=8, seed=42)
        rng = np.random.default_rng(42)

        swarm = Swarm(sphere, np.array([0.5, -0.5]), bounds, options, rng)

        assert len(swarm.particles) == 8
        assert np.allclose(swarm.particles[0].position, np.array([0.5, -0.5]))

    def test_initial_perturb_zero_collapses_initial_spread(self):
        bounds = [(-2.0, 2.0), (-2.0, 2.0)]
        x0 = np.array([0.5, -0.5])
        options = Pso_Options(pop_size=8, initial_perturb=0.0, seed=42)
        rng = np.random.default_rng(42)

        swarm = Swarm(sphere, x0, bounds, options, rng)

        for particle in swarm.particles:
            assert np.allclose(particle.position, x0)
            assert np.allclose(particle.velocity, np.zeros_like(x0))

    def test_initial_perturb_scales_spread_and_speed_by_dimension(self):
        bounds = [(-1.0, 1.0), (-3.0, 3.0)]
        x0 = np.array([0.2, -0.5])
        options = Pso_Options(pop_size=10, initial_perturb=0.1, seed=7)
        rng = np.random.default_rng(7)

        swarm = Swarm(sphere, x0, bounds, options, rng)
        perturb = np.array([0.2, 0.6])

        # Initial velocities are limited component-wise by perturb vector.
        for particle in swarm.particles:
            assert np.all(np.abs(particle.velocity) <= perturb + 1e-12)

        # At least one non-anchor particle should differ from x0 when perturb > 0.
        deltas = [np.abs(p.position - x0) for p in swarm.particles[1:]]
        assert any(np.any(delta > 0.0) for delta in deltas)
        for delta in deltas:
            assert np.all(delta <= perturb + 1e-12)

    def test_velocity_is_clipped_to_initial_perturb_on_step(self):
        bounds = [(-1.0, 1.0), (-3.0, 3.0)]
        x0 = np.array([0.2, -0.5])
        options = Pso_Options(
            pop_size=8,
            initial_perturb=0.05,
            w_high=1.5,
            cognitive=3.0,
            social=3.0,
            seed=11,
        )
        rng = np.random.default_rng(11)

        swarm = Swarm(sphere, x0, bounds, options, rng)
        perturb = np.array([0.1, 0.3])

        swarm.evaluate(inertia=options.w_high)
        swarm.step(inertia=options.w_high)

        for particle in swarm.particles:
            assert np.all(np.abs(particle.velocity) <= perturb + 1e-12)


class Test_Pso:

    def test_pso_is_deterministic_with_seed(self):
        bounds = [(-3.0, 3.0), (-3.0, 3.0)]
        x0 = np.array([2.5, -1.5])

        (best1, score1), niter1 = pso(
            sphere,
            x0,
            bounds=bounds,
            max_iter=80,
            min_iter=10,
            seed=42,
        )
        (best2, score2), niter2 = pso(
            sphere,
            x0,
            bounds=bounds,
            max_iter=80,
            min_iter=10,
            seed=42,
        )

        assert np.allclose(best1, best2)
        assert score1 == score2
        assert niter1 == niter2

    def test_pso_improves_objective(self):
        bounds = [(-4.0, 4.0), (-4.0, 4.0), (-4.0, 4.0)]
        x0 = np.array([3.0, -2.0, 1.0])

        start_score = sphere(x0)
        (best, score), _ = pso(
            sphere,
            x0,
            bounds=bounds,
            max_iter=100,
            min_iter=10,
            seed=42,
        )

        assert score < start_score
        assert np.isfinite(score)
        assert best.shape == x0.shape

    def test_pso_honors_stop_callback(self):
        bounds = [(-2.0, 2.0), (-2.0, 2.0)]
        x0 = np.array([1.0, 1.0])

        calls = {"n": 0}

        def stop_callback() -> bool:
            calls["n"] += 1
            return calls["n"] > 2

        (_, _), niter = pso(
            sphere,
            x0,
            bounds=bounds,
            max_iter=200,
            min_iter=0,
            seed=42,
            stop_callback=stop_callback,
        )

        assert niter <= 2

    def test_pso_runner_exposes_swarm_history(self):
        bounds = [(-3.0, 3.0), (-3.0, 3.0)]
        x0 = np.array([2.0, -1.0])
        options = Pso_Options(max_iter=20, min_iter=0, seed=42)

        runner = Pso(sphere, x0, bounds, options).run()

        assert runner.history is runner.swarm.history
        assert len(runner.history) == runner.iterations
        assert isinstance(runner.history[0], Iteration_Result)
        assert runner.history[0].best.score <= sphere(x0)
