"""Independent verification of a solved state.

A solver returning ``converged=True`` is a claim, not evidence.  Every check in
this module re-derives something the solver already asserted, using different
information:

* the residual is rebuilt from scratch at the reported state;
* global force and moment balance are checked against the support reactions;
* the equilibrium path is tested for continuity, which is what exposes a
  silent branch jump;
* the whole analysis is re-run with a different step size and the answers are
  compared -- a state that is not reproducible under refinement is not a state
  worth reporting.

The output is a structured report so that a caller (or an agent) can act on
individual failures rather than on a single opaque boolean.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .fem import Model, assemble, reactions
from .gci import GCIResult, evaluate_quantity_over_steps
from .solver import SolveResult, SolverOptions, solve

CRITICAL = "critical"
MAJOR = "major"
MINOR = "minor"


@dataclass
class Check:
    name: str
    passed: bool
    severity: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationReport:
    checks: list[Check]
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "severity": c.severity,
                    "detail": c.detail,
                    "evidence": c.evidence,
                }
                for c in self.checks
            ],
        }

    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]


def _verdict(checks: list[Check]) -> str:
    if any(not c.passed and c.severity == CRITICAL for c in checks):
        return "rejected"
    if any(not c.passed for c in checks):
        return "suspect"
    return "verified"


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_residual(model: Model, result: SolveResult, tol: float = 1e-6) -> Check:
    """Rebuild the out-of-balance force at the reported state."""
    if result.u is None:
        return Check(
            "residual", False, CRITICAL, "no solution state to verify", {"reason": "u is None"}
        )

    free = model.free_dofs()
    f_int, _, _ = assemble(model, result.u)
    r = f_int - result.load_factor * model.load_vector()
    r_free = float(np.linalg.norm(r[free]))
    f_ext = float(np.linalg.norm(result.load_factor * model.load_vector()[free]))
    rel = r_free / max(f_ext, 1.0)

    passed = rel <= tol
    return Check(
        "residual",
        passed,
        CRITICAL,
        f"relative residual {rel:.3e} at the reported state (tolerance {tol:.1e})",
        {"abs_residual": r_free, "rel_residual": rel, "tolerance": tol},
    )


def check_global_equilibrium(model: Model, result: SolveResult, tol: float = 1e-6) -> Check:
    """Force and moment balance between applied loads and support reactions.

    Two facts make this an independent statement about the answer rather than a
    restatement of the convergence test:

    * bar internal forces cancel node by node, so the assembled internal force
      vector sums to zero over every DOF;
    * that cancellation holds *in the current configuration*, because a two-force
      member exerts collinear forces there and only there.

    The second point is why the moments below are taken about the deformed
    coordinates.  Using the reference coordinates introduces an error that grows
    with displacement -- negligible for a shallow truss, large enough to trip the
    tolerance on a flexible cantilever.
    """
    if result.u is None:
        return Check("global_equilibrium", False, CRITICAL, "no solution state", {})

    u = result.u
    react = reactions(model, u, result.load_factor)
    applied = result.load_factor * model.load_vector()

    force = react + applied
    force_res = float(np.linalg.norm(force.reshape(-1, 2).sum(axis=0)))

    current = model.coords + u.reshape(-1, 2)
    moment = 0.0
    for node in range(model.node_count):
        x, y = current[node]
        moment += x * force[2 * node + 1] - y * force[2 * node]
    moment_res = abs(float(moment))

    scale = max(float(np.linalg.norm(applied.reshape(-1, 2).sum(axis=0))), 1.0)
    force_rel = force_res / scale
    moment_scale = max(float(np.abs(current).max()) * scale, 1.0)
    moment_rel = moment_res / moment_scale

    passed = force_rel <= tol and moment_rel <= tol
    return Check(
        "global_equilibrium",
        passed,
        MAJOR,
        f"force imbalance {force_rel:.3e}, moment imbalance {moment_rel:.3e}",
        {
            "force_residual": force_res,
            "force_relative": force_rel,
            "moment_residual": moment_res,
            "moment_relative": moment_rel,
            "reaction_sum": react.reshape(-1, 2).sum(axis=0).tolist(),
            "applied_sum": applied.reshape(-1, 2).sum(axis=0).tolist(),
            "moment_coordinates": "deformed",
        },
    )


def check_path_continuity(result: SolveResult, jump_factor: float = 20.0) -> Check:
    """Flag discontinuities between accepted increments.

    A converged run is not necessarily a *continuous* run.  Near a limit point
    Newton-Raphson can escape to a remote equilibrium and report success, while
    the equilibrium path it claims to have traced is broken.  Comparing the
    largest increment against the median is a cheap, honest detector.

    Too few increments to judge is a **failure**, not a pass.  Returning "passed"
    when the check could not run would be fail-open behaviour, and it would
    contradict the only thing this module exists to do: refuse to vouch for what
    it has not actually established.
    A stationary path is a different matter, and conflating the two is a bug this
    check used to have.  With no load there is no motion to trace, so every
    increment is zero and the median increment is zero, which made the ratio
    infinite and the check report "suspect" for an answer that is *exactly* right:
    u = 0 satisfies equilibrium to machine precision.  Crying wolf on a trivially
    correct result teaches a reader to ignore the verdict, which costs more than
    the check is worth.  "Nothing to assess" and "nothing moved" are not the same
    finding, and the check now says which one it has.
    """
    drops = [s.max_displacement for s in result.steps]

    # Nothing moved, so there is no path that could be discontinuous.
    if drops and float(np.max(np.abs(drops))) == 0.0:
        return Check(
            "path_continuity",
            True,
            MAJOR,
            (
                "the path is stationary: every increment has zero displacement, which is "
                "the exact solution when no load is applied. There is no path to check"
            ),
            {
                "increments": len(drops),
                "max_displacement": 0.0,
                "stationary": True,
                "assessable": True,
            },
        )

    if len(drops) < 3:
        return Check(
            "path_continuity",
            False,
            MAJOR,
            (
                f"only {len(drops)} accepted increment(s): too few to assess continuity, "
                f"so the path cannot be vouched for"
            ),
            {"increments": len(drops), "assessable": False, "fail_reason": "insufficient_increments"},
        )

    inc = np.abs(np.diff(drops))
    median = float(np.median(inc))
    biggest = float(inc.max())
    index = int(np.argmax(inc))

    # Motion exists overall, but half the increments are numerically nothing. No
    # ratio can be formed against a zero median, and inventing one would be worse
    # than admitting the check cannot run.
    if median <= 0.0:
        return Check(
            "path_continuity",
            False,
            MAJOR,
            (
                f"the path moves overall (largest displacement "
                f"{float(np.max(np.abs(drops))):.4e} m) but the median increment is zero, "
                f"so no meaningful ratio can be formed and the path cannot be vouched for"
            ),
            {
                "increments": len(drops),
                "max_increment": biggest,
                "median_increment": 0.0,
                "assessable": False,
                "fail_reason": "degenerate_median_increment",
            },
        )

    ratio = biggest / median
    passed = ratio <= jump_factor
    return Check(
        "path_continuity",
        passed,
        MAJOR,
        (
            f"largest increment {biggest:.4e} m vs median {median:.4e} m "
            f"({ratio:,.1f}x) between steps {index} and {index + 1}"
        ),
        {
            "max_increment": biggest,
            "median_increment": median,
            "ratio": ratio,
            "jump_factor": jump_factor,
            "jump_between_steps": [index, index + 1],
        },
    )


def check_step_refinement(
    model: Model,
    result: SolveResult,
    refine: int = 2,
    tol: float = 1e-4,
) -> Check:
    """Re-run the analysis with a finer increment and compare the answers.

    This is the strongest general-purpose check available: it does not assume
    anything about *why* a result might be wrong, only that a trustworthy
    solution should not move when the discretisation of the path is changed.
    """
    if result.options is None or result.u is None:
        return Check(
            "step_refinement", False, MAJOR, "solver options unavailable; cannot re-run", {}
        )

    refined_options: SolverOptions = result.options.replace(
        n_steps=result.options.n_steps * refine,
        adaptive=result.options.adaptive,
    )
    refined = solve(model, refined_options)

    if not refined.converged:
        return Check(
            "step_refinement",
            False,
            MAJOR,
            f"refined run ({refined_options.n_steps} steps) did not converge: {refined.failure}",
            {
                "refined_steps": refined_options.n_steps,
                "refined_converged": False,
                "refined_failure": refined.failure,
            },
        )

    scale = max(float(np.max(np.abs(result.u))), 1e-12)
    du = float(np.max(np.abs(refined.u - result.u))) / scale
    dlam = abs(refined.load_factor - result.load_factor) / max(abs(result.load_factor), 1e-12)

    passed = du <= tol and dlam <= tol
    return Check(
        "step_refinement",
        passed,
        MAJOR,
        f"refined solution differs by {du:.3e} (displacement) and {dlam:.3e} (load factor)",
        {
            "refined_steps": refined_options.n_steps,
            "displacement_relative_difference": du,
            "load_factor_relative_difference": dlam,
            "tolerance": tol,
        },
    )


def check_gci(
    model: Model,
    result: SolveResult,
    n_steps: int = 20,
    r: float = 1.3,
) -> Check:
    """Quantified discretisation-error band, per quantity of interest (QoI).

    The step-refinement gate above answers a boolean question: does the
    answer move under refinement?  This gate answers the V&V literature's
    follow-up: *by how much?*  Three solves at fixed geometric increments
    (N, 1.3 N, 1.69 N) feed the Richardson/GCI recipe in :mod:`verisolv.gci`
    for each QoI.  Each QoI is reported on its own, because a quantity that
    has converged is not evidence that another one has.

    Severity is **minor** on purpose: this gate must never flip the verdict
    of the four existing gates.  Its role is to gate the *claim level*
    (signoff requires a usable GCI band), and its own failures are reported
    three-valued (pass / conditional / reject) inside the check evidence.

    When the solver has converged at the target on every sample -- or the
    samples are indistinguishable to the solver tolerance -- the sequence is
    *saturated at that resolution*: the discretisation error is already below
    what can be measured, and a GCI band is the honest refusal, not a
    failure of the answer itself.  The evidence says so, and ``claim_level``
    treats it accordingly (signoff stays out of reach; that is the point).
    """
    if result.options is None or result.u is None:
        return Check(
            "gci",
            False,
            MINOR,
            "solver options unavailable; GCI not run",
            {"gci_status": "not_run", "reason": "no_options"},
        )

    quantities: list[tuple[str, object]] = [
        (
            "load_factor",
            lambda res: float(res.load_factor),
        ),
        (
            "control_value",
            lambda res: float(res.control_value),
        ),
        (
            "max_displacement",
            lambda res: float(res.steps[-1].max_displacement) if res.steps else 0.0,
        ),
    ]

    results: list[GCIResult] = []
    for name, evaluator in quantities:
        try:
            _values, _steps, gci_result = evaluate_quantity_over_steps(
                model,
                result.options,
                evaluator,
                n_steps=n_steps,
                r=r,
                quantity=name,
                solve_kwargs={"tol": result.options.tol},
            )
        except Exception as exc:  # noqa: BLE001 - gate must not crash verify()
            results.append(
                GCIResult(
                    quantity=name,
                    status="reject",
                    detail=f"GCI could not be computed: {type(exc).__name__}: {exc}",
                )
            )
            continue
        results.append(gci_result)

    all_passed = all(g.status in ("pass", "conditional") for g in results)
    passed = all_passed and all(g.status == "pass" for g in results)

    detail_parts = [f"{g.quantity}: {g.status}" for g in results]
    evidence = {"gci_status": "pass" if passed else ("conditional" if all_passed else "reject"), "results": [g.to_dict() for g in results]}
    detail = "; ".join(detail_parts)
    if not passed:
        for g in results:
            if g.status != "pass":
                detail += f" | {g.quantity} ({g.status}): {g.detail}"

    return Check(
        "gci",
        passed,
        MINOR,
        detail,
        evidence,
    )


def verify(
    model: Model,
    result: SolveResult,
    *,
    tol_residual: float = 1e-6,
    tol_equilibrium: float = 1e-6,
    jump_factor: float = 20.0,
    refine: int = 2,
    tol_refinement: float = 1e-4,
    gci: bool = False,
    gci_n_steps: int = 20,
    gci_r: float = 1.3,
) -> VerificationReport:
    """Run every check and summarise the outcome."""
    checks = [
        check_residual(model, result, tol_residual),
        check_global_equilibrium(model, result, tol_equilibrium),
        check_path_continuity(result, jump_factor),
        check_step_refinement(model, result, refine, tol_refinement),
    ]
    if gci:
        checks.append(check_gci(model, result, n_steps=gci_n_steps, r=gci_r))
    return VerificationReport(checks=checks, verdict=_verdict(checks))


# ---------------------------------------------------------------------------
# Claim levels: what a result is *allowed* to be stated as
# ---------------------------------------------------------------------------


SMOKE = "smoke"
DEBUG = "debug"
ENGINEERING = "engineering"
SIGNOFF = "signoff"


def claim_level(report: VerificationReport, result: SolveResult) -> str:
    """Map a verification report to the strongest claim that is supported.

    Levels, strongest last:

    * ``smoke``      the run produced a readable result; nothing else is claimed
    * ``debug``      a critical gate failed; the result is diagnostic only and
      must not be reported as an engineering answer
    * ``engineering`` the four gates passed (residual, balance, continuity,
      reproducibility) but no usable GCI band is present, so the discrete
      error is not quantified
    * ``signoff``    engineering plus a usable GCI estimate on every QoI.
      This is the strongest claim verisolv supports; it is deliberately the
      one level that no automatic escalation path ever produces on its own.
    """
    if result.u is None:
        return SMOKE
    names = {c.name: c for c in report.checks}
    base_pass = all(
        c.passed
        for c in report.checks
        if c.name in ("residual", "global_equilibrium", "path_continuity", "step_refinement")
    )
    gci_check = names.get("gci")
    gci_pass = gci_check is not None and gci_check.passed
    gci_ran = gci_check is not None
    if report.verdict == "rejected":
        # A critical gate failed; the result is diagnostic only.
        return DEBUG
    if not base_pass:
        # A major gate failed; the result is diagnostic, not an engineering answer.
        return DEBUG
    if report.verdict == "verified" and gci_ran and gci_pass:
        return SIGNOFF
    # base_pass is True and (GCI not present, or GCI not passing):
    # the answer is self-consistent but the discretisation error is not
    # quantified; the strongest honest claim is engineering, not signoff.
    return ENGINEERING

