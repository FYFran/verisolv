"""Is the GCI observed-order formula sign-inverted, as the external reviewer claims?

The claim: gci.py's order formula is inverted relative to its own stated
"f1 = coarsest, f3 = finest" convention, and check_gci.py feeds its synthetic
samples in the opposite order, so the two errors cancel and the self-test is
circular.

The decisive test is not "does it recover p for the sequence it was tuned on" --
that is exactly the circularity being alleged. The decisive test is a sequence
whose convergence direction is KNOWN BY CONSTRUCTION, fed in the documented order.

A Richardson-converging sequence with order p has
    f_n = f_exact + C * h_n^p
with h halving each step. The increments then SHRINK geometrically, and
    |f3 - f2| / |f2 - f1| = 2^-p  < 1   for p > 0.
So the correct observed order from coarse->fine samples is
    p = -ln(|f3-f2| / |f2-f1|) / ln(r)
and any implementation that returns +p from the un-inverted ratio is wrong.
"""

import io
import sys

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"<项目根>")

from verisolv.gci import compute_gci  # noqa: E402


def richardson_sequence(p_true, f_exact=100.0, c=5.0, r=2.0, n=3):
    """f = f_exact + C*h^p, with h = 1, 1/r, 1/r^2 ... returned coarsest FIRST."""
    hs = [1.0 / (r**k) for k in range(n)]
    return [f_exact + c * (h**p_true) for h in hs], hs


print("=" * 78)
print("A. Textbook check: a sequence built to converge at order p")
print("=" * 78)
print("   f = f_exact + C*h^p,  h = 1, 1/2, 1/4  (coarsest first, as the docstring says)")
print()
print(f"{'p_true':>8} {'samples (coarse->fine)':>44} {'reported p':>12} {'status':>13}")

for p_true in (2.0, 1.0, 1.5, 3.0):
    vals, _ = richardson_sequence(p_true)
    result = compute_gci(vals, quantity="test", r=2.0)
    shown = ", ".join(f"{v:.6f}" for v in vals)
    print(f"{p_true:>8.1f} {shown:>44} {result.p:>12.4f} {result.status:>13}")

print()
print("=" * 78)
print("B. The same sequences fed FINEST FIRST")
print("=" * 78)
print(f"{'p_true':>8} {'reported p':>12} {'status':>13}")
for p_true in (2.0, 1.0, 1.5, 3.0):
    vals, _ = richardson_sequence(p_true)
    result = compute_gci(list(reversed(vals)), quantity="test", r=2.0)
    print(f"{p_true:>8.1f} {result.p:>12.4f} {result.status:>13}")

print()
print("=" * 78)
print("C. The real sequence, and what the increments say")
print("=" * 78)
real = [7959.445105, 7960.520968, 7963.136754]
d21 = real[1] - real[0]
d32 = real[2] - real[1]
r = 2.0
correct = -np.log(abs(d32 / d21)) / np.log(r)
print(f"  n=40/80/160 : {real}")
print(f"  increment coarse->medium : {d21:+.6f}")
print(f"  increment medium->fine   : {d32:+.6f}")
print(f"  increments are {'SHRINKING (converging)' if abs(d32) < abs(d21) else 'GROWING (diverging)'}")
print()
print(f"  correct observed order   : {correct:+.4f}")
print("    (negative => the sequence is not converging monotonically at a positive")
print("     order, so Richardson/GCI DOES NOT APPLY and the correct answer is reject)")
result = compute_gci(real, quantity="limit_load", r=2.0)
p_str = f"{result.p:+.4f}" if result.p is not None else "n/a (rejected before extrapolation)"
if result.gci_fine_pct is not None:
    gci_str = f"{result.gci_fine_pct:.5f} %"
else:
    gci_str = "n/a (rejected, no GCI reported)"
print(f"  what the shipped gate reports: p = {p_str}, status = {result.status}, GCI(fine) = {gci_str}")
print(f"  detail: {result.detail}")

print()
print("=" * 78)
print("D. Algebraic check of the asymptotic ratio")
print("=" * 78)
print(f"  claimed identity (legacy, absolute form): asymptotic_ratio == r^(2p)?")
for p_true in (1.0, 2.0):
    vals, _ = richardson_sequence(p_true)
    res = compute_gci(vals, quantity="t", r=2.0)
    ratio = res.asymptotic_ratio if res.asymptotic_ratio is not None else float("nan")
    predicted = 2.0 ** (2 * res.p)
    equal_r2p = abs(ratio - predicted) < 1e-9
    equal_1 = abs(ratio - 1.0) < 1e-12
    print(f"    p={p_true}: reported ratio = {ratio:.6g}, "
          f"r^(2p) = {predicted:.6g}, legacy r^(2p)-identity = {equal_r2p}, "
          f"corrected-form identity (=1) = {equal_1}")
print()
print("  Interpretation: with the SIGN-INVERTED (pre-fix) order formula the legacy")
print("  absolute-form ratio equals r^(2p) exactly -- an algebraic identity, so it")
print("  carries no information beyond p.  With the corrected formula it is")
print("  identically 1.  Either way it is NOT an independent check, which is why it")
print("  is no longer used as a gate.  The gate now uses the literature's relative-")
print("  form consistency ratio GCI_32*r^p/GCI_21 (Celik et al. 2008), which for an")
print("  observed p reduces to |f1|/|f2| -- a same-magnitude sanity check only.")
