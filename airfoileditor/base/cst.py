#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CST/Kulfan curve utilities.

This module is self-contained so it can be reused outside AirfoilEditor.
It only depends on NumPy and the Python standard library.
"""

# from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray

__all__ = [
    "CST",
]


def bernstein_product(a: ArrayLike, b: ArrayLike) -> NDArray[np.float64]:
    """Multiply two Bernstein polynomials and return Bernstein coefficients."""

    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    n = len(a) - 1
    m = len(b) - 1
    c = np.zeros(n + m + 1)

    for i, ai in enumerate(a):
        for j, bj in enumerate(b):
            k = i + j
            c[k] += ai * bj * math.comb(n, i) * math.comb(m, j) / math.comb(n + m, k)

    return c


def bernstein_elevate(a: ArrayLike, degree: int) -> NDArray[np.float64]:
    """Elevate Bernstein coefficients to a higher degree."""

    a = np.asarray(a, dtype=float)
    n = len(a) - 1

    if degree < n:
        raise ValueError("target degree must be greater than or equal to source degree")
    if degree == n:
        return np.copy(a)

    b = np.zeros(degree + 1)
    degree_delta = degree - n

    for j in range(degree + 1):
        i_min = max(0, j - degree_delta)
        i_max = min(n, j)
        for i in range(i_min, i_max + 1):
            b[j] += a[i] * math.comb(n, i) * math.comb(degree_delta, j - i) / math.comb(degree, j)

    return b


def bernstein_basis(degree: int, x: ArrayLike) -> NDArray[np.float64]:
    """Return all Bernstein basis values for degree ``degree`` at ``x``."""

    x = np.asarray(x, dtype=float)
    if x.ndim == 0:
        x = x.reshape(1)

    basis = np.zeros((degree + 1, len(x)), dtype=float)
    one_minus_x = 1.0 - x

    for i in range(degree + 1):
        basis[i, :] = math.comb(degree, i) * (x ** i) * (one_minus_x ** (degree - i))

    return basis


def bernstein_eval(coeffs: ArrayLike, x: ArrayLike) -> NDArray[np.float64]:
    """Evaluate a Bernstein polynomial at ``x``."""

    coeffs = np.asarray(coeffs, dtype=float)
    degree = len(coeffs) - 1
    basis = bernstein_basis(degree, x)
    return np.sum(basis * coeffs[:, None], axis=0)


def fit_cst_from_xy(
        x_upper : np.ndarray,
        y_upper : np.ndarray,
        x_lower : np.ndarray,
        y_lower : np.ndarray,
        n_weights: int = 8,
        le_mode: str = "free",
        le_curvature: float | None = None,
        smooth_lambda: float = 0.0,
        n1: float = 0.5,
        n2: float = 1.0,
    ) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Fit CST weights and shared leading/trailing-edge parameters from airfoil samples.

    The helper fits a single-side CST representation for the upper and lower
    airfoil surfaces from sampled coordinates. It returns the fitted weight
    vectors for both sides together with the leading-edge and trailing-edge
    parameters used by the CST formulation.

    Args:
        x_upper: x coordinates for the upper airfoil side. Must be 0..1
        y_upper: y coordinates for the upper airfoil side. Must be ...
            y[0] = 0, y_upper[-1] + y_lower[-1] = 0
        x_lower: x coordinates for the lower airfoil side. Must be 0..1
        y_lower: y coordinates for the lower airfoil side. Must be ...
            y[0] = 0, y_upper[-1] + y_lower[-1] = 0
        n_weights: Number of Bernstein weights used for each side. Defaults to 8.
        le_mode: Leading-edge mode controlling the treatment of the leading-edge
            coefficient ``a0``. Supported values are ``"free"``, ``"c2"``, ``"fixed"``.
        le_curvature: Curvature value used when ``le_mode="fixed"``. 
        smooth_lambda: Regularization strength for smoothing the fitted weights.
            Typical range 1e-4 to 1e-6.
        n1: Exponent of the CST class-function term at the le. Defaults to 0.5.
        n2: Exponent of the CST class-function term at the te. Defaults to 1.0.

    Returns:
        A tuple ``(weights_upper, weights_lower, le_weight, te_thickness)``
        containing the fitted weight vectors for the upper and lower sides, the
        leading-edge weight, and the trailing-edge thickness parameter.
    """

    # sanity checks

    if n_weights < 2:
        raise ValueError("cst_fit_from_xy: n_weights must be >= 2")

    if le_mode not in {"free", "c2", "fixed"}:
        raise ValueError("cst_fit_from_xy: le_mode must be 'free', 'c2' or 'fixed'")
    if le_mode == "fixed":
        if le_curvature is None or le_curvature <= 0.0:
            raise ValueError("cst_fit_from_xy: le_curvature must be > 0 when le_mode='fixed'")
    else:
        le_curvature = None
    if smooth_lambda < 0.0:
        raise ValueError("cst_fit_from_xy: smooth_lambda must be >= 0")

    x_u = np.asarray(x_upper, dtype=float)
    y_u = np.asarray(y_upper, dtype=float)
    x_l = np.asarray(x_lower, dtype=float)
    y_l = np.asarray(y_lower, dtype=float)

    # Validate the input geometry before fitting.
    if np.any((x_u < 0.0) | (x_u > 1.0)):
        raise ValueError("cst_fit_from_xy: x_upper must be within [0, 1]")
    if np.any((x_l < 0.0) | (x_l > 1.0)):
        raise ValueError("cst_fit_from_xy: x_lower must be within [0, 1]")
    if not y_u[0] == 0.0:
        raise ValueError("cst_fit_from_xy: y_upper[0] must be 0")
    if not y_l[0] == 0.0:
        raise ValueError("cst_fit_from_xy: y_lower[0] must be 0")
    if not np.isclose(y_u[-1] + y_l[-1], 0.0):
        raise ValueError("cst_fit_from_xy: y_upper[-1] + y_lower[-1] must be 0")

    # Build the linear system for the upper and lower CST weights.

    nu, nl = len(x_u), len(x_l)

    Bu = bernstein_basis(n_weights - 1, x_u)
    Bl = bernstein_basis(n_weights - 1, x_l)
    cu = (x_u ** n1) * ((1.0 - x_u) ** n2)
    cl = (x_l ** n1) * ((1.0 - x_l) ** n2)

    p = n_weights + 0.5
    le_term_u = x_u * ((1.0 - x_u) ** p)
    le_term_l = x_l * ((1.0 - x_l) ** p)

    te_term_u = 0.5 * x_u
    te_term_l = -0.5 * x_l

    rhs = np.concatenate((y_u, y_l))

    independent_a0 = (le_mode == "free")
    free_a0 = (le_mode == "c2")

    columns = []

    # Add the shared leading-edge term when it is not solved independently.
    if independent_a0:
        pass
    elif free_a0:
        col_a0 = np.concatenate((cu * Bu[0, :], -cl * Bl[0, :]))
        columns.append(col_a0)
    else:
        a0_fixed = np.sqrt(2.0 / le_curvature)
        fixed_contrib = np.concatenate((a0_fixed * cu * Bu[0, :], -a0_fixed * cl * Bl[0, :]))
        rhs = rhs - fixed_contrib

    # Add the upper and lower CST basis terms.
    upper_start = 0 if independent_a0 else 1
    for i in range(upper_start, n_weights):
        columns.append(np.concatenate((cu * Bu[i, :], np.zeros(nl))))

    lower_start = 0 if independent_a0 else 1
    for i in range(lower_start, n_weights):
        columns.append(np.concatenate((np.zeros(nu), cl * Bl[i, :])))

    # Add the leading- and trailing-edge shape terms.
    columns.append(np.concatenate((le_term_u, le_term_l)))
    columns.append(np.concatenate((te_term_u, te_term_l)))

    def _regularized_lstsq(A_local: np.ndarray, rhs_local: np.ndarray) -> np.ndarray:
        """Solve least squares with optional second-difference regularization."""
        if smooth_lambda <= 0.0 or n_weights < 3:
            return np.linalg.lstsq(A_local, rhs_local, rcond=None)[0]

        n_cols = A_local.shape[1]
        reg_rows = []
        reg_rhs = []

        for side in (0, 1):
            for i in range(n_weights - 2):
                row = np.zeros(n_cols)
                const = 0.0

                for k, coeff in ((i, 1.0), (i + 1, -2.0), (i + 2, 1.0)):
                    if side == 0:
                        if independent_a0:
                            row[k] += coeff
                        elif free_a0:
                            if k == 0:
                                row[0] += coeff
                            else:
                                row[k] += coeff
                        else:
                            if k == 0:
                                const += coeff * a0_fixed
                            else:
                                row[k - 1] += coeff
                    else:
                        if independent_a0:
                            row[n_weights + k] += coeff
                        elif free_a0:
                            if k == 0:
                                row[0] += -coeff
                            else:
                                row[n_weights + k - 1] += coeff
                        else:
                            if k == 0:
                                const += coeff * (-a0_fixed)
                            else:
                                row[n_weights + k - 2] += coeff

                reg_rows.append(np.sqrt(smooth_lambda) * row)
                reg_rhs.append(np.sqrt(smooth_lambda) * (-const))

        if reg_rows:
            A_aug = np.vstack((A_local, np.vstack(reg_rows)))
            rhs_aug = np.concatenate((rhs_local, np.asarray(reg_rhs)))
            return np.linalg.lstsq(A_aug, rhs_aug, rcond=None)[0]

        return np.linalg.lstsq(A_local, rhs_local, rcond=None)[0]

    A = np.column_stack(columns)
    X = _regularized_lstsq(A, rhs)

    if X[-1] < 0.0:
        X = _regularized_lstsq(A[:, :-1], rhs)
        X = np.append(X, 0.0)

    idx = 0

    weights_upper = np.empty(n_weights)
    weights_lower = np.empty(n_weights)

    if independent_a0:
        weights_upper[:] = X[idx:idx + n_weights]
        idx += n_weights
        weights_lower[:] = X[idx:idx + n_weights]
        idx += n_weights
    else:
        if free_a0:
            a0 = X[idx]
            idx += 1
        else:
            a0 = a0_fixed

        weights_upper[0] = a0
        weights_upper[1:] = X[idx:idx + n_weights - 1]
        idx += n_weights - 1

        weights_lower[0] = -a0
        weights_lower[1:] = X[idx:idx + n_weights - 1]
        idx += n_weights - 1

    le_weight = float(X[idx])
    idx += 1
    te_thickness = float(X[idx])

    return weights_upper, weights_lower, le_weight, te_thickness


