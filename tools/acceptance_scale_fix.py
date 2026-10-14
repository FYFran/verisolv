"""Independent acceptance test for the check_scale_consistency repair.

Written from scratch against the stated acceptance criteria, not by running the
agent's own script. If the fix only works when exercised its way, that is not a
fix.

Criteria:
  1. a x1000 overload MUST now fail the check      (it used to pass)
  2. a nominal load MUST still pass                (it must not become an alarm)
  3. a mechanism MUST NOT crash check_model        (singular solve must be caught)
"""

import io
import sys

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"<项目根>")

from verisolv.cases import _cantilever  # noqa: E402
from verisolv.checkmodel import check_model  # noqa: E402

failures: list[str] = []


def scale_finding(model):
    report = check_model(model)
    return report, next(f for f in report.findings if f.check == "scale_consistency")


print("=" * 76)
print("CRITERION 1 + 2: does the check now distinguish overload from nominal?")
print("=" * 76)
print(f"{'load':>14} {'scale check':>12} {'estimate':>13} {'actual(linear est)':>18}")
print("-" * 76)

for factor, expect_pass in ((1.0, True), (10.0, True), (100.0, False), (1000.0, False)):
    model = _cantilever(tip_load=-50_000.0 * factor)
    report, finding = scale_finding(model)
    verdict = "PASSED" if finding.passed else "FAILED"
    estimate = finding.evidence.get("estimated_displacement_m", float("nan"))
    method = finding.evidence.get("estimate_method", "?")
    print(f"{-50_000.0 * factor:>14,.0f} {verdict:>12} {estimate:>13.4e}  method={method}")

    if factor == 1000.0 and finding.passed:
        failures.append("CRITERION 1 FAILED: x1000 overload still passes")
    if factor == 1.0 and not finding.passed:
        failures.append("CRITERION 2 FAILED: nominal load now alarms")

print()
print("=" * 76)
print("CRITERION 3: does a mechanism crash check_model?")
print("=" * 76)

# A structure free to translate in x: the reference cantilever with the base
# x-restraints removed. Its free-free tangent is singular at zero load.
mechanism = _cantilever()
mechanism.fixed[0] = (False, True)
mechanism.fixed[5] = (False, True)
mechanism.name = "mechanism_probe"

try:
    report, finding = scale_finding(mechanism)
    print(f"  check_model returned          : {report.verdict}")
    print(f"  rigid_body_modes              : {report.rigid_body_modes}")
    print(f"  scale_consistency             : {'PASSED' if finding.passed else 'FAILED'}")
    print(f"  estimate_method               : {finding.evidence.get('estimate_method')}")
    print(f"  estimate_unavailable_because  : {finding.evidence.get('estimate_unavailable_because')}")
    if report.verdict != "ill_posed":
        failures.append(f"CRITERION 3 FAILED: mechanism verdict is {report.verdict}, expected ill_posed")
except Exception as exc:  # noqa: BLE001
    failures.append(f"CRITERION 3 FAILED: check_model raised {type(exc).__name__}: {exc}")
    print(f"  RAISED {type(exc).__name__}: {exc}")

print()
print("=" * 76)
if failures:
    print("ACCEPTANCE: FAIL")
    for line in failures:
        print(f"  - {line}")
else:
    print("ACCEPTANCE: all three criteria PASS")
print("=" * 76)
sys.exit(1 if failures else 0)
