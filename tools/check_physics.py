"""Validate the finite element core against the closed-form von Mises truss.

The shallow two-bar truss has a textbook analytical solution, so it is the
cheapest honest way to prove that the Green-Lagrange / PK2 implementation and
its tangent are correct rather than merely plausible.

Run from the project root:  python tools/check_physics.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verisolv.fem import E_STEEL  # noqa: E402
from verisolv.models import von_mises_truss  # noqa: E402
from verisolv.solver import SolverOptions, limit_point, solve  # noqa: E402

HALF_SPAN = 1.0
RISE = 0.1
AREA = 1.0e-4
REFERENCE_LOAD = 20_000.0
APEX_Y_DOF = 5  # node 2, y component


def exact_apex_force(downward: float) -> float:
    """Closed-form downward apex force for downward apex displacement."""
    l0 = float(np.hypot(HALF_SPAN, RISE))
    den = 2.0 * (HALF_SPAN**2 + RISE**2)
    strain = downward * (downward - 2.0 * RISE) / den
    return 2.0 * E_STEEL * AREA * l0 * strain * (downward - RISE) / (HALF_SPAN**2 + RISE**2)


def main() -> int:
    model = von_mises_truss(HALF_SPAN, RISE, AREA, REFERENCE_LOAD, E_STEEL)
    print(f"model            : {model.name}")
    print(f"nodes/DOF/free   : {model.node_count} / {model.dof_count} / {model.free_dofs().tolist()}")
    print(f"reference load   : {REFERENCE_LOAD:,.0f} N downward")
    print()

    ok = True

    # --- 1. displacement control vs closed form ---------------------------
    print("1) displacement control vs closed form")
    print(f"{'apex drop v (m)':>16} {'FEM P (N)':>14} {'exact P (N)':>14} {'rel.err':>10}")
    for downward in (0.005, 0.02, 0.0423, 0.08, 0.12, 0.15):
        result = solve(
            model,
            SolverOptions(
                control="displacement",
                control_dof=APEX_Y_DOF,
                target_displacement=-downward,
                n_steps=40,
                tol=1e-10,
                max_iter=40,
            ),
        )
        if not result.converged:
            print(f"{downward:>16.4f}  NOT CONVERGED ({result.failure})")
            ok = False
            continue
        fem_force = result.load_factor * REFERENCE_LOAD
        exact = exact_apex_force(downward)
        rel = abs(fem_force - exact) / max(abs(exact), 1e-9)
        flag = "" if rel < 1e-6 else "  <-- MISMATCH"
        if rel >= 1e-6:
            ok = False
        print(f"{downward:>16.4f} {fem_force:>14.1f} {exact:>14.1f} {rel:>10.2e}{flag}")

    # --- 2. locate the limit point ---------------------------------------
    print()
    print("2) limit point (max downward force on the stable branch)")
    steps = 400
    result = solve(
        model,
        SolverOptions(
            control="displacement",
            control_dof=APEX_Y_DOF,
            target_displacement=-0.15,
            n_steps=steps,
            tol=1e-10,
        ),
    )
    loads = np.array([s.load_factor * REFERENCE_LOAD for s in result.steps])
    ctrl = np.array([s.control_end for s in result.steps])
    peak = int(np.argmax(loads))
    print(f"numerical peak   : {loads[peak]:,.1f} N at v = {-ctrl[peak]:.5f} m")

    grid = np.linspace(0.0, 0.09, 200_001)
    exact_grid = np.array([exact_apex_force(v) for v in grid])
    k = int(np.argmax(exact_grid))
    print(f"closed-form peak : {exact_grid[k]:,.1f} N at v = {grid[k]:.5f} m")
    rel = abs(loads[peak] - exact_grid[k]) / exact_grid[k]
    print(f"peak rel. error  : {rel:.2e}")
    if rel >= 1e-4:
        ok = False

    # --- 3. load control must fail at the limit point ---------------------
    print()
    print("3) load control to the full reference load (must FAIL)")
    failure = solve(
        model,
        SolverOptions(control="load", n_steps=10, tol=1e-8, max_iter=30, adaptive=False),
    )
    reached = failure.load_factor * REFERENCE_LOAD
    print(f"converged        : {failure.converged}")
    print(f"failure kind     : {failure.failure}")
    print(f"accepted steps   : {len(failure.steps)}")
    print(f"reached load     : {reached:,.1f} N  (limit is {exact_grid[k]:,.1f} N)")
    print(f"message          : {failure.message}")
    if failure.converged:
        print("  <-- UNEXPECTED: load control passed the limit point")
        ok = False
    if failure.failure != "max_iterations":
        print(f"  <-- expected 'max_iterations', got {failure.failure!r}")
        ok = False
    if not (0.60 * exact_grid[k] <= reached < exact_grid[k]):
        print("  <-- reached load is not a sensible fraction of the limit load")
        ok = False
    stalled = failure.failures[-1].residual_norm if failure.failures else float("nan")
    print(f"stalled residual : {stalled:.4e} N after {failure.failures[-1].iterations if failure.failures else 0} iterations")

    # --- 4. adaptive load control silently jumps branches -----------------
    print()
    print("4) adaptive load control: converges, but jumps equilibrium branches")
    jumped = solve(
        model,
        SolverOptions(control="load", n_steps=10, tol=1e-8, max_iter=30, adaptive=True),
    )
    inc = np.abs(np.diff([s.max_displacement for s in jumped.steps]))
    biggest = float(inc.max()) if inc.size else 0.0
    median = float(np.median(inc)) if inc.size else 0.0
    print(f"converged        : {jumped.converged}")
    print(f"final lambda     : {jumped.load_factor:.4f}  ({jumped.load_factor * REFERENCE_LOAD:,.1f} N)")
    print(f"largest step jump: {biggest:.5f} m  (median {median:.3e} m, ratio {biggest / max(median, 1e-15):,.0f}x)")
    print("  -> the solver reports success while the path is discontinuous;")
    print("     this is exactly what the verification layer must catch.")
    if not jumped.converged or biggest < 0.1:
        print("  <-- UNEXPECTED: expected a large branch jump")
        ok = False

    # --- 5. displacement control traces the true path ---------------------
    print()
    print("5) displacement control traces the full path (the repair)")
    path = solve(
        model,
        SolverOptions(
            control="displacement",
            control_dof=APEX_Y_DOF,
            target_displacement=-0.15,
            n_steps=60,
            tol=1e-10,
        ),
    )
    factors = [s.load_factor for s in path.steps]
    print(f"converged        : {path.converged}")
    print(f"final lambda     : {path.load_factor:.4f}  ({path.load_factor * REFERENCE_LOAD:,.1f} N)")
    print(f"lambda sign flips: {sum(1 for a, b in zip(factors, factors[1:]) if (a > 0) != (b > 0))}")
    print(f"max displacement : {path.steps[-1].max_displacement:.5f} m")
    if not path.converged:
        print("  <-- UNEXPECTED: displacement control should complete")
        ok = False
    if path.load_factor >= 0:
        print("  <-- UNEXPECTED: the unstable branch should carry a negative load factor")
        ok = False
    if path.steps[-1].max_displacement <= 0.15 * 0.99:
        print("  <-- UNEXPECTED: did not reach the requested displacement")
        ok = False

    print()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
