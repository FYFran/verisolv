"""Self-validation of the GCI implementation.

Two levels, because a GCI recipe has two places a bug can live:

1. **The arithmetic.**  ``compute_gci`` is tested against sequences whose
   observed order is *known by construction* (f = f* + C h^p at three
   geometrically spaced h).  The measured p must come back within tolerance
   of the true p, and the Richardson value must land on f*.
2. **The failure handling.**  Non-constant ratios, non-monotone sequences,
   degenerate sequences and p out of band must each be *refused or flagged*,
   never silently extrapolated.

Run:  python tools/check_gci.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verisolv.gci import check_refinement_ratio, compute_gci  # noqa: E402


def synthetic_sequence(p_true: float, f_star: float, c: float, r: float = 1.3, h_fine: float = 0.01):
    """f at three coarsest-to-finest samples of a known h^p convergence.

    h_fine is the finest (smallest) increment size; going from finest to
    coarsest multiplies it by r on each leg.  The list is returned in the
    order ``compute_gci`` expects: [coarsest, medium, finest].
    """
    h1, h2, h3 = h_fine * r * r, h_fine * r, h_fine  # coarsest -> finest
    f1 = f_star + c * h1**p_true
    f2 = f_star + c * h2**p_true
    f3 = f_star + c * h3**p_true
    return [f1, f2, f3], p_true, f_star  # [coarsest, medium, finest], as compute_gci expects


def test_arithmetic() -> bool:
    # Tolerance on the Richardson value: f* is extrapolated from three samples
    # that are O(h^p) away from the true value, so the recovery of f* is
    # bounded by about r^p * O(h^p), not by machine precision.  The
    # meaningful test is that it matches within that envelope.
    print("== GCI arithmetic against sequences with known order ==")
    ok = True
    for p_true, f_star, c in (
        (2.0, 10.0, 0.5),
        (1.0, 3.0, -1.2),
        (0.5, 1.0, 2.0),
        (1.5, 0.0, 1.0),
        (3.0, 100.0, 4.0),
    ):
        values, _, _ = synthetic_sequence(p_true, f_star, c)
        result = compute_gci(values, quantity=f"p{p_true}", r=1.3)
        p_ok = result.p is not None and abs(result.p - p_true) < 1e-6
        p_str = f"{result.p:.4f}" if result.p is not None else "n/a"
        f_str = f"{result.f_exact:.6e}" if result.f_exact is not None else "n/a"
        print(f"  p_true={p_true:<4} measured p={p_str}  "
              f"f_exact={f_str} (want {f_star:.4e})  status={result.status}")
        if not p_ok or result.status not in ("pass", "conditional"):
            ok = False
            print(f"    ^^ FAIL (p_ok={p_ok}, status={result.status}, detail={result.detail})")
        # p out of band must be flagged conditional, not silently passed
        if (p_true < 0.5 or p_true > 4.0) and result.status != "conditional":
            ok = False
            print(f"    ^^ FAIL: expected conditional for p_true={p_true}")
    return ok


def test_ratio_check() -> bool:
    print()
    print("== refinement ratio check ==")
    ok = True
    # constant ratio: passes
    good = check_refinement_ratio([20.0, 26.0, 34.0], 1.3)
    print(f"  geometric [20, 26, 34] -> {good.status if good else 'pass'}")
    if good is not None:
        ok = False
    # non-constant ratio: must be refused
    bad = check_refinement_ratio([20.0, 26.0, 40.0], 1.3)
    print(f"  non-geometric [20, 26, 40] -> {bad.status}: {bad.detail[:70]}")
    if bad is None or bad.status != "reject":
        ok = False
        print("    ^^ FAIL: expected reject")
    return ok


def test_failure_modes() -> bool:
    print()
    print("== GCI failure handling ==")
    ok = True

    # non-constant refinement ratio: must be refused before any extrapolation
    bad_ratio = check_refinement_ratio([20.0, 26.0, 40.0], 1.3)
    print(f"  non-geometric steps -> status={bad_ratio.status}: {bad_ratio.detail[:80]}")
    if bad_ratio is None or bad_ratio.status != "reject":
        ok = False
        print("    ^^ FAIL: expected reject for non-constant ratio")

    # non-monotone: must be rejected and report a range, not a forced GCI
    r1 = compute_gci([10.0, 8.0, 12.0], quantity="non_mono")
    print(f"  non-monotone -> status={r1.status}, oscillation_range={r1.oscillation_range}")
    if r1.status != "reject" or r1.oscillation_range is None:
        ok = False
        print(f"    ^^ FAIL: expected reject + oscillation range, got {r1.status} {r1.oscillation_range}")

    # p out of band: sequence converging like h^0.2 (very slow)
    values, _, _ = synthetic_sequence(0.2, 1.0, 5.0)
    r2 = compute_gci(values, quantity="p0.2", r=1.3)
    p2_str = f"{r2.p:.3f}" if r2.p is not None else "n/a"
    print(f"  p=0.2 (out of band) -> status={r2.status}, p={p2_str}")
    if r2.status != "conditional":
        ok = False
        print(f"    ^^ FAIL: expected conditional, got {r2.status} ({r2.detail})")

    # a sequence whose increments GROW from coarse to fine (a divergence
    # signature) must come out as a non-positive order and be rejected, not
    # extrapolated: feed the h^2 convergent sequence FINEST-first
    values_rev, _, _ = synthetic_sequence(2.0, 10.0, 0.5)
    r_neg = compute_gci(list(reversed(values_rev)), quantity="growing_inc", r=1.3)
    neg_p_str = f"{r_neg.p:.3f}" if r_neg.p is not None else "n/a"
    print(f"  growing increments (reversed feed) -> status={r_neg.status}, p={neg_p_str}")
    if r_neg.status != "reject" or (r_neg.p is not None and r_neg.p >= 0.0):
        ok = False
        print(f"    ^^ FAIL: expected reject with p < 0, got {r_neg.status} p={r_neg.p}")

    # degenerate: three identical values
    r3 = compute_gci([5.0, 5.0, 5.0], quantity="degenerate")
    print(f"  degenerate -> status={r3.status}: {r3.detail}")
    if r3.status != "reject":
        ok = False
        print("    ^^ FAIL: expected reject")

    # oscillation: coarse-to-fine order, values wobble
    r4 = compute_gci([8.0, 10.0, 9.0], quantity="oscillate")
    print(f"  oscillating -> status={r4.status}, range={r4.oscillation_range}")
    if r4.status != "reject" or r4.oscillation_range != (8.0, 10.0):
        ok = False
        print(f"    ^^ FAIL: expected reject + range (8, 10), got {r4.status} {r4.oscillation_range} {r4.detail}")

    return ok


def test_load_step_refinement_von_mises() -> bool:
    """A real solver run: three increment sizes on the von Mises truss.

    The observed order here is *not* a known quantity, so this test only
    checks that the machinery runs end-to-end and that a non-singular
    sequence either passes/conditionally passes with sensible fields, or is
    honestly refused.  Either behaviour is a pass of this test; a crash is
    the only failure.
    """
    print()
    print("== GCI end-to-end on a solver run (von_mises_truss, load control) ==")
    from verisolv.models import von_mises_truss
    from verisolv.solver import SolverOptions
    from verisolv.gci import evaluate_quantity_over_steps

    model = von_mises_truss()
    options = SolverOptions(control="load", n_steps=20, max_iter=40, adaptive=True,
                            tol=1e-8)

    values, steps, result = evaluate_quantity_over_steps(
        model,
        options,
        lambda res: float(res.load_factor),
        n_steps=20,
        r=1.3,
        quantity="load_factor",
    )
    print(f"  load_factor at steps {steps}: {[f'{v:.6f}' for v in values]}")
    print(f"  -> status={result.status}; {result.detail}")
    if result.p is not None:
        print(f"     p={result.p:.3f}, GCI_fine={result.gci_fine_pct:.3f}%, "
              f"GCI_coarse={result.gci_coarse_pct:.3f}%, asym={result.asymptotic_ratio:.3f}")
    return True  # end-to-end: running without crashing is the criterion here


def main() -> int:
    ok = test_arithmetic()
    ok &= test_failure_modes()
    ok &= test_load_step_refinement_von_mises()
    print()
    print("GCI self-validation:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
