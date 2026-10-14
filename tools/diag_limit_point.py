"""Diagnostic: what does load control actually do at the limit point?"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verisolv.models import von_mises_truss  # noqa: E402
from verisolv.solver import SolverOptions, solve  # noqa: E402

REF = 20_000.0
model = von_mises_truss(1.0, 0.1, 1.0e-4, REF)


def show(title: str, options: SolverOptions) -> None:
    r = solve(model, options)
    print(f"\n=== {title} ===")
    print(f"converged={r.converged} failure={r.failure} accepted={len(r.steps)} rejected={len(r.failures)}")
    print(f"{'step':>4} {'lambda':>10} {'P (N)':>12} {'apex drop v (m)':>16} {'iters':>6}")
    for s in r.steps:
        print(f"{s.step:>4} {s.control_end:>10.4f} {s.control_end * REF:>12.1f} {s.max_displacement:>16.6f} {s.iterations:>6}")
    for f in r.failures:
        print(f"  REJECT step={f.step} trial={f.control_trial:.4f} {f.failure} iters={f.iterations} res={f.residual_norm:.3e}")


show("load control, 10 steps, NO adaptive", SolverOptions(control="load", n_steps=10, adaptive=False))
show("load control, 10 steps, adaptive", SolverOptions(control="load", n_steps=10, adaptive=True))
show("load control, 1 step (lambda 0 -> 1)", SolverOptions(control="load", n_steps=1, adaptive=False, max_iter=30))

r = solve(model, SolverOptions(control="load", n_steps=40, adaptive=False))
loads = np.array([s.control_end * REF for s in r.steps])
drops = np.array([s.max_displacement for s in r.steps])
inc = np.diff(drops)
print(f"\n=== fine load control (40 steps, no adaptive) ===")
print(f"converged={r.converged} failure={r.failure}")
print("per-step displacement increments:")
print(np.array2string(inc, precision=6, max_line_width=200))
if inc.size:
    med = float(np.median(np.abs(inc)))
    print(f"median increment={med:.3e}  max increment={np.abs(inc).max():.3e}  ratio={np.abs(inc).max()/max(med,1e-15):.1f}x")
