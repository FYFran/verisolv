"""Blind-test fault F1 (support settlement).

Builds, via public constructors only, the F1 model described in
docs/AGH-BRIEF.md section 4.3:

    F1 支座沉降: 给某个支座节点一个强制位移
    出题人判断: 当前 Model 的约束只能锁死(位移=0)，无法表达强制非零位移。

The point is precisely to record *how far* the framework gets you:
it is documented that ``Model.fixed`` can only express "locked" or
"free", never a prescribed non-zero displacement.  This script tries
to express F1 honestly and records whatever the constructors actually
allow.  No project code under verisolv/ is modified; this is a test
driver in tools/ only.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, r"<项目根>")

import numpy as np

from verisolv.checkmodel import check_model
from verisolv.fem import ModelError
from verisolv.models import cantilever_truss


def build_f1() -> dict:
    """Attempt the F1 construction; return a record of what actually happened."""
    m = cantilever_truss()
    record: dict = {
        "fault": "F1_support_settlement",
        "intent": "prescribe a non-zero displacement to a support node",
        "steps": [],
        "construction_succeeded": False,
        "model_constructed": None,
        "attempted_representation": "",
        "notes": [],
    }

    # The only displacement language Model.fixed offers is boolean.
    record["notes"].append(
        "Model.fixed is dict[int, tuple[bool, bool]]: the only displacements a node "
        "can be given are zero (restrained) or unknown (free). There is no field "
        "to express 'node 0 is forced to move 0.02 m in x'."
    )

    # Attempt 1: the honest representation is not expressible.
    try:
        # Not valid Python for this dataclass, but it is what the intent asks for.
        _ = m.fixed  # show the shape of what exists
        record["notes"].append(
            "f'{m.fixed}' shows only (True, True) style entries; no value slot exists"
        )
    except Exception as exc:  # pragma: no cover - defensive
        record["notes"].append(f"inspection raised {type(exc).__name__}: {exc}")

    # Attempt 2: the only displacement the framework can *attach* to a support
    # node is a load.  That is not a prescribed displacement; it is recorded so
    # the diagnosis file can state exactly what the closest expressible
    # construction is, and show what the system reports for it.
    m2 = cantilever_truss()
    m2.name = "cantilever_truss_p4_f1"
    m2.loads[0, 0] = 20_000.0  # a load on the support DOF, not a displacement
    record["attempted_representation"] = "load of 20000 N on restrained DOF 0x; Model has no prescribed-displacement field"
    record["construction_succeeded"] = True
    record["model_constructed"] = "cantilever_truss_p4 + load on node 0 x-DOF"

    report = check_model(m2)
    record["checkmodel_verdict"] = report.verdict
    record["checkmodel_findings"] = [f.to_dict() for f in report.findings]
    return record


if __name__ == "__main__":
    print(json.dumps(build_f1(), indent=2, ensure_ascii=False))
