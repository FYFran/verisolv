"""Can check_scale_consistency be repaired without running a solve?

The current estimate is load / sum(E*A/L) over every bar. That sum is not a
structural stiffness: it is the sum of all member stiffnesses, which for the
17-bar cantilever is ~890x larger than the tip stiffness the load actually sees.
Hence the estimate is ~800x too small and the threshold is never reached.

check_model's value is that it never runs the solver, so the replacement has to be
solve-free too. This compares candidate cheap estimators against the real
first-order displacement, so the choice is made on measurement rather than taste.
"""
from pathlib import Path

import io
import sys

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verisolv.cases import _cantilever  # noqa: E402
from verisolv.fem import assemble  # noqa: E402
from verisolv.solver import SolverOptions, solve  # noqa: E402

print(f"{'load':>12} {'current':>12} {'max-diag':>12} {'min-diag':>12} {'ACTUAL':>12}")
print("-" * 66)

rows = []
for factor in (1.0, 10.0, 100.0, 1000.0):
    model = _cantilever(tip_load=-50_000.0 * factor)
    free = model.free_dofs()

    # current estimator: load / sum(E*A/L)
    stiffness_sum = 0.0
    for bar in model.bars:
        stiffness_sum += bar.modulus * bar.area / max(bar.length(model.coords), 1e-30)
    force = float(np.max(np.abs(model.load_vector())))
    current = force / max(stiffness_sum, 1e-30)

    # candidate: displacement predicted at the loaded DOF from that row's diagonal
    _, k_mat, _ = assemble(model, np.zeros(model.dof_count))
    k_ff = k_mat[np.ix_(free, free)]
    diagonal = np.diag(k_ff)
    f_free = model.load_vector()[free]
    with np.errstate(divide="ignore", invalid="ignore"):
        per_dof = np.abs(f_free) / np.where(diagonal > 0, diagonal, np.inf)
    max_diag = float(np.max(per_dof)) if per_dof.size else 0.0

    # candidate: solve the linear system (cheap, but it *is* an analysis)
    linear = float(np.max(np.abs(np.linalg.solve(k_ff, f_free))))

    result = solve(model, SolverOptions(control="load", n_steps=10, max_iter=60, adaptive=True))
    actual = float(np.max(np.abs(result.u))) if result.u is not None else float("nan")

    rows.append((factor, current, max_diag, linear, actual))
    print(f"{-50_000.0 * factor:>12,.0f} {current:>12.3e} {max_diag:>12.3e} "
          f"{linear:>12.3e} {actual:>12.3e}")

print()
print("ratio of estimate to ACTUAL (1.0 would be perfect):")
print(f"{'load':>12} {'current':>12} {'max-diag':>12} {'linear':>12}")
print("-" * 52)
for factor, current, max_diag, linear, actual in rows:
    print(f"{-50_000.0 * factor:>12,.0f} {current / actual:>12.4g} "
          f"{max_diag / actual:>12.4g} {linear / actual:>12.4g}")
