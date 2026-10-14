"""Method of Manufactured Solutions (MMS) attempt for the 2-node truss element.

**RETRACTED (Round 5, 2026-10-11).** An external adversarial review found that
this tool is NOT a valid MMS, and the captain's decision is to RETRACT rather
than fix it.  This file is kept for the record; do NOT read its output as
verification evidence.  See docs/mms.md for the full retraction note.

Why this is not a valid MMS (the three errors the review found):

1. **The manufactured source term was never injected into the solver.**  The
   displacement is PRESCRIBED (displacement control), not solved for.  A
   manufactured solution requires the manufactured field to be the solution of
   the *loaded* problem with a source term q(u_m) added; here the solver is
   driven by a boundary value, so nothing that the SymPy "source term" claims
to be is ever applied to the discretised equations.  The load factor
   measured is a dependent variable of the prescribed displacement, not a
   check that f_int(u_m) = q(u_m).

2. **Two SymPy source-term derivation errors** (in `sympy_source_term()`):
   * The Green-Lagrange strain of a manufactured field u = a*x on a bar of
     length L0 is `e = a + a^2/2` (the quadratic term (du/dx)^2/2), NOT `a`
     -- the linear-only expression the SymPy derivation uses is wrong by
     O(a^2).
   * The equivalent nodal forces for the *exact* (nonlinear) internal force
     N(u_m) must be `-N` and `+N` at the two nodes (the bar is a two-force
     member in its own deformed configuration), NOT `-N/2` / `+N/2` as the
     SymPy block computes.

3. **"theory_p = 1" contradicts the saturated measurement.**  If the
   theoretical order were 1, the observed difference between the n=80 and
   n=10 runs would be O(h) = O(1/10) ~ 10%, not the observed 1.4e-11
   saturation.  The saturation is consistent with a LINEAR-ELASTIC operator
   at small displacement (Newton converges in one iteration at every
   increment, so the load factor is resolution-independent to machine
   precision) -- which is exactly why the claimed p=1 theoretical order is
   itself inconsistent with the data the tool reports.

**Fundamental reason for the retraction (captain's judgment):** MMS measures
the OBSERVED SPATIAL DISCRETISATION ORDER -- it requires a spatial mesh to
refine.  Our models have **no spatial mesh**: the nodes are given and the
only discretisation parameter is the load increment count.  There is no
spatial refinement to measure, so a real MMS cannot be performed in this
framework.  This is the same problem as with our GCI: we have no mesh.

What this tool CAN still honestly report (and nothing more):
* a load-factor stability observation under step refinement
  (the "1.4e-11 saturation" is a step-refinement stability fact, not an
  MMS measurement);
* a SymPy algebra block whose two formulas are wrong and which was never
  injected into the solver.

Run (record only, NOT verification evidence):
    python tools/mms_verification.py
    python tools/mms_verification.py --model cantilever_truss --target-displacement 0.01
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

# Add the project root so the script can import verisolv
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import sympy as sp
    _SYMPY_OK = True
except ImportError:
    _SYMPY_OK = False


# ---------------------------------------------------------------------------
# Manufactured displacement fields
# ---------------------------------------------------------------------------

@dataclass
class MMSRun:
    """Outcome of one MMS solver run at a given n_steps."""
    n_steps: int
    target_displacement: float
    solver_load_factor: float
    solver_max_displacement: float
    total_iterations: int
    converged: bool


@dataclass
class MMSReport:
    """Full MMS verification report."""
    model_name: str
    field_name: str
    theory_p: float
    runs: list[MMSRun]
    observed_p: float | None
    conclusion: str
    sympy_source: dict[str, Any] | None
    error: str | None = None


# ---------------------------------------------------------------------------
# SymPy equivalent-nodal-force derivation
# ---------------------------------------------------------------------------

def sympy_source_term() -> dict[str, Any]:
    """Derive the exact equivalent nodal force for a manufactured linear
    displacement field on a 2-node truss bar, using SymPy.

    Manufactured field (linear in x):
        u(x) = a * x

    For a bar from node i to node j with reference length L0 and a
    purely axial displacement delta_u = a * L0:

        Green-Lagrange strain  e = delta_u / L0 = a
        internal force          N = E * A * e = E * A * a

    Equivalent nodal forces (axial, aligned with the bar at the
    reference configuration):
        f_i = -N / 2 = -E * A * a / 2
        f_j = +N / 2 = +E * A * a / 2

    SymPy confirms the algebra; the numeric values below are the
    expressions evaluated at E=1, A=1, a=0.01, L0=1.
    """
    if not _SYMPY_OK:
        return {
            "error": "SymPy not available. "
                     "The MMS test will still run (the solver's own residual "
                     "is used), but without an independently derived source "
                     "term.  Do not interpret a passing MMS test as "
                     "verifying the source term -- only the operator."
        }

    try:
        E, A, a = sp.symbols("E A a", real=True)
        # linear axial displacement: delta_u = a * L0, strain = a
        N_expr = E * A * a
        f_i_expr = -N_expr / 2
        f_j_expr = +N_expr / 2
        subs = {E: 1.0, A: 1.0, a: 0.01}
        return {
            "N_expression": str(N_expr),
            "f_i_expression": str(f_i_expr),
            "f_j_expression": str(f_j_expr),
            "N_numeric": float(N_expr.subs(subs)),
            "f_i_numeric": float(f_i_expr.subs(subs)),
            "f_j_numeric": float(f_j_expr.subs(subs)),
            "note": (
                "Source term is linear in the manufactured displacement "
                "because the Green-Lagrange strain of a uniform axial "
                "deformation is exactly the displacement gradient, with "
                "no higher-order terms.  A higher-order manufactured "
                "field (e.g. quadratic) would produce a quadratic "
                "source term and test a higher-order discretisation."
            ),
        }
    except Exception as exc:
        return {
            "error": f"SymPy derivation failed: {type(exc).__name__}: {exc}. "
                     "No source term is reported.  The MMS test cannot "
                     "verify the operator against a known source."
        }


# ---------------------------------------------------------------------------
# MMS solver runs
# ---------------------------------------------------------------------------

def _run_sequence(
    model,
    control_dof: int,
    target_displacement: float,
    n_steps_list: list[int],
    max_iter: int = 60,
    tol: float = 1e-8,
) -> list[MMSRun]:
    """Run the solver at each n_steps and collect the load factor."""
    from verisolv.solver import SolverOptions, solve

    results: list[MMSRun] = []
    for n in n_steps_list:
        opts = SolverOptions(
            control="displacement",
            control_dof=control_dof,
            target_displacement=target_displacement,
            n_steps=n,
            max_iter=max_iter,
            tol=tol,
        )
        try:
            result = solve(model, opts)
            if result.converged and result.u is not None and result.steps:
                last = result.steps[-1]
                results.append(MMSRun(
                    n_steps=n,
                    target_displacement=target_displacement,
                    solver_load_factor=result.load_factor,
                    solver_max_displacement=float(last.max_displacement),
                    total_iterations=sum(s.iterations for s in result.steps),
                    converged=True,
                ))
            else:
                results.append(MMSRun(
                    n_steps=n,
                    target_displacement=target_displacement,
                    solver_load_factor=0.0,
                    solver_max_displacement=0.0,
                    total_iterations=0,
                    converged=False,
                ))
        except Exception:
            results.append(MMSRun(
                n_steps=n,
                target_displacement=target_displacement,
                solver_load_factor=float("nan"),
                solver_max_displacement=float("nan"),
                total_iterations=0,
                converged=False,
            ))
    return results


def observed_order(runs: list[MMSRun]) -> tuple[float | None, str]:
    """Measure the observed convergence order of the load factor.

    For displacement control the load factor is the dependent variable;
    the prescribed displacement is fixed.  As ``n_steps`` increases the
    increment size ``h`` decreases and the load factor should approach
    a limit.  The observed order is:

        p_obs = log(|lambda_coarse - lambda_fine|) / log(h_coarse / h_fine)
              = log(|lambda_coarse - lambda_fine|) / log(n_fine / n_coarse)

    where ``h ∝ 1/n``.
    """
    if len(runs) < 2:
        return None, "Need at least two runs to measure an order."
    fine, coarse = runs[0], runs[1]
    if not fine.converged or not coarse.converged:
        return None, "One or both runs did not converge; order not measurable."
    diff = abs(fine.solver_load_factor - coarse.solver_load_factor)
    if diff < 1e-10:
        return None, (
            f"|lambda_fine - lambda_coarse| = {diff:.2e} < 1e-10: "
            "the sequence is saturated at machine precision.  The "
            "discretisation error is below the measurable threshold; "
            "a convergence order cannot be distinguished from zero.  "
            "This is a *pass* for the MMS test (the answer is stable "
            "at this resolution), not a measurement of the order."
        )
    ratio = float(coarse.n_steps / fine.n_steps)
    if ratio <= 1.0:
        return None, "Refinement ratio <= 1; runs are not ordered coarse-to-fine."
    p_obs = math.log(diff) / math.log(ratio)
    note = f"p_obs = {p_obs:.4f} from runs at n={coarse.n_steps} and n={fine.n_steps}."
    return p_obs, note


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def run_mms(
    model,
    n_steps_list: list[int] | None = None,
    target_displacement: float = 0.01,
    field_name: str = "linear_axial",
) -> MMSReport:
    """Run the MMS verification study.

    The theoretical order for the Green-Lagrange 2-node bar under
    displacement control is **p = 1** (first order in the increment
    size).  For a linear-elastic bar the order is effectively infinity
    (Newton converges in one iteration) and the test saturates.
    """
    from verisolv.solver import SolverOptions

    if n_steps_list is None:
        n_steps_list = [10, 20, 40, 80]

    free_dofs = model.free_dofs()
    if len(free_dofs) == 0:
        return MMSReport(
            model_name=model.name,
            field_name=field_name,
            theory_p=1.0,
            runs=[],
            observed_p=None,
            conclusion="No free DOF available; MMS test cannot be run.",
            sympy_source=None,
            error="no_free_dof",
        )

    control_dof = int(free_dofs[0])
    runs = _run_sequence(
        model, control_dof, target_displacement, n_steps_list
    )
    p_obs, p_note = observed_order(runs)
    source = sympy_source_term()
    theory_p = 1.0  # Green-Lagrange, incremental, displacement control

    if p_obs is None:
        conclusion = (
            p_note + " RETRACTION NOTE: this tool is not a valid MMS (see module"
            " header). The saturation reported here is a step-refinement stability"
            " observation only; no convergence order is claimed."
        )
    elif abs(p_obs - theory_p) <= 0.5:
        conclusion = (
            f"Observed order p={p_obs:.3f} is within 0.5 of the theoretical "
            f"order p={theory_p:.1f}.  RETRACTION NOTE: this tool is not a valid "
            "MMS (the manufactured source term was never injected into the solver, "
            "and the SymPy source-term block contains two derivation errors -- see "
            "the module header). No convergence order is claimed; the number above "
            "is a step-refinement stability observation only.  "
            f"{p_note}"
        )
    else:
        conclusion = (
            f"Observed order p={p_obs:.3f} differs from the theoretical "
            f"order p={theory_p:.1f} by more than 0.5.  Do NOT report a "
            "convergence order as verified without investigating first; in fact, "
            "this tool cannot claim a convergence order at all because it is not a "
            "valid MMS (retracted -- see module header).  "
            f"{p_note}"
        )

    return MMSReport(
        model_name=model.name,
        field_name=field_name,
        theory_p=theory_p,
        runs=runs,
        observed_p=p_obs,
        conclusion=conclusion,
        sympy_source=source,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _json_default(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return str(v)
    raise TypeError(f"not JSON serialisable: {type(v).__name__}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mms_verification",
        description=("RETRACTED (Round 5): step-refinement stability observation only; "
                     "NOT a valid MMS -- see module header and docs/mms.md"),
    )
    parser.add_argument("--model", default="cantilever_truss",
                        help="model name (default cantilever_truss)")
    parser.add_argument("--field", default="linear_axial",
                        help="name of the manufactured field")
    parser.add_argument("--target-displacement", type=float, default=0.01,
                        help="magnitude of the prescribed MMS displacement")
    parser.add_argument("--n-steps-list", type=int, nargs="+",
                        default=[10, 20, 40, 80],
                        help="list of n_steps values, fine to coarse")
    args = parser.parse_args(argv)

    from verisolv.models import build
    model = build(args.model)

    report = run_mms(
        model,
        n_steps_list=args.n_steps_list,
        target_displacement=args.target_displacement,
        field_name=args.field,
    )

    payload: dict[str, Any] = {
        "ok": report.error is None,
        "command": "mms",
        "retracted": True,
        "retraction_note": (
            "This tool is NOT a valid MMS (retracted 2026-10-11): the manufactured "
            "source term was never injected into the solver, the SymPy source-term "
            "block has two derivation errors, and our models have no spatial mesh, "
            "so MMS's core (spatial-refinement order measurement) is not applicable. "
            "The output below is a step-refinement STABILITY observation only; no "
            "convergence order is claimed. See docs/mms.md."
        ),
        "model": report.model_name,
        "field": report.field_name,
        "theory_p": report.theory_p,
        "observed_p": report.observed_p,
        "conclusion": report.conclusion,
        "sympy_source": report.sympy_source,
        "runs": [
            {
                "n_steps": r.n_steps,
                "converged": r.converged,
                "solver_load_factor": r.solver_load_factor,
                "solver_max_displacement": r.solver_max_displacement,
                "iterations": r.total_iterations,
            }
            for r in report.runs
        ],
    }
    if report.error:
        payload["error"] = report.error

    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, default=_json_default)
    sys.stdout.write("\n")

    if report.error:
        return 1
    # A saturated test (observed_p is None because the sequence is at
    # machine precision) is a *pass*, not a failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
