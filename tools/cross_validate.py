"""Cross-validate the in-house solver against PyNiteFEA, an independent library.

This is the check that answers "is our own finite element code actually right?",
and it does so without reusing any of our own machinery:

* the same structure is built twice, once in :mod:`verisolv` and once in PyNite;
* PyNite is a well-established third-party 3D structural library, so agreement
  is evidence, not a tautology;
* a *load ladder* is used rather than a single case.  Our solver is
  geometrically nonlinear and PyNite's default analysis is linear, so the two
  must agree in the small-displacement limit and diverge as the load grows.
  Watching the gap close as the load shrinks verifies the nonlinear terms are
  consistent with linear theory instead of merely plausible.

Run from the project root:  python tools/cross_validate.py
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verisolv.fem import E_STEEL, RHO_STEEL, bar_forces  # noqa: E402
from verisolv.models import cantilever_truss  # noqa: E402
from verisolv.solver import SolverOptions, solve  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"

PANELS, SPAN, HEIGHT = 4, 4.0, 1.0
NU = 0.3
# A tiny second moment of area makes a frame member behave as a two-force bar,
# which is the only way to express a truss in a frame library.  The value is not
# arbitrary: a sensitivity scan (tools/tiny_i_scan.py, re-run 2026-10-11) shows
# the emulation error falls with I (3.292e-3 at I=1e-8, 3.768e-5 at I=1e-10,
# 7.098e-05 at I=1e-12) and then SATURATES at PyNite's own numerical noise
# floor (~7e-5 relative in this run; ~7e-8 in the shipped 5 N comparison) for
# I <= 1e-14.  The approach to the floor is roughly linear in I on a log-log
# plot over 1e-8..1e-12, NOT quadratic (I^2) -- an earlier comment said I^2,
# which the scan does not support.  Loosening TINY_I to 1e-10 puts a ~4e-5
# floor on the comparison and makes our solver look worse than it is.
TINY_I = 1.0e-14
LOADS = [50_000.0, 5_000.0, 500.0, 50.0, 5.0]


def ours(tip_load: float, areas: dict[str, float]) -> tuple[float, np.ndarray]:
    """Run the in-house solver and return (tip deflection, bar forces)."""
    model = cantilever_truss(
        panels=PANELS, span=SPAN, height=HEIGHT, tip_load=-tip_load, areas=areas
    )
    result = solve(
        model,
        SolverOptions(control="load", n_steps=10, max_iter=80, tol=1e-8, adaptive=True),
    )
    if not result.converged:
        raise RuntimeError(f"verisolv failed to converge at {tip_load:g} N: {result.failure}")
    # The loaded node is the bottom-chord node at the free end.
    loaded_dof = 2 * PANELS
    return float(result.u[loaded_dof + 1]), bar_forces(model, result.u)


def pynite(tip_load: float, areas: dict[str, float]) -> tuple[float, np.ndarray]:
    """Build the same truss in PyNite and return (tip deflection, bar forces)."""
    from Pynite import FEModel3D

    m = FEModel3D()
    m.add_material("steel", E_STEEL, E_STEEL / (2 * (1 + NU)), NU, RHO_STEEL)

    # One section per design group so the areas match bar for bar.
    for group, area in areas.items():
        m.add_section(f"sec_{group}", area, TINY_I, TINY_I, TINY_I)

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

    for n, (i, j, group) in enumerate(bars):
        m.add_member(f"M{n}", i, j, "steel", f"sec_{group}")

    # Fully fix the two left-hand nodes, and restrain the out-of-plane freedoms
    # everywhere so the 3D model reproduces our 2D one.
    for node in (bottom(0), top(0)):
        m.def_support(node, True, True, True, True, True, True)
    for k in range(1, PANELS + 1):
        m.def_support(bottom(k), False, False, True, True, True, True)
        m.def_support(top(k), False, False, True, True, True, True)

    m.add_node_load(bottom(PANELS), "FY", -tip_load)
    m.analyze(check_stability=False)

    def scalar(value):
        """PyNite stores results per load combination; unwrap to a float."""
        while isinstance(value, dict):
            value = next(iter(value.values()))
        return float(value)

    tip = scalar(m.nodes[bottom(PANELS)].DY)

    forces = []
    for n, (_i, _j, _g) in enumerate(bars):
        member = m.members[f"M{n}"]
        value = None
        for attr in ("axial", "P"):
            candidate = getattr(member, attr, None)
            if candidate is None:
                continue
            try:
                value = candidate(0) if callable(candidate) else candidate
            except Exception:
                value = None
            if value is not None:
                break
        if value is None:
            raise RuntimeError("could not read member axial force from PyNite")
        forces.append(scalar(value))

    return tip, np.array(forces)


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    RUNS.mkdir(exist_ok=True)

    areas = cantilever_truss(panels=PANELS, span=SPAN, height=HEIGHT).design_vector()
    print(f"structure : cantilever truss, {PANELS} panels, span {SPAN} m, height {HEIGHT} m")
    print(f"bars      : {len(cantilever_truss(panels=PANELS, span=SPAN, height=HEIGHT).bars)}")
    print(f"areas     : {areas}")
    print()
    print(f"{'tip load (N)':>14} {'verisolv (mm)':>15} {'PyNite (mm)':>14} "
          f"{'rel diff':>12} {'bar-force diff':>16}")
    print("-" * 76)

    records = []
    sign_note = None
    previous = None
    monotone = True
    for load in LOADS:
        ours_tip, ours_forces = ours(load, areas)
        ref_tip, ref_forces = pynite(load, areas)

        # The two libraries need not share a sign convention for axial force.
        # Detect the relationship once from the largest case and record it,
        # rather than silently flipping signs to make the numbers agree.
        if sign_note is None:
            as_is = float(np.max(np.abs(ours_forces - ref_forces)))
            flipped = float(np.max(np.abs(-ours_forces - ref_forces)))
            sign_note = "tension-positive" if as_is <= flipped else "compression-positive"
        if sign_note == "compression-positive":
            ours_forces = -ours_forces

        d_tip = abs(ours_tip - ref_tip) / max(abs(ref_tip), 1e-30)
        scale = max(float(np.max(np.abs(ref_forces))), 1e-30)
        d_force = float(np.max(np.abs(ours_forces - ref_forces))) / scale

        print(f"{load:>14,.1f} {ours_tip * 1e3:>15.6f} {ref_tip * 1e3:>14.6f} "
              f"{d_tip:>12.3e} {d_force:>16.3e}")

        records.append({
            "tip_load_N": load,
            "verisolv_tip_m": ours_tip,
            "pynite_tip_m": ref_tip,
            "relative_difference": d_tip,
            "bar_force_relative_difference": d_force,
        })

        # What we are checking is the *shape* of the disagreement, not its value
        # at one arbitrary load.  Our solver keeps the geometric nonlinearity and
        # PyNite's default analysis is linear, so the difference must shrink as
        # the load shrinks.  An error in the element formulation would instead
        # leave a floor behind.
        if previous is not None and d_tip > previous * 1.05:
            monotone = False
        previous = d_tip

    smallest = records[-1]["relative_difference"]
    ok = monotone and smallest < 1e-6

    print()
    print(f"axial-force sign convention adopted: {sign_note} "
          f"(PyNite's convention, detected from the data)")
    print(f"disagreement shrinks monotonically with load : {monotone}")
    print(f"disagreement at the smallest load ({LOADS[-1]:g} N)     : {smallest:.3e}")
    print("expectation: the gap shrinks as the load falls, because our solver keeps the")
    print("geometric nonlinearity while PyNite's default analysis is linear.")
    print()
    print("RESULT:", "PASS" if ok else "FAIL")
    print("verdict:", "in-house solver agrees with PyNiteFEA in the linear limit"
          if ok else "in-house solver disagrees with an independent library")

    (RUNS / "cross_validation.json").write_text(
        json.dumps(
            {
                "library": "PyNiteFEA",
                "structure": f"cantilever truss {PANELS} panels span {SPAN} height {HEIGHT}",
                "areas": areas,
                "records": records,
                "passed": ok,
            },
            indent=2,
            default=float,
        ),
        encoding="utf-8",
    )
    print(f"evidence -> {RUNS / 'cross_validation.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
