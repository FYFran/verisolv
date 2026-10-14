import sys
sys.path.insert(0, r"<项目根>")
import numpy as np
from verisolv.cases import _cantilever
from verisolv.checkmodel import check_scale_consistency

print("=== 缺陷① 修复前后：各载荷级触发情况（阈值 0.1*span=0.4m，未改）===")
for mult in (1, 10, 100, 1000):
    m = _cantilever(tip_load=-50_000.0 * mult)
    f = check_scale_consistency(m)
    est = f.evidence.get("linear_tip_displacement_m")
    est_s = "n/a" if est is None else "{:.4e} m".format(est)
    d = "（PASS）" if f.passed else "（FAILED: " + f.detail + "）"
    print("x{:<5} load={:>12,.0f} N   est_disp={:<18}   {}".format(mult, -50_000 * mult, est_s, d))
