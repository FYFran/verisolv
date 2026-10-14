"""Constrained design search on top of the verified nonlinear solver.

The point of this module is not to be the fastest optimiser.  It is to make a
structural optimisation loop whose *answers can be trusted*:

* every candidate is analysed with the same nonlinear solver used everywhere
  else, so a design that only works in a linearised world is never accepted;
* constraints are checked against physics the solver actually reports --
  axial stress and nodal displacement at the converged state;
* the design that wins is put through the full independent verification suite
  before it is handed to anyone, because "the optimiser liked it" is not
  evidence.

Screening and verification are deliberately separated.  A search may evaluate
hundreds of candidates cheaply; only the winner pays for the rigorous checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import numpy as np

from .fem import Model, bar_forces
from .sections import CircularTube, Section, critical_load, slenderness
from .solver import SolveResult, SolverOptions, solve
from .verify import VerificationReport, verify


@dataclass
class Constraints:
    """Allowable limits a candidate design has to respect.

    ``max_stress`` is compared against the **Cauchy (engineering) stress** that
    :mod:`verisolv.fem` now reports alongside the second Piola-Kirchhoff stress,
    because allowable stresses in every design code are written in that measure.
    The two coincide only in the small-strain limit, and this project works
    outside it.

    ``buckling_factor`` applies to compression members only.  A two-force bar
    element cannot represent buckling in its stiffness, so a design that is
    "feasible" on stress alone can still be one that would collapse in service.
    The check below closes that gap explicitly rather than pretending the
    element handles it.
    """

    max_stress: float                 # Pa, |engineering stress| in any bar
    max_deflection: float             # m, largest nodal displacement
    load_factor: float = 1.0          # fraction of the reference load case
    buckling_factor: float = 2.0      # required N_cr / |N_compressive|
    section: Section = field(default_factory=CircularTube)
    k_factor: float = 1.0             # effective-length factor for N_cr
    search_margin: float = 0.98       # search against 98% of each allowable

    def describe(self) -> dict[str, Any]:
        return {
            "max_stress_Pa": self.max_stress,
            "max_stress_measure": "engineering (nominal) stress N/A0",
            "max_deflection_m": self.max_deflection,
            "load_factor": self.load_factor,
            "buckling_factor": self.buckling_factor,
            "buckling_curve": "Johnson parabola below C_c, Euler above",
            "k_factor": self.k_factor,
            "k_factor_note": "truss joints treated as pinned, so K = 1",
            "search_margin": self.search_margin,
            **self.section.describe(),
        }

    def targets(self) -> tuple[float, float, float]:
        """The tightened limits the search actually aims at.

        Driving utilisation to exactly 100% makes the reported design a
        boundary case: the smallest change of stress measure, section family or
        solver tolerance flips an independent re-check to "infeasible".  Real
        design practice leaves margin, so the search does too -- and the result
        is a design that stays feasible when somebody else checks it.
        """
        return (
            self.max_stress * self.search_margin,
            self.max_deflection * self.search_margin,
            self.buckling_factor / self.search_margin,
        )


@dataclass
class Candidate:
    """One evaluated design."""

    areas: dict[str, float]
    mass: float
    feasible: bool
    converged: bool
    max_stress: float
    max_deflection: float
    load_factor: float
    violations: list[str] = field(default_factory=list)
    failure: str | None = None
    verified: bool = False
    verdict: str | None = None
    min_buckling_ratio: float | None = None   # min over bars of N_cr/|N_comp|
    governing_bar: int | None = None          # bar with the worst utilisation

    def to_dict(self) -> dict[str, Any]:
        return {
            "areas": {k: float(v) for k, v in self.areas.items()},
            "mass": float(self.mass),
            "feasible": self.feasible,
            "converged": self.converged,
            "max_stress": float(self.max_stress),
            "max_deflection": float(self.max_deflection),
            "load_factor": float(self.load_factor),
            "violations": list(self.violations),
            "failure": self.failure,
            "verified": self.verified,
            "verdict": self.verdict,
            "min_buckling_ratio": (
                float(self.min_buckling_ratio) if self.min_buckling_ratio is not None else None
            ),
            "governing_bar": self.governing_bar,
        }


@dataclass
class OptimizeResult:
    best: Candidate | None
    history: list[Candidate]
    evaluations: int
    verified: bool
    verdict: str
    message: str
    report: VerificationReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "best": self.best.to_dict() if self.best else None,
            "evaluations": self.evaluations,
            "verified": self.verified,
            "verdict": self.verdict,
            "message": self.message,
            "history_tail": [c.to_dict() for c in self.history[-8:]],
            "verification": self.report.to_dict() if self.report else None,
        }


class OptimizeError(RuntimeError):
    """Raised for an unusable optimisation request."""


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate(
    make_model: Callable[[dict[str, float]], Model],
    areas: dict[str, float],
    constraints: Constraints,
    options: SolverOptions | None = None,
) -> Candidate:
    """Analyse one design and score it against the constraints.

    Three things are checked, all at the converged nonlinear state:

    1. **Stress**, measured as Cauchy stress so it is comparable with the
       allowable -- see the note on :class:`Constraints`.
    2. **Deflection**, the largest nodal displacement.
    3. **Buckling**, per compression member.  This is the check that makes the
       answer a *design* rather than an arithmetic exercise: a two-force bar
       carries no bending stiffness in this formulation, so nothing else in the
       pipeline would ever notice a member that is too slender to do its job.

    A design that fails to solve is infeasible, not an exception: the search must
    be able to walk through a region where the structure cannot carry the load.
    """
    model = make_model(areas)
    options = options or SolverOptions(
        control="load", n_steps=6, max_iter=40, adaptive=True
    )
    result: SolveResult = solve(model, options)
    mass = model.total_mass({k: float(v) for k, v in areas.items()})
    normalised = {k: float(v) for k, v in areas.items()}

    if not result.converged or result.u is None:
        return Candidate(
            areas=normalised,
            mass=float(mass),
            feasible=False,
            converged=False,
            max_stress=float("nan"),
            max_deflection=float("nan"),
            load_factor=float(result.load_factor),
            violations=["analysis did not converge"],
            failure=result.failure,
        )

    from .fem import assemble

    _, _, states = assemble(model, result.u)
    max_stress = float(np.max([abs(s.engineering_stress) for s in states]))
    max_deflection = float(np.max(np.abs(result.u)))

    # Check against the tightened targets, not the bare allowables: see
    # Constraints.targets().  The values reported back are the measured ones.
    stress_limit, deflection_limit, buckling_limit = constraints.targets()

    violations: list[str] = []
    if max_stress > stress_limit:
        violations.append(
            f"stress {max_stress / 1e6:.2f} MPa exceeds the design target "
            f"{stress_limit / 1e6:.2f} MPa (allowable {constraints.max_stress / 1e6:.1f} MPa "
            f"x margin {constraints.search_margin:g})"
        )
    if max_deflection > deflection_limit:
        violations.append(
            f"deflection {max_deflection * 1e3:.3f} mm exceeds the design target "
            f"{deflection_limit * 1e3:.3f} mm"
        )

    # Buckling: only compression members can buckle, and only they are checked.
    # The strength used is the Johnson/Euler critical stress, so a stocky member
    # is governed by yield rather than by a buckling load it could never reach.
    #
    # Limitation: the check is evaluated at the converged target state only.  For
    # a monotonically loaded structure that is the governing state; a structure
    # whose compression peaks mid-path would need a path envelope instead.
    min_ratio = float("inf")
    governing: int | None = None
    worst_slenderness = 0.0
    for index, state in enumerate(states):
        if not state.in_compression or state.axial_force == 0.0:
            continue
        bar = model.bars[index]
        n_cr = critical_load(
            bar.modulus,
            bar.yield_stress,
            state.area,
            state.reference_length,
            constraints.section,
            constraints.k_factor,
        )
        ratio = n_cr / abs(state.axial_force)
        if ratio < min_ratio:
            min_ratio = ratio
            governing = index
            worst_slenderness = slenderness(
                state.area, state.reference_length, constraints.section, constraints.k_factor
            )

    if governing is not None and min_ratio < buckling_limit:
        violations.append(
            f"bar {governing} buckling: N_cr/|N| = {min_ratio:.2f} < target "
            f"{buckling_limit:.2f} (slenderness KL/r = {worst_slenderness:.0f})"
        )

    return Candidate(
        areas=normalised,
        mass=float(mass),
        feasible=not violations,
        converged=True,
        max_stress=max_stress,
        max_deflection=max_deflection,
        load_factor=float(result.load_factor),
        violations=violations,
        min_buckling_ratio=(None if governing is None else min_ratio),
        governing_bar=governing,
    )


# ---------------------------------------------------------------------------
# Search: constraint-aware pattern search
# ---------------------------------------------------------------------------


def _clamp(value: float, low: float, high: float) -> float:
    return float(min(max(value, low), high))


def pattern_search(
    make_model: Callable[[dict[str, float]], Model],
    start: dict[str, float],
    constraints: Constraints,
    lower: dict[str, float],
    upper: dict[str, float],
    options: SolverOptions | None = None,
    max_iterations: int = 40,
    shrink: float = 0.6,
    verbose: bool = False,
) -> tuple[Candidate | None, list[Candidate], int]:
    """Minimise mass subject to the constraints, by shrinking pattern moves.

    The classic difficulty with penalty-free sizing is that the feasible region
    is bounded by behaviour, not by the box.  This search therefore never
    accepts a move that makes the design infeasible, and only shrinks the step
    when no feasible improvement exists -- so it walks *along* the constraint
    boundary rather than into it.
    """
    groups = list(start)
    span = {g: (upper[g] - lower[g]) for g in groups}
    step = {g: 0.25 * span[g] for g in groups}

    evaluations = 0
    history: list[Candidate] = []

    current = evaluate(make_model, start, constraints, options)
    evaluations += 1
    history.append(current)

    for _ in range(max_iterations):
        improved = False
        for group in groups:
            for direction in (-1.0, 1.0):
                trial_areas = dict(current.areas)
                trial_areas[group] = _clamp(
                    current.areas[group] + direction * step[group], lower[group], upper[group]
                )
                if trial_areas[group] == current.areas[group]:
                    continue
                trial = evaluate(make_model, trial_areas, constraints, options)
                evaluations += 1
                history.append(trial)
                if trial.feasible and (
                    not current.feasible or trial.mass < current.mass - 1e-9
                ):
                    current = trial
                    improved = True
                    if verbose:
                        print(
                            f"  accept {group}{'+' if direction > 0 else '-'} "
                            f"-> mass {trial.mass:.3f} kg"
                        )
                    break
            if improved:
                break
        if not improved:
            for group in groups:
                step[group] *= shrink
            if max(step.values()) < 1e-6 * max(span.values()):
                break

    return (current if current.feasible else None), history, evaluations


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def optimize(
    make_model: Callable[[dict[str, float]], Model],
    start: dict[str, float],
    constraints: Constraints,
    lower: dict[str, float],
    upper: dict[str, float],
    solver_options: SolverOptions | None = None,
    max_iterations: int = 40,
    verify_best: bool = True,
    verify_kwargs: dict[str, Any] | None = None,
    verbose: bool = False,
) -> OptimizeResult:
    """Search for the lightest feasible design, then verify the winner.

    ``verify_best`` runs the full independent verification suite on the winning
    design.  The returned ``verified`` flag is what a caller should treat as
    permission to believe the number.
    """
    for group in start:
        if group not in lower or group not in upper:
            raise OptimizeError(f"missing bounds for design variable {group!r}")
        if lower[group] <= 0 or upper[group] < lower[group]:
            raise OptimizeError(f"invalid bounds for {group!r}")
    if constraints.max_stress <= 0 or constraints.max_deflection <= 0:
        raise OptimizeError("constraints must be positive")

    best, history, evaluations = pattern_search(
        make_model,
        start,
        constraints,
        lower,
        upper,
        options=solver_options,
        max_iterations=max_iterations,
        verbose=verbose,
    )

    if best is None:
        return OptimizeResult(
            best=None,
            history=history,
            evaluations=evaluations,
            verified=False,
            verdict="no_feasible_design",
            message=(
                "no feasible design found within the box; the search never reached a "
                "state that satisfies both stress and deflection limits"
            ),
        )

    report: VerificationReport | None = None
    verdict = "unverified"
    if verify_best:
        model = make_model(best.areas)
        options = solver_options or SolverOptions(
            control="load", n_steps=6, max_iter=40, adaptive=True
        )
        result = solve(model, options)
        if result.converged:
            report = verify(model, result, **(verify_kwargs or {}))
            verdict = report.verdict
            best.verified = verdict == "verified"
            best.verdict = verdict
        else:
            verdict = "not_converged"

    return OptimizeResult(
        best=best,
        history=history,
        evaluations=evaluations,
        verified=best.verified,
        verdict=verdict,
        message=(
            f"lightest feasible design: {best.mass:.3f} kg "
            f"(evaluated {evaluations} designs); verification verdict {verdict}"
        ),
        report=report,
    )
