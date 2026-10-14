"""Independently verify the audit's two most serious findings.

Finding 1: an area magnitude error (A x1000) passes all four numerical gates AND
           the model checker, while giving a wrong answer -- and is undisclosed.
Finding 2: optimize.py's verdict=verified covers numerical self-consistency but
           not the design Constraints the optimiser was asked to satisfy.

Both are serious enough to change what the submission may claim, so neither is
accepted on the auditor's word alone.
"""

import io
import sys

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"<项目根>")

from verisolv.cases import _cantilever  # noqa: E402
from verisolv.checkmodel import check_model  # noqa: E402
from verisolv.solver import SolverOptions, solve  # noqa: E402
from verisolv.verify import verify  # noqa: E402

print("=" * 78)
print("FINDING 1: is an area magnitude error really invisible?")
print("=" * 78)

baseline_deflection = None
for factor in (1.0, 10.0, 100.0, 1000.0):
    model = _cantilever()
    for bar in model.bars:
        bar.area *= factor
    model.name = f"area_x{factor:g}"

    report = check_model(model)
    result = solve(model, SolverOptions(control="load", n_steps=10, max_iter=60, adaptive=True))
    verdict = verify(model, result).verdict if result.converged else f"not converged ({result.failure})"
    deflection = float(np.max(np.abs(result.u))) if result.u is not None else float("nan")
    if factor == 1.0:
        baseline_deflection = deflection

    print(f"\n  area x{factor:<6g}")
    print(f"    check_model verdict : {report.verdict}")
    print(f"    solver converged    : {result.converged}")
    print(f"    verification verdict: {verdict}")
    print(f"    max deflection      : {deflection:.6e} m"
          f"   ({deflection / baseline_deflection:.4g}x the correct answer)")

print()
print("  --> if check_model says 'ok' and verification says 'verified' for a")
print("      deflection that is orders of magnitude wrong, the finding is CONFIRMED")

print()
print("=" * 78)
print("FINDING 2: does optimize.py's verdict cover the design constraints?")
print("=" * 78)

import inspect  # noqa: E402

from verisolv import optimize  # noqa: E402

source = inspect.getsource(optimize)
verify_calls = [
    line.strip() for line in source.splitlines()
    if "verify(" in line and not line.strip().startswith("#")
]
print("  verify( call sites inside optimize.py:")
for line in verify_calls:
    print(f"    {line}")
print()
constraint_mentions = [
    line.strip() for line in source.splitlines()
    if ("constraints" in line.lower() or "max_stress" in line or "buckling_factor" in line)
    and "verify" in line.lower()
]
print("  lines mentioning both a constraint and 'verify':")
print(f"    {constraint_mentions if constraint_mentions else 'NONE'}")
print()
print("  --> if verify() is called without the Constraints being passed to it,")
print("      'verdict=verified' cannot mean 'satisfies the design constraints'")
