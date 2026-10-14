"""Independently verify the AGH agent's F6 claim.

Its report says check_scale_consistency fails to fire on a x1000 overload because
it estimates displacement from a linear stiffness scale that systematically
underestimates. If true, that is a real defect in the check, and the check is
blind in exactly the regime it was written for.

I did not write this by trusting the report. I am reproducing it from scratch.
"""

import io
import sys

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"<项目根>")

from verisolv.checkmodel import check_model  # noqa: E402
from verisolv.cases import _cantilever  # noqa: E402
from verisolv.solver import SolverOptions, solve  # noqa: E402
from verisolv.verify import verify  # noqa: E402

print("=" * 78)
print("Reproducing F6: does check_scale_consistency fire on a x1000 overload?")
print("=" * 78)

for factor, label in ((1.0, "nominal"), (10.0, "x10"), (100.0, "x100"), (1000.0, "x1000")):
    model = _cantilever(tip_load=-50_000.0 * factor)
    report = check_model(model)
    scale = next(f for f in report.findings if f.check == "scale_consistency")

    result = solve(model, SolverOptions(control="load", n_steps=10, max_iter=60, adaptive=True))
    displacement = (
        float(np.max(np.abs(result.u))) if result.u is not None else float("nan")
    )
    verdict = verify(model, result).verdict if result.converged else f"not converged ({result.failure})"

    print(f"\n{label}  (tip load {-50_000.0 * factor:,.0f} N)")
    print(f"  check_scale_consistency : {'PASSED' if scale.passed else 'FAILED'}"
          f"   estimated = {scale.evidence.get('estimated_displacement_m'):.6g} m"
          f"   span = {scale.evidence.get('characteristic_span_m'):.6g} m")
    print(f"  ACTUAL max displacement : {displacement:.6g} m")
    print(f"  verification verdict    : {verdict}")
    if displacement == displacement and scale.evidence.get("estimated_displacement_m"):
        estimated = scale.evidence["estimated_displacement_m"]
        if displacement > 0:
            print(f"  --> estimate is off by a factor of {displacement / estimated:,.1f}")

print()
print("=" * 78)
print("VERDICT ON THE AGENT'S CLAIM")
print("=" * 78)
