"""Nonlinear solution driver: Newton-Raphson with load / displacement control.

Two control modes exist because they fail differently, and that difference is
the whole point of this project:

* **load control** increases the applied force.  At a limit point of the
  equilibrium path the tangent stiffness becomes singular and the iteration
  cannot proceed no matter how small the load step is.
* **displacement control** prescribes a displacement component and treats the
  load factor as an unknown.  It walks straight through the limit point and
  traces the unstable branch.

A solver that only knows load control reports "failed".  A solver that can
recognise *why* it failed can switch strategy and finish the job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from .fem import Model, assemble, residual

Control = Literal["load", "displacement"]

# Failure kinds, ordered by how informative they are to a caller.
FAILURE_MAX_ITERATIONS = "max_iterations"
FAILURE_DIVERGED = "diverged"
FAILURE_SINGULAR_TANGENT = "singular_tangent"
FAILURE_NONFINITE = "nonfinite"
FAILURE_STEP_EXHAUSTED = "step_exhausted"
FAILURE_BAD_OPTIONS = "bad_options"


class SolverError(RuntimeError):
    """Raised for unusable solver configuration."""


@dataclass
class SolverOptions:
    """Everything the driver needs to attempt a solution."""

    control: Control = "load"
    n_steps: int = 10
    max_iter: int = 30
    tol: float = 1e-8
    diverge_factor: float = 1e6
    line_search: bool = False
    max_backtracks: int = 8
    adaptive: bool = True
    max_cutbacks: int = 12
    min_step_ratio: float = 1e-4
    step_growth: float = 1.0
    # displacement control
    control_dof: int | None = None
    target_displacement: float = 0.0
    # scaling floor for the relative residual
    reference_force: float = 1.0

    def replace(self, **kwargs: Any) -> "SolverOptions":
        data = {f: getattr(self, f) for f in self.__dataclass_fields__}
        data.update(kwargs)
        return SolverOptions(**data)


@dataclass
class StepRecord:
    """One accepted load (or displacement) increment."""

    step: int
    control_start: float
    control_end: float
    load_factor: float
    iterations: int
    residual_norm: float
    max_displacement: float
    residual_history: list[float] = field(default_factory=list)


@dataclass
class FailedAttempt:
    """A rejected increment, kept so the failure can be reported honestly."""

    step: int
    control_start: float
    control_trial: float
    failure: str
    iterations: int
    residual_norm: float
    residual_history: list[float] = field(default_factory=list)


@dataclass
class SolveResult:
    converged: bool
    control: Control
    load_factor: float
    control_value: float
    u: np.ndarray | None
    steps: list[StepRecord] = field(default_factory=list)
    failures: list[FailedAttempt] = field(default_factory=list)
    failure: str | None = None
    message: str = ""
    options: SolverOptions | None = None

    @property
    def path(self) -> list[tuple[float, float, float]]:
        """Equilibrium path as ``(control, load_factor, max_displacement)``."""
        return [(s.control_end, s.load_factor, s.max_displacement) for s in self.steps]

    def summary(self) -> dict[str, Any]:
        return {
            "converged": self.converged,
            "control": self.control,
            "load_factor": self.load_factor,
            "control_value": self.control_value,
            "accepted_steps": len(self.steps),
            "rejected_steps": len(self.failures),
            "failure": self.failure,
            "message": self.message,
            "max_displacement": self.steps[-1].max_displacement if self.steps else 0.0,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scale(model: Model, free: np.ndarray, load_factor: float, floor: float) -> float:
    f_ext = model.load_vector()[free]
    return max(float(np.linalg.norm(load_factor * f_ext)), floor)


def _backtrack(
    model: Model,
    u: np.ndarray,
    free: np.ndarray,
    du: np.ndarray,
    load_factor: float,
    base_norm: float,
    options: SolverOptions,
) -> tuple[float, float]:
    """Simple backtracking line search on the residual norm."""
    alpha = 1.0
    best_alpha, best_norm = 0.0, base_norm
    for _ in range(options.max_backtracks):
        trial = u.copy()
        trial[free] += alpha * du
        r_trial, _, _ = residual(model, trial, load_factor)
        norm = float(np.linalg.norm(r_trial[free]))
        if np.isfinite(norm) and norm < best_norm:
            best_norm, best_alpha = norm, alpha
            break
        alpha *= 0.5
    return best_alpha, best_norm


# ---------------------------------------------------------------------------
# Single-increment Newton iterations
# ---------------------------------------------------------------------------


def _newton_load(
    model: Model, u: np.ndarray, load_factor: float, options: SolverOptions
) -> tuple[bool, np.ndarray, int, float, list[float], str | None]:
    free = model.free_dofs()
    u = u.copy()
    history: list[float] = []
    norm = float("inf")

    for iteration in range(1, options.max_iter + 1):
        r, k_mat, _ = residual(model, u, load_factor)
        r_free = r[free]
        norm = float(np.linalg.norm(r_free))

        if not np.isfinite(norm):
            return False, u, iteration, norm, history, FAILURE_NONFINITE
        history.append(norm)

        if norm <= options.tol * _scale(model, free, load_factor, options.reference_force):
            return True, u, iteration, norm, history, None

        if len(history) > 1 and norm > options.diverge_factor * history[0]:
            return False, u, iteration, norm, history, FAILURE_DIVERGED

        k_free = k_mat[np.ix_(free, free)]
        try:
            du = np.linalg.solve(k_free, -r_free)
        except np.linalg.LinAlgError:
            return False, u, iteration, norm, history, FAILURE_SINGULAR_TANGENT

        if not np.all(np.isfinite(du)):
            return False, u, iteration, norm, history, FAILURE_NONFINITE

        alpha = 1.0
        if options.line_search:
            alpha, _ = _backtrack(model, u, free, du, load_factor, norm, options)
            if alpha == 0.0:
                return False, u, iteration, norm, history, FAILURE_DIVERGED

        u[free] += alpha * du

    return False, u, options.max_iter, norm, history, FAILURE_MAX_ITERATIONS


def _newton_displacement(
    model: Model,
    u: np.ndarray,
    load_factor: float,
    target: float,
    options: SolverOptions,
) -> tuple[bool, np.ndarray, float, int, float, list[float], str | None]:
    """Bordered Newton iteration: prescribed displacement, load factor unknown."""
    if options.control_dof is None:
        raise SolverError("displacement control requires control_dof")

    free = model.free_dofs()
    local = int(np.flatnonzero(free == options.control_dof)[0])
    u = u.copy()
    history: list[float] = []
    norm = float("inf")
    gap = float("inf")

    for iteration in range(1, options.max_iter + 1):
        r, k_mat, _ = residual(model, u, load_factor)
        r_free = r[free]
        norm = float(np.linalg.norm(r_free))
        gap = target - float(u[options.control_dof])

        if not np.isfinite(norm) or not np.isfinite(gap) or not np.isfinite(load_factor):
            return False, u, load_factor, iteration, norm, history, FAILURE_NONFINITE
        history.append(norm)

        scale = _scale(model, free, load_factor, options.reference_force)
        if norm <= options.tol * scale and abs(gap) <= options.tol * max(abs(target), 1e-12):
            return True, u, load_factor, iteration, norm, history, None

        n_free = free.size
        bordered = np.zeros((n_free + 1, n_free + 1))
        bordered[:n_free, :n_free] = k_mat[np.ix_(free, free)]
        bordered[:n_free, n_free] = -model.load_vector()[free]
        bordered[n_free, local] = 1.0
        rhs = np.concatenate((-r_free, [gap]))

        try:
            delta = np.linalg.solve(bordered, rhs)
        except np.linalg.LinAlgError:
            return False, u, load_factor, iteration, norm, history, FAILURE_SINGULAR_TANGENT

        if not np.all(np.isfinite(delta)):
            return False, u, load_factor, iteration, norm, history, FAILURE_NONFINITE

        u[free] += delta[:n_free]
        load_factor += float(delta[n_free])

    return False, u, load_factor, options.max_iter, norm, history, FAILURE_MAX_ITERATIONS


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def solve(model: Model, options: SolverOptions | None = None) -> SolveResult:
    """Trace the equilibrium path with adaptive stepping."""
    options = options or SolverOptions()
    free = model.free_dofs()

    if options.n_steps < 1:
        raise SolverError("n_steps must be >= 1")
    if options.control == "displacement" and options.control_dof is None:
        raise SolverError("displacement control requires control_dof")
    if options.control == "displacement" and options.control_dof not in set(free.tolist()):
        raise SolverError("control_dof must be a free DOF")

    target = float(options.target_displacement) if options.control == "displacement" else 1.0
    if target == 0.0:
        raise SolverError("control target must be non-zero")

    u = np.zeros(model.dof_count)
    load_factor = 0.0
    steps: list[StepRecord] = []
    failures: list[FailedAttempt] = []

    # Signed: the control target may be negative (e.g. a downward displacement).
    base_step = target / options.n_steps
    step = base_step
    min_step = abs(base_step) * options.min_step_ratio
    current = 0.0
    cutbacks = 0
    tolerance = abs(target) * 1e-12

    while abs(target) - abs(current) > tolerance:
        if abs(step) < min_step:
            return SolveResult(
                converged=False,
                control=options.control,
                load_factor=load_factor,
                control_value=current,
                u=u,
                steps=steps,
                failures=failures,
                failure=FAILURE_STEP_EXHAUSTED,
                message=(
                    f"increment fell below the minimum step ({min_step:.3e}) before reaching "
                    f"the target; last converged control value {current:.6g}"
                ),
                options=options,
            )

        remaining = target - current
        trial_step = step if abs(step) < abs(remaining) else remaining
        trial = current + trial_step

        if options.control == "load":
            ok, u_new, iters, norm, history, failure = _newton_load(model, u, trial, options)
            new_load_factor = trial
        else:
            ok, u_new, new_load_factor, iters, norm, history, failure = _newton_displacement(
                model, u, load_factor, trial, options
            )

        if ok:
            u = u_new
            current = trial
            load_factor = new_load_factor
            steps.append(
                StepRecord(
                    step=len(steps),
                    control_start=current - trial_step,
                    control_end=current,
                    load_factor=load_factor,
                    iterations=iters,
                    residual_norm=norm,
                    max_displacement=float(np.max(np.abs(u))),
                    residual_history=history,
                )
            )
            cutbacks = 0
            if options.step_growth > 1.0:
                grown = step * options.step_growth
                step = grown if abs(grown) < abs(base_step) else base_step
            continue

        failures.append(
            FailedAttempt(
                step=len(steps),
                control_start=current,
                control_trial=trial,
                failure=failure or "unknown",
                iterations=iters,
                residual_norm=norm,
                residual_history=history,
            )
        )

        if not options.adaptive:
            return SolveResult(
                converged=False,
                control=options.control,
                load_factor=load_factor,
                control_value=current,
                u=u,
                steps=steps,
                failures=failures,
                failure=failure,
                message=(
                    f"increment to {trial:.6g} failed ({failure}) and adaptive stepping is off; "
                    f"last converged control value {current:.6g}"
                ),
                options=options,
            )

        cutbacks += 1
        if cutbacks > options.max_cutbacks:
            return SolveResult(
                converged=False,
                control=options.control,
                load_factor=load_factor,
                control_value=current,
                u=u,
                steps=steps,
                failures=failures,
                failure=FAILURE_STEP_EXHAUSTED,
                message=(
                    f"{cutbacks} consecutive cutbacks without progress; "
                    f"last converged control value {current:.6g}"
                ),
                options=options,
            )

        step *= 0.5

    return SolveResult(
        converged=True,
        control=options.control,
        load_factor=load_factor,
        control_value=current,
        u=u,
        steps=steps,
        failures=failures,
        failure=None,
        message=f"reached the target in {len(steps)} accepted increments",
        options=options,
    )


def limit_point(result: SolveResult) -> dict[str, Any] | None:
    """Best estimate of the last stable equilibrium point before failure."""
    if result.converged or not result.steps:
        return None
    last = result.steps[-1]
    return {
        "control_value": last.control_end,
        "load_factor": last.load_factor,
        "max_displacement": last.max_displacement,
        "rejected_after": len(result.failures),
    }
