"""Reconstruct what the OLD check_scale_consistency reported for B02, without
touching the current code. Mirrors the pre-fix formula exactly:

    stiffness_scale = sum(E*A/L for all bars), floored at 1e-30
    load = max |load_vector|
    span = max bar length
    estimated = load / stiffness_scale
    FAIL when span > 0 and estimated > 0.1 * span
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from verisolv.cases import _cantilever


def old_scale_finding(m):
    stiffness_scale = 0.0
    for bar in m.bars:
        stiffness_scale += bar.modulus * bar.area / max(bar.length(m.coords), 1e-30)
    stiffness_scale = max(stiffness_scale, 1e-30)
    load = float(np.max(np.abs(m.load_vector()))) if m.load_vector().size else 0.0
    span = max((bar.length(m.coords) for bar in m.bars), default=0.0)
    estimated = load / stiffness_scale
    passed = not (span > 0.0 and estimated > 0.1 * span)
    return {"max_node_load_N": load, "span_m": span, "stiffness_scale_N_per_m": stiffness_scale,
            "estimated_displacement_m": estimated, "old_verdict": "PASSED" if passed else "FAILED"}


m = _cantilever(tip_load=-50_000_000.0)
print("OLD formula, B02 (tip load -50,000,000 N):")
for k, v in old_scale_finding(m).items():
    print(f"  {k}: {v}")
