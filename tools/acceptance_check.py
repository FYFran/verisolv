"""Self-check for acceptance items #1, #2, #3: independently re-run the three
cases the team leader will hand-check, using ONLY the fixed code."""
import sys
sys.path.insert(0, r"<项目根>")
from verisolv.cases import _cantilever
from verisolv.checkmodel import check_model

# #1: x1000 load -> check_scale_consistency MUST FAILED
m1000 = _cantilever(tip_load=-50_000_000.0)
r1 = check_model(m1000)
scale1 = next(f for f in r1.findings if f.check == "scale_consistency")
print("#1 x1000 load:  scale_consistency passed =", scale1.passed,
      "| est =", scale1.evidence.get("linear_tip_displacement_m"), "m | expect passed=False")

# #2: nominal load -> scale_consistency MUST STILL PASSED
mn = _cantilever(tip_load=-50_000.0)
rn = check_model(mn)
scaln = next(f for f in rn.findings if f.check == "scale_consistency")
print("#2 nominal load: scale_consistency passed =", scaln.passed,
      "| est =", scaln.evidence.get("linear_tip_displacement_m"), "m | expect passed=True")

# #3: mechanism model -> check_model must return normally with ill_posed (no exception)
mm = _cantilever()
mm.fixed[0] = (False, True)
mm.fixed[5] = (False, True)
try:
    rm = check_model(mm)
    print("#3 mechanism: check_model returned normally, verdict =", rm.verdict,
          "| rigid_body_modes =", rm.rigid_body_modes, "| NO EXCEPTION | expect ill_posed")
except Exception as e:
    print("#3 mechanism: EXCEPTION raised ->", type(e).__name__, e, "| FAIL")