class CST:
    """Single CST/Kulfan curve with ``y(x)`` on ``x`` in ``[0, 1]``."""

    DEFAULT_N1 = 0.5
    DEFAULT_N2 = 1.0

    def __init__(
            self,
            weights: ArrayLike,
            le_weight: float = 0.0,
            te_gap: float = 0.0,
            n1: float = DEFAULT_N1,
            n2: float = DEFAULT_N2,
        ):
        self._weights = np.asarray(weights, dtype=float)
        self._le_weight = float(le_weight)
        self._te_gap = float(te_gap)
        self._n1 = float(n1)
        self._n2 = float(n2)
        self._validate()


    def _validate(self):
        if self._weights.ndim != 1 or len(self._weights) < 2:
            raise ValueError("CST: weights must have at least 2 entries")
        if self._n1 <= 0.0:
            raise ValueError("CST: n1 must be > 0")
        if self._n2 <= 0.0:
            raise ValueError("CST: n2 must be > 0")


    @staticmethod
    def _as_x_array(x: float | ArrayLike) -> np.ndarray:
        xa = np.asarray(x, dtype=float)
        if xa.ndim == 0:
            xa = xa.reshape(1)
        return np.clip(xa, 0.0, 1.0)


    def _eval_1D(self, x: np.ndarray, der: int = 0) -> np.ndarray:
        """Evaluate ``y(x)`` or its first two derivatives."""

        if der < 0 or der > 2:
            raise ValueError("CST: der must be 0, 1 or 2")

        degree = len(self._weights) - 1
        s = bernstein_eval(self._weights, x)
        c = (x ** self._n1) * ((1.0 - x) ** self._n2)
        one_minus_x = 1.0 - x
        p = len(self._weights) + 0.5
        l = self._le_weight * x * (one_minus_x ** p)

        y = c * s + l + self._te_gap * x
        if der == 0:
            return y

        if degree >= 1:
            dw = np.diff(self._weights)
            ds = degree * bernstein_eval(dw, x)
        else:
            ds = np.zeros_like(x)

        n1, n2 = self._n1, self._n2
        with np.errstate(divide="ignore", invalid="ignore"):
            dc = (
                n1 * (x ** (n1 - 1.0)) * (one_minus_x ** n2)
                - n2 * (x ** n1) * (one_minus_x ** (n2 - 1.0))
            )

            dl = self._le_weight * ((one_minus_x ** p) - p * x * (one_minus_x ** (p - 1.0)))
            dy = dc * s + c * ds + dl + self._te_gap
            if der == 1:
                return dy

            if degree >= 2:
                ddw = self._weights[2:] - 2.0 * self._weights[1:-1] + self._weights[:-2]
                dds = degree * (degree - 1) * bernstein_eval(ddw, x)
            else:
                dds = np.zeros_like(x)

            coeff_a = n1 * (n1 - 1.0)
            term_a = coeff_a * (x ** (n1 - 2.0)) * (one_minus_x ** n2) if coeff_a != 0.0 else np.zeros_like(x)

            coeff_c = n2 * (n2 - 1.0)
            term_c = coeff_c * (x ** n1) * (one_minus_x ** (n2 - 2.0)) if coeff_c != 0.0 else np.zeros_like(x)

            term_b = -2.0 * n1 * n2 * (x ** (n1 - 1.0)) * (one_minus_x ** (n2 - 1.0))
            ddc = term_a + term_b + term_c

            ddl = self._le_weight * (-2.0 * p * (one_minus_x ** (p - 1.0)) + p * (p - 1.0) * x * (one_minus_x ** (p - 2.0)))
            return ddc * s + 2.0 * dc * ds + c * dds + ddl


    @property
    def weights(self) -> np.ndarray:
        """Return a copy of the Bernstein weights."""

        return np.copy(self._weights)


    @property
    def weights_x(self) -> np.ndarray:
        """Return the Bernstein x-locations of the weights."""

        n = len(self._weights) - 1
        return np.array([i / n for i in range(n + 1)], dtype=float)


    @property
    def ncp(self) -> int:
        """Return the number of control points."""

        return len(self._weights)


    @property
    def le_weight(self) -> float:
        """Return the leading-edge weight."""

        return self._le_weight


    @property
    def te_gap(self) -> float:
        """Return the trailing-edge gap."""

        return self._te_gap


    @property
    def n1(self) -> float:
        """Return the class-function exponent at the leading edge."""

        return self._n1


    @property
    def n2(self) -> float:
        """Return the class-function exponent at the trailing edge."""

        return self._n2


    def set_weights(self, weights: ArrayLike):
        self._weights = np.asarray(weights, dtype=float)
        self._validate()


    def set_le_weight(self, le_weight: float):
        self._le_weight = float(le_weight)


    def set_te_gap(self, te_gap: float):
        self._te_gap = float(te_gap)


    @property
    def cpoints(self) -> list[tuple[float, float]]:
        """
        Return the weights as a list of (x, y) tuples
        - compatible with the control-point interface of Bezier and B-Spline curves.
        """
        return list(zip(self.weights_x, self._weights))
    
    def set_cpoints(self, cpx_or_cp: list, cpy: list | None = None):
        """Set the weight vector from a control-point style input."""

        if cpy is None:
            cpx, cpy = zip(*cpx_or_cp)
        else:
            cpx = cpx_or_cp

        n = len(cpx)
        if n < 4:
            raise ValueError("CST: must have at least 4 control points")
        if n != len(cpy):
            raise ValueError("CST: length of x,y is different")

        self._weights = np.asarray(cpy, dtype=float)
        self._validate()


    def eval(
            self,
            u: float | ArrayLike,
            der: int = 0,
            update_cache: bool = True,
        ) -> tuple[np.ndarray, np.ndarray] | tuple[float, float]:
        """Evaluate the curve or one of its derivatives."""

        x = self._as_x_array(u)
        if der == 0:
            out_x, out_y = x, self._eval_1D(x, der=0)
        elif der == 1:
            out_x, out_y = np.ones_like(x), self._eval_1D(x, der=1)
        elif der == 2:
            out_x, out_y = np.zeros_like(x), self._eval_1D(x, der=2)
        else:
            raise ValueError("CST.eval: der must be 0, 1 or 2")

        if np.asarray(u).ndim == 0:
            return float(out_x[0]), float(out_y[0])
        return out_x, out_y


    def eval_y(self, u: float | ArrayLike) -> float | np.ndarray:
        """Evaluate ``y`` directly."""

        y = self._eval_1D(self._as_x_array(u), der=0)
        if np.asarray(u).ndim == 0:
            return float(y[0])
        return y


    def eval_y_on_x(self, x: float | ArrayLike, fast: bool = False, epsilon: float = 1e-7) -> float | np.ndarray:
        """Compatibility helper for curve interfaces."""

        return self.eval_y(x)


    def curvature(self, x: float | ArrayLike) -> float | np.ndarray:
        """Evaluate signed curvature."""

        xa = self._as_x_array(x)
        dy = self._eval_1D(xa, der=1)
        ddy = self._eval_1D(xa, der=2)

        denom = (1.0 + dy * dy) ** 1.5
        with np.errstate(divide="ignore", invalid="ignore"):
            kappa = np.where(denom > 1e-14, ddy / denom, 0.0)

        if abs(self._n1 - 0.5) < 1e-12:
            mask_le = np.isclose(xa, 0.0)
            if np.any(mask_le):
                a0 = float(self._weights[0])
                if abs(a0) > 1e-14:
                    kappa_le = -2.0 * np.sign(a0) / (a0 * a0)
                else:
                    kappa_le = 0.0
                kappa[mask_le] = kappa_le

        if np.asarray(x).ndim == 0:
            return float(kappa[0])
        return kappa


    def elevate_weights(self) -> None:
        """Raise the Bernstein degree by one without changing the shape."""

        weights = self.weights
        n = len(weights) - 1

        elevated = np.empty(n + 2)
        elevated[0] = weights[0]
        elevated[-1] = weights[-1]

        for i in range(1, n + 1):
            alpha = i / (n + 1)
            elevated[i] = alpha * weights[i - 1] + (1.0 - alpha) * weights[i]

        self.set_weights(elevated)
