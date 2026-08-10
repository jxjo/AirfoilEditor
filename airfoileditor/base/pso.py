#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""

Particle Swarm Optimization (PSO).

This module provides a small OO PSO core with:
- Particle state and updates
- Swarm-level best tracking
- A convenience `pso` loop function

"""

from __future__ import annotations

from dataclasses            import dataclass, replace
from termcolor              import colored

from typing import Callable
import logging

import numpy as np

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

try:
	from .math_util import enforce_bounds
except ImportError:
	# Allow direct script execution (python pso.py) for local smoke testing.
	from math_util import enforce_bounds

try:
	from .common_utils import init_logging
except:
	# Allow direct script execution (python pso.py) for local smoke testing.
  from common_utils import init_logging

class Pso_Options:
	"""Configuration options for PSO.

	Initializer assigns all instance variables directly for model-style readability.
	Use set_* methods for validated updates after initialization.
	"""

	def __init__(self,
				 pop_size: int | None = 40,
				 initial_perturb: float = 0.1,
				 w_high: float = 1.0,
				 w_low: float = 0.2,
				 convrate: float = 0.03,
				 cognitive: float = 1.2,
				 social: float = 1.6,
				 max_iter: int = 200,
				 min_iter: int = 20,
				 min_radius_best: float | None = 0.0001,
				 bound_mode: str = "reflect",
				 seed: int | None = 100):

		self._pop_size = pop_size
		self._initial_perturb = initial_perturb
		self._w_high = w_high
		self._w_low = w_low
		self._convrate = convrate
		self._cognitive = cognitive
		self._social = social
		self._max_iter = max_iter
		self._min_iter = min_iter
		self._min_radius_best = min_radius_best
		self._bound_mode = bound_mode
		self._seed = seed

	@property
	def pop_size(self) -> int | None:
		return self._pop_size

	def set_pop_size(self, value: int | None):
		if value is None:
			self._pop_size = None
		else:
			value = int(value)
			if value < 1:
				raise ValueError("pop_size must be >= 1 or None")
			self._pop_size = value

	@property
	def initial_perturb(self) -> float:
		return self._initial_perturb

	def set_initial_perturb(self, value: float):
		value = float(value)
		if value < 0.0 or value > 1.0:
			raise ValueError("initial_perturb must be in [0, 1]")
		self._initial_perturb = value

	@property
	def w_high(self) -> float:
		return self._w_high

	def set_w_high(self, value: float):
		value = float(value)
		if value < 0.0:
			raise ValueError("w_high must be >= 0")
		self._w_high = value

	@property
	def w_low(self) -> float:
		return self._w_low

	def set_w_low(self, value: float):
		value = float(value)
		if value < 0.0:
			raise ValueError("w_low must be >= 0")
		self._w_low = value

	@property
	def convrate(self) -> float:
		return self._convrate

	def set_convrate(self, value: float):
		value = float(value)
		if value < 0.0:
			raise ValueError("convrate must be >= 0")
		self._convrate = value

	@property
	def cognitive(self) -> float:
		return self._cognitive

	def set_cognitive(self, value: float):
		value = float(value)
		if value < 0.0:
			raise ValueError("cognitive must be >= 0")
		self._cognitive = value

	@property
	def social(self) -> float:
		return self._social

	def set_social(self, value: float):
		value = float(value)
		if value < 0.0:
			raise ValueError("social must be >= 0")
		self._social = value

	@property
	def max_iter(self) -> int:
		return self._max_iter

	def set_max_iter(self, value: int):
		value = int(value)
		if value < 1:
			raise ValueError("max_iter must be >= 1")
		self._max_iter = value

	@property
	def min_iter(self) -> int:
		return self._min_iter

	def set_min_iter(self, value: int):
		value = int(value)
		if value < 0:
			raise ValueError("min_iter must be >= 0")
		self._min_iter = value

	@property
	def min_radius_best(self) -> float | None:
		return self._min_radius_best

	def set_min_radius_best(self, value: float | None):
		if value is None:
			self._min_radius_best = None
		else:
			value = float(value)
			if value <= 0.0:
				raise ValueError("min_radius_best must be > 0 or None")
			self._min_radius_best = value

	@property
	def bound_mode(self) -> str:
		return self._bound_mode

	def set_bound_mode(self, value: str):
		if value not in ("reflect", "clip"):
			raise ValueError("bound_mode must be 'reflect' or 'clip'")
		self._bound_mode = value

	@property
	def seed(self) -> int | None:
		return self._seed

	def set_seed(self, value: int | None):
		if value is None:
			self._seed = None
		else:
			value = int(value)
			if value < 0:
				raise ValueError("seed must be >= 0 or None")
			self._seed = value

	@property
	def seed_ui(self) -> int:
		"""UI helper: show random seed mode as -1."""
		return self.seed if self.seed is not None else -1

	def set_seed_ui(self, value: int):
		value = int(value)
		self.set_seed(None if value < 0 else value)

	@property
	def min_radius_best_ui(self) -> float:
		"""UI helper: show disabled radius criterion as 0.0."""
		return self.min_radius_best if self.min_radius_best is not None else 0.0

	def set_min_radius_best_ui(self, value: float):
		value = float(value)
		self.set_min_radius_best(None if value <= 0.0 else value)


@dataclass(frozen=True)
class Iteration_Result:
	"""Snapshot of one PSO iteration."""

	iteration: int
	best: "Design_Score"
	r_centroid: float
	r_best: float
	inertia: float



@dataclass
class Design_Score:
	"""Container for a design vector with its objective score."""

	position: np.ndarray
	score: float = float("inf")
	particle_id: int = -1
	iteration: int = -1



class Particle:
	"""Represents one PSO particle."""

	def __init__(self,
				 position: np.ndarray,
				 velocity: np.ndarray,
				 particle_id: int):
		self._position = np.array(position, dtype=float)
		self._velocity = np.array(velocity, dtype=float)
		self._particle_id = int(particle_id)
		self._score = float("inf")
		self._best = Design_Score(self._position.copy(), float("inf"), self._particle_id, -1)


	@property
	def position(self) -> np.ndarray:
		return self._position


	@property
	def velocity(self) -> np.ndarray:
		return self._velocity


	@property
	def score(self) -> float:
		return self._score


	@property
	def particle_id(self) -> int:
		return self._particle_id


	@property
	def best_position(self) -> np.ndarray:
		return self._best.position


	@property
	def best_score(self) -> float:
		return self._best.score


	@property
	def best(self) -> Design_Score:
		return self._best


	def set_score(self, value: float, iteration: int):
		"""Update current score and personal best when improved."""
		self._score = float(value)
		if self._score < self._best.score:
			self._best = Design_Score(self._position.copy(), self._score, self._particle_id, iteration)


	def evaluate(self,
				 objective: Callable[[np.ndarray], float],
				 iteration: int) -> float:
		"""Evaluate objective for this particle and update personal best."""
		score = objective(self._position)
		self.set_score(score, iteration)
		return score


	def update_velocity(
			self,
			global_best_position: np.ndarray,
			inertia: float,
			options: Pso_Options,
			rng: np.random.Generator,
	):
		"""Apply canonical PSO velocity update for one particle."""
		# Independent random pulls per dimension keep exploration isotropic.
		r1 = rng.random(self._position.shape)
		r2 = rng.random(self._position.shape)
		cognitive_term = options.cognitive * r1 * (self._best.position - self._position)
		social_term = options.social * r2 * (global_best_position - self._position)
		self._velocity = inertia * self._velocity + cognitive_term + social_term


	def update_position(self,
						bounds: list[tuple[float, float]],
						mode: str):
		"""Advance particle position and enforce parameter bounds."""
		trial = self._position + self._velocity
		new_position = enforce_bounds(trial, bounds, mode=mode)

		# Keep velocity coherent after reflection/clipping at the bounds.
		self._velocity = new_position - self._position
		self._position = new_position



class Swarm:
	"""Collection of particles plus global-best tracking."""

	def __init__(self,
				 objective: Callable[[np.ndarray], float],
				 x_start: np.ndarray,
				 bounds: list[tuple[float, float]],
				 options: Pso_Options,
				 rng: np.random.Generator):
		"""Create and initialize a swarm for one optimization run."""
		self._objective = objective
		self._bounds = bounds
		self._options = options
		self._rng = rng

		self._dim = len(bounds)
		self._pop_size = options.pop_size if options.pop_size is not None else max(20, self._dim * 5)
		self._lower = np.array([b[0] for b in self._bounds], dtype=float)
		self._upper = np.array([b[1] for b in self._bounds], dtype=float)
		self._span = np.maximum(self._upper - self._lower, 1e-12)
		self._perturb_vec = np.clip(self._options.initial_perturb, 0.0, 1.0) * self._span
		self._particles = self._init_particles(np.array(x_start, dtype=float))

		self._global_best = Design_Score(self._particles[0].position, float("inf"), -1, -1)
		self._iteration = 0
		self._r_centroid = 0.0            # design radius around the current population centroid
		self._r_best = 0.0                # design radius around the current best particle position
		self._history: list[Iteration_Result] = []



	@property
	def particles(self) -> list[Particle]:
		return self._particles


	@property
	def global_best(self) -> Design_Score:
		return self._global_best


	@property
	def iteration(self) -> int:
		return self._iteration


	@property
	def design_radius_max(self) -> float:
		"""Maximum particle distance from current population centroid."""
		return self._r_centroid


	@property
	def design_radius_best(self) -> float:
		"""RMS particle distance from the current best particle position."""
		return self._r_best


	@property
	def history(self) -> list[Iteration_Result]:
		return self._history



	def _init_particles(self, x_start: np.ndarray) -> list[Particle]:
		"""Initialize particles from start point plus random swarm spread."""
		vel_span = self._perturb_vec
		pos_span = self._perturb_vec

		particles: list[Particle] = []
		start_position = enforce_bounds(x_start, self._bounds, mode=self._options.bound_mode)
		start_velocity = self._rng.uniform(-vel_span, vel_span)
		particles.append(Particle(start_position, start_velocity, particle_id=0))

		for iparticle in range(1, self._pop_size):
			position = start_position + self._rng.uniform(-pos_span, pos_span)
			position = enforce_bounds(position, self._bounds, mode=self._options.bound_mode)
			velocity = self._rng.uniform(-vel_span, vel_span)
			particles.append(Particle(position, velocity, particle_id=iparticle))

		return particles
    

	def evaluate(self, inertia: float):
		"""Evaluate all particles and update global-best state."""
		
		for particle in self._particles:
			particle.evaluate(self._objective, self._iteration)

			if particle.best_score < self._global_best.score:
				self._global_best = replace(particle.best)

		self._update_design_radius()

		result = Iteration_Result(
			iteration=self._iteration,
			best=replace(self._global_best),
			r_centroid=self._r_centroid,
			r_best=self._r_best,
			inertia=float(inertia),
		)
		self._history.append(result)
		self._log_iteration_status(result)


	def _log_iteration_status(self, result: Iteration_Result):
		"""Log one compact progress line for the current iteration."""
		particle_status_chars = []
		improved_global_now = result.best.iteration == result.iteration
		for particle in self._particles:
			# Particle improved this iteration if personal best was set now.
			improved_now = particle.best.iteration == result.iteration

			# Global best marker wins over personal-best marker.
			is_global_best_now = (
				improved_now
				and particle.particle_id == result.best.particle_id
				and result.best.iteration == result.iteration
			)

			if is_global_best_now:
				particle_status_chars.append(colored("!", "green", attrs=["bold"]))
			elif improved_now:
				particle_status_chars.append(colored("+", "white", attrs=["dark"]))
			else:
				particle_status_chars.append(colored("-", "white", attrs=["dark"]))

		particle_status = "".join(particle_status_chars)
		obj_str = f"{result.best.score:.8f}"
		if improved_global_now:
			obj_str = colored(obj_str, "green")

		logger.info(
			f"iter {result.iteration:4d}  "
			f"p:{particle_status}  "
			f"{colored(f'r_centr:{result.r_centroid:.3e} ', 'white', attrs=['dark'])}"
			f"{colored(f'r_best:{result.r_best:.3e}  ', 'white', attrs=['dark'])}"
			f"{colored(f'obj:', 'white', attrs=['dark'])}" + obj_str
		)


	def _update_design_radius(self):
		"""Update radius metrics around centroid and current best particle."""
		if not self._particles:
			self._r_centroid = 0.0
			self._r_best = 0.0
			return

		positions = np.array([particle.position for particle in self._particles], dtype=float)
		centroid = np.mean(positions, axis=0)
		distances_centroid = np.linalg.norm(positions - centroid, axis=1)
		distances_best = np.linalg.norm(positions - self._global_best.position, axis=1)

		self._r_centroid = float(np.max(distances_centroid))
		self._r_best     = float(np.sqrt(np.mean(distances_best * distances_best)))


	def step(self, inertia: float | None = None):
		"""Run one swarm movement step using current global best."""
		inertia_curr = self._options.w_high if inertia is None else float(inertia)
		for particle in self._particles:
			particle.update_velocity(self._global_best.position, inertia_curr, self._options, self._rng)
			particle.velocity[:] = np.clip(particle.velocity, -self._perturb_vec, self._perturb_vec)
			particle.update_position(self._bounds, mode=self._options.bound_mode)
		self._iteration += 1



class Pso:
	"""Class-based PSO runner holding state, history, and final results."""

	def __init__(self,
				 objective: Callable[[np.ndarray], float],
				 x_start: np.ndarray | list[float],
				 bounds: list[tuple[float, float]] | None,
				 options: Pso_Options,
				 stop_callback: Callable[[], bool] | None = None):
		
		self._objective = objective
		self._x_start = np.array(x_start, dtype=float)
		self._bounds = bounds if bounds is not None else [(-1.0, 1.0)] * len(self._x_start)
		self._options = options
		self._stop_callback = stop_callback if callable(stop_callback) else None

		self._rng = np.random.default_rng(self._options.seed)
		self._swarm = Swarm(self._objective, self._x_start, self._bounds, self._options, self._rng)

		self._w_high = float(self._options.w_high)
		self._w_low = float(self._options.w_low)
		self._w_curr = float(self._w_high)


	@property
	def swarm(self) -> Swarm:
		return self._swarm


	@property
	def options(self) -> Pso_Options:
		return self._options


	@property
	def history(self) -> list[Iteration_Result]:
		return self._swarm.history


	@property
	def iterations(self) -> int:
		return self._swarm.iteration


	@property
	def best_position(self) -> np.ndarray:
		return self._swarm.global_best.position


	@property
	def best_score(self) -> float:
		return self._swarm.global_best.score


	@property
	def design_radius_max(self) -> float:
		return self._swarm.design_radius_max


	@property
	def design_radius_best(self) -> float:
		return self._swarm.design_radius_best


	def _reduce_inertia(self):
		"""Reduce inertia toward w_low using the configured convergence rate."""
		if self._options.convrate <= 0.0:
			return

		next_w = self._w_curr - self._options.convrate * (self._w_curr - self._w_low)
		if self._w_high >= self._w_low:
			self._w_curr = max(self._w_low, next_w)
		else:
			self._w_curr = min(self._w_low, next_w)


	def _radius_converged(self) -> bool:
		"""Return True when design radius around best reaches configured threshold."""
		if self._options.min_radius_best is None:
			return False

		return self._swarm.design_radius_best <= float(self._options.min_radius_best)


	def run(self) -> "Pso":
		"""Execute PSO loop and collect simple per-iteration history."""
		
		for _ in range(self._options.max_iter):
			
			self._swarm.evaluate(self._w_curr)

			if self._swarm.iteration >= self._options.min_iter and self._radius_converged():
				break

			if self._stop_callback and self._stop_callback():
				break

			self._swarm.step(inertia=self._w_curr)
			self._reduce_inertia()

		return self


def pso  (objective: Callable[[np.ndarray], float],
		  x_start: np.ndarray | list[float],
		  *,
		  pop_size: int | None = None,
		  initial_perturb: float = 0.05,
		  max_iter: int = 200,
		  min_iter: int = 0,
		  bounds: list[tuple[float, float]] | None = None,
		  bound_mode: str = "reflect",
		  seed: int | None = None,
		  stop_callback: Callable[[], bool] | None = None,
		) -> tuple[tuple[np.ndarray, float], int]:
	"""Run PSO and return ((best_position, best_score), iterations)."""

	options = Pso_Options(
		pop_size=pop_size,
		initial_perturb=initial_perturb,
		max_iter=max_iter,
		min_iter=min_iter,
		bound_mode=bound_mode,
		seed=seed,
	)

	runner = Pso(objective, x_start, bounds, options, stop_callback=stop_callback).run()
	return (runner.best_position, runner.best_score), runner.iterations


if __name__ == "__main__":
	"""Small smoke run for local verification."""

	init_logging(level=logging.INFO)
	
	def objective_demo(x: np.ndarray) -> float:
		# Shifted sphere with known optimum at [0.25, -0.5, 1.0].
		target = np.array([0.25, -0.5, 1.0])
		delta = x - target
		return float(np.sum(delta * delta))

	x0 = np.array([2.0, -2.0, 3.0])
	bounds_demo = [(-4.0, 4.0), (-4.0, 4.0), (-4.0, 4.0)]

	options = Pso_Options(
		pop_size=25,
		min_radius_best=1e-3,
		w_high=1.5,
		w_low=0.5,
		convrate=0.05,
		cognitive=1.2,
		social=1.2,
		max_iter=120,
		min_iter=10,
		no_improve_thr=1e-7,
		no_improv_break=50,
		bound_mode="reflect",
		seed=42,
	)

	runner = Pso(objective_demo, x0, bounds_demo, options).run()

	print("PSO smoke run")
	print(f"  iterations: {runner.iterations}")
	print(f"  best score: {runner.best_score:.8f}")
	print(f"  best position: {np.round(runner.best_position, 6)}")
	print(f"  design radius max: {runner.design_radius_max:.6e}")
	print(f"  design radius best: {runner.design_radius_best:.6e}")
