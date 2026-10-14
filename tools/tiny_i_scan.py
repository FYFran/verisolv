"""Round-5 independent scan: how does the cross-validation floor scale with TINY_I?

The external reviewer claims the PyNite-side emulation error scales LINEARLY
with I (not as I^2 as an earlier comment in cross_validate.py says).  This
script re-runs the 5000 N comparison at five values of TINY_I and prints the
relative tip-deflection difference, so the scaling can be read off directly.

Independent of verisolv.gci; only uses the same public verisolv model/solver
API and PyNite, exactly like tools/cross_validate.py.
"""
from pathlib import Path
import io
import sys

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verisolv.fem import E_STEEL, RHO_STEEL  # noqa: E402
from verisolv.models import cantilever_truss  # noqa: E402
from verisolv.solver import SolverOptions, solve  # noqa: E402

PANELS, SPAN, HEIGHT, NU, LOAD = 4, 4.0, 1.0, 0.3, 5000.0
areas = cantilever_truss(panels=PANELS, span=SPAN, height=HEIGHT).design_vector()

print(f"{'TINY_I':>10} {'verisolv tip (mm)':>18} {'PyNite tip (mm)':>16} {'rel diff':>12} {'shrink factor':>14}")
prev = None
for I in (1e-8, 1e-10, 1e-12, 1e-14, 1e-16):
    from Pynite import FEModel3D

    m = FEModel3D()
    m.add_material("steel", E_STEEL, E_STEEL / (2 * (1 + NU)), NU, RHO_STEEL)
    for group, area in areas.items():
        m.add_section(f"sec_{group}", area, I, I, I)

    def bottom(k: int) -> str:
        return f"B{k}"

    def top(k: int) -> str:
        return f"T{k}"

    for k in range(PANELS + 1):
        m.add_node(bottom(k), k * SPAN / PANELS, 0.0, 0.0)
        m.add_node(top(k), k * SPAN / PANELS, HEIGHT, 0.0)

    bars = []
    for k in range(PANELS):
        bars.append((bottom(k), bottom(k + 1), "bottom"))
        bars.append((top(k), top(k + 1), "top"))
    for k in range(PANELS + 1):
        bars.append((bottom(k), top(k), "vertical"))
    for k in range(PANELS):
        bars.append((bottom(k), top(k + 1), "diagonal"))
    for n, (i, j, g) in enumerate(bars):
        m.add_member(f"M{n}", i, j, "steel", f"sec_{g}")

    for node in (bottom(0), top(0)):
        m.def_support(node, True, True, True, True, True, True)
    for k in range(1, PANELS + 1):
        m.def_support(bottom(k), False, False, True, True, True, True)
        m.def_support(top(k), False, False, True, True, True, True)

    m.add_node_load(bottom(PANELS), "FY", -LOAD)
    m.analyze(check_stability=False)
    ref_tip = float(next(iter(m.nodes[bottom(PANELS)].DY.values())))

    model = cantilever_truss(panels=PANELS, span=SPAN, height=HEIGHT, tip_load=-LOAD, areas=areas)
    r = solve(model, SolverOptions(control="load", n_steps=10, max_iter=80, tol=1e-8, adaptive=True))
    ours_tip = float(r.u[2 * PANELS + 1])
    d = abs(ours_tip - ref_tip) / max(abs(ref_tip), 1e-30)
    shrink = "n/a" if prev is None or prev == 0 else f"{prev / d:8.1f}x"
    print(f"{I:>10.0e} {ours_tip * 1e3:>18.6f} {ref_tip * 1e3:>16.6f} {d:>12.3e} {shrink:>14}")
    prev = d

print()
print("Read off the scaling: successive I values differ by 100x.  A linear-in-I")
print("emulation error would shrink ~100x per step; a quadratic (I^2) error")
print("would shrink ~10000x per step.  Observed here: 3.292e-3 -> 3.768e-5 (~87x),")
print("then 3.768e-5 -> 7.098e-5 (GROWS: PyNite numerical-noise floor takes over),")
print("then flat at ~7.1e-5.  So the approach to the floor is roughly LINEAR in I")
print("over 1e-8..1e-10, NOT quadratic (I^2).  The I^2 wording in an earlier")
print("comment of cross_validate.py is not supported by this scan and has been")
print("corrected there.")
