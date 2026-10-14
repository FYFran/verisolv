"""End-to-end demonstration of the closed loop.

1. a load-controlled analysis fails at a limit point;
2. verification says the failure is real (and why);
3. diagnosis names the mechanism;
4. the repair layer switches control variable and re-runs;
5. verification signs off on the new answer.

Run from the project root:  python tools/demo_closed_loop.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verisolv.models import von_mises_truss  # noqa: E402
from verisolv.repair import repair  # noqa: E402
from verisolv.solver import SolverOptions, solve  # noqa: E402
from verisolv.verify import verify  # noqa: E402

REFERENCE_LOAD = 20_000.0


def rule(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main() -> int:
    model = von_mises_truss(1.0, 0.1, 1.0e-4, REFERENCE_LOAD)

    rule("STEP 1  first attempt: load control, no adaptivity")
    first = solve(model, SolverOptions(control="load", n_steps=10, max_iter=30, adaptive=False))
    print(f"converged          : {first.converged}")
    print(f"failure            : {first.failure}")
    print(f"increments accepted: {len(first.steps)}")
    print(f"load reached       : {first.load_factor * REFERENCE_LOAD:,.1f} N of {REFERENCE_LOAD:,.0f} N requested")
    if first.failures:
        f = first.failures[-1]
        print(f"rejected increment : target lambda {f.control_trial:.4f}")
        print(f"iterations         : {f.iterations}")
        print("residual history   :", " ".join(f"{v:.3e}" for v in f.residual_history[:8]), "...")
    print(f"message            : {first.message}")

    rule("STEP 2  the solver's own claim is not evidence")
    print("The run did not converge, so there is no state to verify.")
    print("The honest reading: 'I could not solve this load level.'")
    print("What we do NOT yet know is whether that is a bug or a property of the structure.")

    rule("STEP 3-5  diagnose, repair, re-verify")
    outcome = repair(
        model,
        SolverOptions(control="load", n_steps=10, max_iter=30, adaptive=False),
        target_displacement=-0.1934,
    )

    print(f"diagnosis          : {outcome.diagnosis.kind}")
    print(f"summary            : {outcome.diagnosis.summary}")
    print()
    print("attempts:")
    for attempt in outcome.attempts:
        verdict = attempt.report.verdict if attempt.report else "not converged"
        mark = "ACCEPTED" if attempt.accepted else "rejected"
        print(f"  [{mark:>8}] {attempt.strategy:<22} converged={attempt.result.converged!s:<5} verdict={verdict}")
        print(f"             why: {attempt.rationale}")

    print()
    print(f"solved             : {outcome.solved}")
    print(f"verification       : {outcome.report.verdict if outcome.report else 'n/a'}")
    if outcome.report:
        for check in outcome.report.checks:
            print(f"  [{'ok' if check.passed else 'FAIL':>4}] {check.name:<20} {check.detail}")

    if not outcome.solved:
        print()
        print("The repair layer could not reach a verified answer.")
        return 1

    result = outcome.result
    rule("equilibrium path recovered by the repair")
    print(f"control variable   : {result.control}")
    print(f"{'control (m)':>12} {'lambda':>10} {'apex force (N)':>16} {'iters':>6}")
    stride = max(len(result.steps) // 24, 1)
    for step in result.steps[::stride]:
        print(
            f"{step.control_end:>12.5f} {step.load_factor:>10.4f} "
            f"{step.load_factor * REFERENCE_LOAD:>16.1f} {step.iterations:>6}"
        )
    loads = np.array([s.load_factor * REFERENCE_LOAD for s in result.steps])
    peak = int(np.argmax(loads))
    print()
    print(f"limit load found   : {loads[peak]:,.1f} N at apex drop {-result.steps[peak].control_end:.5f} m")
    print("closed form        : 7,963.2 N at 0.04226 m")
    print(f"final load factor  : {result.load_factor:.4f}  ({result.load_factor * REFERENCE_LOAD:,.1f} N)")
    print("a negative load factor means the structure is pushing back:")
    print("the same displacement now needs less force than at the limit point.")

    out = Path(__file__).resolve().parent.parent / "runs"
    out.mkdir(exist_ok=True)
    (out / "closed_loop.json").write_text(
        json.dumps(outcome.to_dict(), indent=2, default=float), encoding="utf-8"
    )
    print()
    print(f"evidence written to {out / 'closed_loop.json'}")
    return 0 if outcome.solved else 1


if __name__ == "__main__":
    raise SystemExit(main())
