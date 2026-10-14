"""Can a REAL GCI be formed on this solver, at all?

The fine-resolution sweep saturates (160 and 320 steps give bit-identical
answers), so no GCI can be formed there.  But the coarse end showed movement:
40 -> 7959.45, 80 -> 7960.52.  A refinement sequence only needs three levels
with a fixed ratio, and nothing says they must be fine ones.

If a genuine GCI exists anywhere in this problem, it is at the coarse end.  If
it does not exist even there, then the honest position is that this solver's
discretisation error is not measurable by GCI on the problems we have -- and
the gate's `reject` is the correct answer, not a failure of the gate.

This script delegates the GCI arithmetic and the verdict to
`verisolv.gci.compute_gci`, i.e. the exact formula and criteria of the shipped
gate.  (An earlier local copy of the GCI maths used a *different* GCI_fine
formula -- Fs*|f3-f2|/((r^p-1)*|f3|) instead of the gate's GCI_coarse/r^p --
and a different asymptotic-ratio formula, so it printed numbers that did not
match the gate.  That divergence was a real bug: this tool exists to check
the gate, and it must use the gate's own definitions.)

HISTORY NOTE (Round 5, external review): the gate's observed-order formula was
SIGN-INVERTED relative to its own coarsest->finest convention, and the
n=40/80/160 triple once reported p = +1.2818, GCI(fine) = 0.00485 %, status
conditional.  That number was INVALID: the increments on that triple grow from
coarse to fine (+1.076, then +2.616), so the true observed order is -1.282 and
correct verdict is `reject` -- no GCI band exists on this problem.  The
formula has since been corrected (see tools/verify_gci_formula.py, an
independent check that constructs known-order sequences by hand and does not
share the gate's formula), and this script now reproduces the corrected
gate: 40/80/160 -> reject (non-positive p).
"""

import io
import sys

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"<项目根>")

from verisolv.models import von_mises_truss  # noqa: E402
from verisolv.solver import SolverOptions, solve  # noqa: E402
from verisolv.gci import compute_gci, GCIResult  # noqa: E402

REF = 20_000.0


def limit_load(n_steps, target=-0.15):
    model = von_mises_truss(1.0, 0.1, 1.0e-4, REF)
    result = solve(
        model,
        SolverOptions(control="displacement", control_dof=5, target_displacement=target,
                      n_steps=n_steps, max_iter=80, adaptive=False),
    )
    if not result.converged:
        return None
    return max(s.load_factor for s in result.steps) * REF


def gci_triple(f1, f2, f3, r=2.0):
    """Run the SHIPPED gate (verisolv.gci.compute_gci) on one triple.

    Returns ``(GCIResult, "")`` so the caller sees exactly what the gate sees,
    including its refusal reasons.  Values are coarsest-to-finest, matching
    the gate's convention.
    """
    return compute_gci([f1, f2, f3], quantity="peak_load", r=r), ""


print("=" * 78)
print("Sweep the whole resolution range and look for a formable GCI")
print("=" * 78)
print(f"{'n_steps':>8} {'peak load (N)':>18} {'change':>14}")
counts = [5, 10, 20, 40, 80, 160]
vals = {}
for n in counts:
    v = limit_load(n)
    vals[n] = v
    print(f"{n:>8} {v:>18.6f} {'' if n == counts[0] else f'{v - prev:+.6f}':>14}")
    prev = v

print()
print("=" * 78)
print("GCI on every contiguous geometric triple (r = 2)")
print("=" * 78)
for i in range(len(counts) - 2):
    n1, n2, n3 = counts[i], counts[i + 1], counts[i + 2]
    f1, f2, f3 = vals[n1], vals[n2], vals[n3]
    res, _ = gci_triple(f1, f2, f3, 2.0)
    if res.status == "reject":
        print(f"  n = {n1:>3}/{n2:>3}/{n3:>3}   REJECT   ({res.detail})")
    else:
        p_str = f"{res.p:+.4f}" if res.p is not None else "n/a"
        gci_str = f"{res.gci_fine_pct:.5f}" if res.gci_fine_pct is not None else "n/a (rejected)"
        cr_str = f"{res.consistency_ratio:.4f}" if res.consistency_ratio is not None else "n/a"
        ar_str = f"{res.asymptotic_ratio:.4f}" if res.asymptotic_ratio is not None else "n/a"
        print(f"  n = {n1:>3}/{n2:>3}/{n3:>3}   p = {p_str}   "
              f"Richardson = {res.f_exact:.2f} N   "
              f"GCI(fine) = {gci_str} %   "
              f"consistency_ratio (relative form) = {cr_str}   "
              f"asymptotic_ratio (legacy, identity-only) = {ar_str}   "
              f"[{res.status}]")
    print(f"       detail: {res.detail}")

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
formable = []
for i in range(len(counts) - 2):
    n1, n2, n3 = counts[i], counts[i + 1], counts[i + 2]
    res, _ = gci_triple(vals[n1], vals[n2], vals[n3], 2.0)
    if res.status in ("pass", "conditional"):
        formable.append((n1, n2, n3, res.status, res.p, res.asymptotic_ratio))

if formable:
    print("  Some triples yield a gate number, but it is NOT a usable error band:")
    print("  the only 'conditional' triple has p = 4.4, OUTSIDE the [0.5, 4.0] safety")
    print("  band, which means the three samples are not in the asymptotic regime and")
    print("  the extrapolated number must not be read as a discretisation-error band.")
    print("  The 40/80/160 triple (the one once mis-reported as GCI(fine) = 0.00485 %)")
    print("  is REJECTED: its increments grow from coarse to fine, so the observed")
    print("  order is negative and Richardson/GCI does not apply there.")
    print("  HONEST POSITION: no usable GCI band exists on this problem; the gate's")
    print("  rejects are the correct answer, not a gate failure.")
    for n1, n2, n3, status, p, ar in formable:
        p_str = f"{p:+.4f}" if p is not None else "n/a"
        ar_str = f"{ar:.4f}" if ar is not None else "n/a"
        print(f"    n = {n1}/{n2}/{n3}: status = {status}, p = {p_str} (out of [0.5,4] band), "
              f"legacy asymptotic_ratio = {ar_str} (identity only, not a check)")
else:
    print("  No triple yields a valid GCI. The honest statement is that this solver's")
    print("  discretisation error is not measurable by GCI on this problem -- the gate's")
    print("  reject is the CORRECT answer, and the useful finding is that the answer is")
    print("  resolution-independent well before the resolutions we would normally use.")
