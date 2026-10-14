"""Compare OLD vs NEW check_scale_consistency across all 20 library cases,
to enumerate exactly which case model_check_verdict entries changed.

OLD = the pre-fix formula (sum E*A/L), mirrored here verbatim.
NEW = the fixed checkmodel.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from verisolv.cases import build_cases
from verisolv.checkmodel import check_model as _new_check_model


def old_scale_pass(m):
    stiffness_scale = 0.0
    for bar in m.bars:
        stiffness_scale += bar.modulus * bar.area / max(bar.length(m.coords), 1e-30)
    stiffness_scale = max(stiffness_scale, 1e-30)
    load = float(np.max(np.abs(m.load_vector()))) if m.load_vector().size else 0.0
    span = max((bar.length(m.coords) for bar in m.bars), default=0.0)
    estimated = load / stiffness_scale
    return not (span > 0.0 and estimated > 0.1 * span)


for case in build_cases():
    m, _o, _x = case.build()
    rep = _new_check_model(m)
    scale = next((f for f in rep.findings if f.check == "scale_consistency"), None)
    new_scale = scale.passed if scale is not None else None
    new_verdict = rep.verdict
    old_flag = old_scale_pass(m)
    changed = old_flag != new_scale
    mark = "  <- scale flipped" if changed else ""
    print(
        "{:<44} old_scale={} new_scale={} new_model_check={}{}".format(
            case.name[:42],
            "P" if old_flag else "F",
            "P" if new_scale else "F",
            new_verdict,
            mark,
        )
    )
