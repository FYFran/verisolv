"""Blind-test fault F2 (swapped bar node numbering i<->j).

F2 per docs/AGH-BRIEF.md 4.3:
    杆件 i/j 互换 —— 把某根杆的两端节点编号对调
    出题人判断: 静力等价,数值结果完全相同,纯数值检查检测不到。

This script constructs the swap exactly as described (two-node numbering
flipped on a single bar of the reference cantilever truss), runs the
public model checks and a solve, and records what is actually observed.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, r"<项目根>")

import numpy as np

from verisolv.checkmodel import check_model
from verisolv.fem import Model
from verisolv.models import cantilever_truss
from verisolv.solver import SolverOptions, solve


def build_f2() -> dict:
    record: dict = {"fault": "F2_bar_ij_swapped", "steps": [], "notes": []}

    base = cantilever_truss()
    swapped = cantilever_truss()
    swapped.name = "cantilever_truss_p4_f2"
    # Flip i<->j on bar index 0 only (bottom chord, node 0 -> node 1).
    b = swapped.bars[0]
    swapped.bars[0] = type(b)(i=b.j, j=b.i, area=b.area, modulus=b.modulus,
                              density=b.density, group=b.group,
                              yield_stress=b.yield_stress)
    record["steps"].append(
        "bars[0] (bottom chord, node 0->1) replaced with i/j swapped"
    )

    record["checkmodel_verdict_base"] = check_model(base).verdict
    rep = check_model(swapped)
    record["checkmodel_verdict_swapped"] = rep.verdict
    record["checkmodel_findings_swapped"] = [f.to_dict() for f in rep.findings]

    opts = SolverOptions(control="load", n_steps=10, max_iter=60, adaptive=True)
    res_base = solve(base, opts)
    res_swap = solve(swapped, opts)
    record["solve_base"] = {"message": res_base.message, "path": res_base.path}
    record["solve_swapped"] = {"message": res_swap.message, "path": res_swap.path}

    if res_base.converged and res_swap.converged:
        pb = np.asarray(res_base.path, dtype=float)
        ps = np.asarray(res_swap.path, dtype=float)
        record["path_max_abs_difference"] = float(np.max(np.abs(pb - ps)))
    return record


if __name__ == "__main__":
    print(json.dumps(build_f2(), indent=2, ensure_ascii=False))
