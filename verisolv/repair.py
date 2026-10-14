"""Diagnosis and repair: turn a failed or untrustworthy analysis into a good one.

The escalation is deliberately explicit.  A failure carries different meaning
depending on *how* the iteration failed, and the right response differs:

======  ==========================================  ==============================
Failure What it means                               First response
======  ==========================================  ==============================
stall   residual frozen near a limit point          displacement control
jump    converged onto a different branch           displacement control
diverge residual growing without bound              smaller steps + line search
singular tangent stiffness is singular              displacement control
exhaust increments shrank to nothing without progress  displacement control
======  ==========================================  ==============================

Switching control variable is the only one of these that fixes a limit point:
no amount of step refinement lets a load-controlled iteration pass a maximum of
the equilibrium path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .fem import Model, assemble
from .solver import (
    FAILURE_DIVERGED,
    FAILURE_MAX_ITERATIONS,
    FAILURE_NONFINITE,
    FAILURE_SINGULAR_TANGENT,
    FAILURE_STEP_EXHAUSTED,
    SolveResult,
    SolverOptions,
    limit_point,
    solve,
)
from .verify import VerificationReport, claim_level, verify

# Diagnosis kinds
LIMIT_POINT = "limit_point"
BRANCH_JUMP = "branch_jump"
DIVERGENCE = "divergence"
SINGULAR = "singular_tangent"
INCREMENT_EXHAUSTED = "increment_exhausted"
NONFINITE = "nonfinite"
MECHANISM = "rigid_body_mechanism"
UNKNOWN = "unknown"

# Diagnoses a change of control variable or increment can plausibly fix.  A
# mechanism is deliberately not among them: the fault is in the model.
REPAIRABLE = frozenset({LIMIT_POINT, BRANCH_JUMP, DIVERGENCE, SINGULAR, INCREMENT_EXHAUSTED})


@dataclass
class Diagnosis:
    kind: str
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class Strategy:
    name: str
    rationale: str
    options: SolverOptions


@dataclass
class RepairAttempt:
    strategy: str
    rationale: str
    result: SolveResult
    report: VerificationReport | None = None
    accepted: bool = False


@dataclass
class RepairOutcome:
    solved: bool
    diagnosis: Diagnosis
    result: SolveResult
    report: VerificationReport | None
    attempts: list[RepairAttempt] = field(default_factory=[])
    claim_level_value: str = "smoke"

    def to_dict(self) -> dict[str, Any]:
        return {
            "solved": self.solved,
            "diagnosis": {
                "kind": self.diagnosis.kind,
                "summary": self.diagnosis.summary,
                "evidence": self.diagnosis.evidence,
            },
            "final": self.result.summary(),
            "verification": self.report.to_dict() if self.report else None,
            "claim_level": self.claim_level_value,
            "attempts": [
                {
                    "strategy": a.strategy,
                    "rationale": a.rationale,
                    "accepted": a.accepted,
                    "result": a.result.summary(),
                    "verdict": a.report.verdict if a.report else None,
                }
                for a in self.attempts
            ],
        }


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------


def _zero_load_deficiency(model: Model, threshold: float = 1e-12) -> tuple[bool, float]:
    """Is the tangent stiffness singular before any load is applied?

    Returns ``(deficient, ratio)`` where ``ratio`` is the smallest singular value
    of the free-free stiffness divided by the largest -- a scale-free measure of
    how close the structure is to being a mechanism.  A structure that can move
    without straining anything produces a zero there, at zero load, regardless of
    what the load case later asks of it.
    """
    _, k_mat, _ = assemble(model, np.zeros(model.dof_count))
    free = model.free_dofs()
    if free.size == 0:
        return False, float("inf")
    k_free = k_mat[np.ix_(free, free)]
    try:
        singular_values = np.linalg.svd(k_free, compute_uv=False)
    except np.linalg.LinAlgError:
        return True, 0.0
    largest = float(singular_values[0])
    if largest <= 0.0:
        return True, 0.0
    ratio = float(singular_values[-1]) / largest
    return ratio < threshold, ratio


def diagnose(model: Model, result: SolveResult, report: VerificationReport | None = None) -> Diagnosis:
    """Explain what went wrong, using the failure mode and the residual history."""
    if result.converged and report is not None and report.verdict != "verified":
        bad = report.failures()
        kinds = {c.name for c in bad}
        if "path_continuity" in kinds:
            jump = next(c for c in bad if c.name == "path_continuity")
            return Diagnosis(
                BRANCH_JUMP,
                (
                    "the iteration converged but the equilibrium path is discontinuous; "
                    "the solver escaped to a different branch instead of tracing the real one"
                ),
                jump.evidence,
            )
        return Diagnosis(
            UNKNOWN,
            f"converged but verification verdict is {report.verdict}",
            {"failed_checks": sorted(kinds)},
        )

    if result.converged:
        return Diagnosis("converged", "analysis converged and verified", {})

    # Rule out a mechanism before blaming the increment.
    #
    # This check has to come first.  A structure with a rigid-body mode does not
    # announce itself as a singular tangent: in practice it surfaces as
    # "divergence" or "step exhaustion", because the iteration chases a solution
    # that does not exist and the driver cuts the step until it gives up.  A
    # reader of those diagnoses would reduce the increment -- which can never
    # work, because the problem is in the model, not the stepping.
    #
    # Asking whether the tangent is already singular at ZERO load separates the
    # two cleanly: no load, no limit point, so a singular tangent there can only
    # mean the structure is free to move.
    deficient, ratio = _zero_load_deficiency(model)
    if deficient:
        return Diagnosis(
            MECHANISM,
            (
                "the tangent stiffness is singular before any load is applied, so the "
                "structure has a rigid-body mode: it is a mechanism, not a structure. "
                "No change of increment size or control variable can fix this; a "
                "restraint is missing or the model is otherwise under-constrained"
            ),
            {
                "zero_load_stiffness_ratio": ratio,
                "failure_observed": result.failure,
                "rejected_increments": len(result.failures),
                "hint": "check the supports: a translation or rotation is unrestrained",
            },
        )

    history = result.failures[-1].residual_history if result.failures else []
    stalled = False
    residual_stats: dict[str, Any] = {}
    if len(history) >= 4:
        first, best, last = history[0], min(history), history[-1]
        # A limit point shows a characteristic signature: the residual falls a long
        # way, then stops improving and oscillates in a band.  Divergence looks
        # different -- either it never improves, or it improves and then runs away.
        improved = best <= 0.1 * first
        growing = last > 10.0 * best
        stalled = improved and not growing
        residual_stats = {
            "residual_first": first,
            "residual_best": best,
            "residual_last": last,
            "improved_by": first / max(best, 1e-30),
            "final_over_best": last / max(best, 1e-30),
        }

    lp = limit_point(result)
    common: dict[str, Any] = {
        "failure": result.failure,
        "last_converged_control": result.control_value,
        "last_converged_load_factor": result.load_factor,
        "rejected_increments": len(result.failures),
        "final_residual_history": [f"{v:.4e}" for v in history[-6:]],
        **residual_stats,
    }
    if lp:
        common["limit_point_estimate"] = lp

    if result.failure == FAILURE_MAX_ITERATIONS and stalled:
        return Diagnosis(
            LIMIT_POINT,
            (
                "the residual stopped decreasing without growing: the iteration is pressed "
                "against a limit point of the equilibrium path, where the tangent stiffness "
                "becomes singular and no load increment can make progress"
            ),
            {**common, "residual_stalled": True},
        )
    if result.failure in (FAILURE_MAX_ITERATIONS, FAILURE_DIVERGED):
        return Diagnosis(
            DIVERGENCE,
            "the residual grew instead of settling; the increment is too large for this state",
            {**common, "residual_stalled": stalled},
        )
    if result.failure == FAILURE_SINGULAR_TANGENT:
        return Diagnosis(
            SINGULAR,
            "the tangent stiffness matrix became singular",
            common,
        )
    if result.failure == FAILURE_STEP_EXHAUSTED:
        return Diagnosis(
            INCREMENT_EXHAUSTED,
            (
                "the increment was reduced repeatedly without progress; the analysis is "
                "pinned against a limit point or the step floor"
            ),
            common,
        )
    if result.failure == FAILURE_NONFINITE:
        return Diagnosis(NONFINITE, "the iteration produced non-finite values", common)
    return Diagnosis(UNKNOWN, f"unclassified failure: {result.failure}", common)


# ---------------------------------------------------------------------------
# Strategy planning
# ---------------------------------------------------------------------------


def auto_control_dof(model: Model) -> tuple[int, float]:
    """Pick the free DOF that moves most under a linear analysis of the load.

    Returns ``(dof, signed_linear_displacement)``.  The largest-response DOF is
    the natural quantity to prescribe when the load path folds back on itself.
    """
    free = model.free_dofs()
    _, k_mat, _ = assemble(model, np.zeros(model.dof_count))
    k_free = k_mat[np.ix_(free, free)]
    try:
        u_free = np.linalg.solve(k_free, model.load_vector()[free])
    except np.linalg.LinAlgError as exc:  # pragma: no cover - defensive
        raise RuntimeError("cannot auto-select a control DOF: linear system is singular") from exc
    local = int(np.argmax(np.abs(u_free)))
    return int(free[local]), float(u_free[local])


def plan(
    diagnosis: Diagnosis,
    model: Model,
    base: SolverOptions,
    *,
    target_displacement: float | None = None,
    displacement_target_factor: float = 4.0,
) -> list[Strategy]:
    """Ordered strategies to try, most likely to work first."""
    # A mechanism is not a numerical problem.  Running the escalation would burn
    # solver time to reach a conclusion already known -- nothing about the
    # increment or the control variable can make an unconstrained structure
    # determinate -- and worse, it would imply the fault might be numerical when
    # it is in the model.  Say so and stop.
    if diagnosis.kind == MECHANISM:
        return []

    strategies: list[Strategy] = []

    wants_displacement = diagnosis.kind in {LIMIT_POINT, BRANCH_JUMP, SINGULAR, INCREMENT_EXHAUSTED}
    if wants_displacement:
        dof, linear = auto_control_dof(model)
        if target_displacement is None:
            reference = abs(linear) if abs(linear) > 0 else 1.0
            target_displacement = float(np.sign(linear) or 1.0) * reference * displacement_target_factor
        strategies.append(
            Strategy(
                "displacement_control",
                (
                    "prescribe the displacement component with the largest linear response and "
                    "treat the load factor as an unknown; this is the only strategy that can "
                    "pass a limit point"
                ),
                base.replace(
                    control="displacement",
                    control_dof=dof,
                    target_displacement=float(target_displacement),
                    n_steps=max(base.n_steps, 40),
                    adaptive=True,
                ),
            )
        )

    # Each strategy must establish a *workable floor*, not merely scale whatever
    # the caller passed in.
    #
    # Scaling alone assumes the incoming options are reasonable and only need one
    # knob turned.  When the caller hands over a pathological configuration -- a
    # single increment with a six-iteration budget, say -- every strategy inherits
    # the pathology: refining the increment to 40 steps is useless while the
    # iteration budget is still six, and "try smaller steps" is meaningless with
    # adaptive stepping switched off.  The case library caught exactly this: three
    # strategies, three failures, all for the same inherited reason.
    MIN_ITER = 40
    MIN_STEPS = 20

    def floored(**overrides: Any) -> SolverOptions:
        merged = {
            "max_iter": max(base.max_iter, MIN_ITER),
            "n_steps": max(base.n_steps, MIN_STEPS),
            "adaptive": True,
        }
        merged.update(overrides)
        return base.replace(**merged)

    strategies.append(
        Strategy(
            "refined_increments",
            "refine the increment size so the iteration starts closer to the solution, "
            "with an iteration budget large enough to use it",
            floored(n_steps=max(base.n_steps * 4, MIN_STEPS * 2)),
        )
    )
    strategies.append(
        Strategy(
            "line_search",
            "add backtracking so an overshooting Newton update is damped instead of accepted",
            floored(line_search=True, max_iter=max(base.max_iter * 2, MIN_ITER * 2)),
        )
    )
    strategies.append(
        Strategy(
            "robust_combo",
            "combine fine increments, damping and a larger iteration budget",
            floored(
                n_steps=max(base.n_steps * 8, MIN_STEPS * 4),
                max_iter=max(base.max_iter * 3, MIN_ITER * 3),
                line_search=True,
            ),
        )
    )
    return strategies


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def repair(
    model: Model,
    base: SolverOptions | None = None,
    *,
    target_displacement: float | None = None,
    verify_kwargs: dict[str, Any] | None = None,
    max_attempts: int = 4,
) -> RepairOutcome:
    """Solve, verify, diagnose, escalate -- and stop at the first verified answer."""
    base = base or SolverOptions()
    verify_kwargs = verify_kwargs or {}

    first = solve(model, base)
    first_report = verify(model, first, **verify_kwargs) if first.converged else None

    if first.converged and first_report is not None and first_report.verdict == "verified":
        return RepairOutcome(
            solved=True,
            diagnosis=Diagnosis("converged", "solved and verified without repair", {}),
            result=first,
            report=first_report,
            attempts=[],
            claim_level_value=claim_level(first_report, first),
        )

    diagnosis = diagnose(model, first, first_report)
    attempts: list[RepairAttempt] = []
    best: tuple[SolveResult, VerificationReport | None] | None = None

    # The escalation is a *loop*, not a fixed list.
    #
    # A strategy that fixes the symptom it was chosen for can expose the next
    # problem underneath.  Refining the increments of a run that diverged may
    # produce a converged solution that has silently jumped equilibrium branches
    # -- a different fault, needing a different response, and invisible to a plan
    # written before the first attempt was made.  So after every attempt that
    # fails verification, the failure is re-diagnosed and any strategy the new
    # diagnosis suggests is appended to the queue.
    queue: list[Strategy] = plan(
        diagnosis, model, base, target_displacement=target_displacement
    )
    tried: set[str] = set()
    index = 0

    while index < len(queue) and len(attempts) < max_attempts:
        strategy = queue[index]
        index += 1
        if strategy.name in tried:
            continue
        tried.add(strategy.name)

        candidate = solve(model, strategy.options)
        report = verify(model, candidate, **verify_kwargs) if candidate.converged else None
        accepted = bool(candidate.converged and report is not None and report.verdict == "verified")
        attempts.append(
            RepairAttempt(
                strategy=strategy.name,
                rationale=strategy.rationale,
                result=candidate,
                report=report,
                accepted=accepted,
            )
        )
        if accepted:
            return RepairOutcome(
                solved=True,
                diagnosis=diagnosis,
                result=candidate,
                report=report,
                attempts=attempts,
                claim_level_value=claim_level(report, candidate),
            )
        if candidate.converged and best is None:
            best = (candidate, report)

        # Re-diagnose whatever this attempt produced, and let the plan grow.
        if candidate.converged and report is not None and report.verdict != "verified":
            follow_up = diagnose(model, candidate, report)
            for extra in plan(
                follow_up, model, base, target_displacement=target_displacement
            ):
                if extra.name not in tried and extra.name not in {s.name for s in queue[index:]}:
                    queue.append(extra)

    if best is not None:
        return RepairOutcome(
            solved=False,
            diagnosis=diagnosis,
            result=best[0],
            report=best[1],
            attempts=attempts,
            claim_level_value=claim_level(best[1], best[0]) if best[1] else "smoke",
        )
    return RepairOutcome(
        solved=False,
        diagnosis=diagnosis,
        result=first,
        report=first_report,
        attempts=attempts,
        claim_level_value=(
            claim_level(first_report, first) if first_report else "smoke"
        ),
    )
