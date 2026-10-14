"""Command-line interface: a JSON contract for an agent to drive the solver.

Every command writes a single JSON object to stdout and nothing else, so a
caller never has to parse prose.  Diagnostics go to stderr and are not part of
the contract.

    python -m verisolv models
    python -m verisolv solve  --model von_mises_truss --control load --n-steps 10
    python -m verisolv verify --model von_mises_truss --control load --n-steps 10
    python -m verisolv repair --model von_mises_truss --control load --n-steps 10

Exit codes: 0 success, 1 the analysis did not produce a trustworthy answer,
2 the request itself was invalid.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import numpy as np

from . import models as model_registry
from .fem import (
    Model,
    bar_engineering_stresses,
    bar_forces,
    bar_stresses,
    reactions,
)
from .repair import repair as run_repair
from .solver import SolverOptions, limit_point, solve
from .verify import claim_level, verify as run_verify

EXIT_OK = 0
EXIT_UNTRUSTWORTHY = 1
EXIT_BAD_REQUEST = 2


# ---------------------------------------------------------------------------
# serialisation helpers
# ---------------------------------------------------------------------------


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def _emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, default=_json_default, indent=2)
    sys.stdout.write("\n")


def _fail(message: str, code: int = EXIT_BAD_REQUEST) -> int:
    _emit({"ok": False, "error": message})
    return code


# ---------------------------------------------------------------------------
# option plumbing
# ---------------------------------------------------------------------------


def _parse_params(pairs: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--param expects key=value, got {pair!r}")
        key, raw = pair.split("=", 1)
        key = key.strip()
        raw = raw.strip()
        try:
            out[key] = json.loads(raw)
        except json.JSONDecodeError:
            out[key] = raw
    return out


def _build_model(args: argparse.Namespace) -> Model:
    params = _parse_params(args.param)
    return model_registry.build(args.model, **params)


def _build_options(args: argparse.Namespace) -> SolverOptions:
    return SolverOptions(
        control=args.control,
        n_steps=args.n_steps,
        max_iter=args.max_iter,
        tol=args.tol,
        adaptive=args.adaptive,
        line_search=args.line_search,
        max_cutbacks=args.max_cutbacks,
        control_dof=args.control_dof,
        target_displacement=args.target_displacement,
        step_growth=args.step_growth,
    )


def _path(result, points: int) -> list[dict[str, float]]:
    steps = result.steps
    if not steps:
        return []
    stride = max(len(steps) // max(points, 1), 1)
    chosen = steps[::stride]
    if chosen[-1] is not steps[-1]:
        chosen = chosen + [steps[-1]]
    return [
        {
            "control": s.control_end,
            "load_factor": s.load_factor,
            "max_displacement": s.max_displacement,
            "iterations": s.iterations,
        }
        for s in chosen
    ]


def _reference_load(model: Model) -> float:
    """Magnitude of the resultant reference load, so factors can be read in newtons."""
    return float(np.linalg.norm(model.load_vector().reshape(-1, 2).sum(axis=0)))


def _peak_payload(model: Model, result) -> dict[str, Any] | None:
    """The maximum load carried anywhere along the traced equilibrium path.

    This is the number a caller actually wants when asking "how much can it
    take?".  Reporting it explicitly stops an agent from re-running the analysis
    with ever-finer steps trying to read the peak off the samples by eye.
    """
    if not result.steps:
        return None
    factors = [s.load_factor for s in result.steps]
    index = max(range(len(factors)), key=factors.__getitem__)
    reference = _reference_load(model)
    step = result.steps[index]
    return {
        "load_factor": factors[index],
        "absolute_load": factors[index] * reference,
        "reference_load": reference,
        "at_control_value": step.control_end,
        "max_displacement": step.max_displacement,
        "interior": 0 < index < len(factors) - 1,
    }


def _result_payload(model: Model, result, path_points: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model.name,
        "control": result.control,
        "converged": result.converged,
        "failure": result.failure,
        "message": result.message,
        "load_factor": result.load_factor,
        "control_value": result.control_value,
        "accepted_steps": len(result.steps),
        "rejected_steps": len(result.failures),
        "max_displacement": result.steps[-1].max_displacement if result.steps else 0.0,
        "path": _path(result, path_points),
        "rejected": [
            {
                "at_control": f.control_trial,
                "failure": f.failure,
                "iterations": f.iterations,
                "residual_norm": f.residual_norm,
                "residual_tail": [float(v) for v in f.residual_history[-5:]],
            }
            for f in result.failures[-5:]
        ],
    }
    lp = limit_point(result)
    if lp:
        payload["limit_point_estimate"] = lp
    peak = _peak_payload(model, result)
    if peak:
        payload["peak_load"] = peak
    return payload


def _state_payload(model: Model, result) -> dict[str, Any]:
    """Physical quantities at the final state, for a caller that wants evidence.

    Both stress measures are reported **and labelled**, because they answer
    different questions and silently mixing them is how a design check ends up
    comparing the wrong number:

    * ``bar_stress_pk2``         -- second Piola-Kirchhoff, the constitutive measure
    * ``bar_stress_engineering`` -- N/A0, the measure design codes are written in

    A caller doing a stress check wants the engineering stress.  At the
    displacements this solver is used for, the two differ by about 0.1% here but
    by far more on flexible structures, and by a factor that grows with the
    stretch rather than staying fixed.
    """
    if result.u is None or not result.converged:
        return {}
    react = reactions(model, result.u, result.load_factor)
    applied = result.load_factor * model.load_vector()
    return {
        "bar_forces": [float(v) for v in bar_forces(model, result.u)],
        "bar_stress_pk2": [float(v) for v in bar_stresses(model, result.u)],
        "bar_stress_engineering": [
            float(v) for v in bar_engineering_stresses(model, result.u)
        ],
        "stress_measure_note": (
            "design checks must use bar_stress_engineering (N/A0); "
            "bar_stress_pk2 is the constitutive measure"
        ),
        "reaction_sum": react.reshape(-1, 2).sum(axis=0).tolist(),
        "applied_sum": applied.reshape(-1, 2).sum(axis=0).tolist(),
        "groups": model.bar_groups,
        "total_mass": model.total_mass(),
    }


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_models(_: argparse.Namespace) -> int:
    catalogue = {}
    for name in sorted(model_registry.MODELS):
        model = model_registry.build(name)
        catalogue[name] = {
            "nodes": model.node_count,
            "bars": len(model.bars),
            "free_dofs": model.free_dofs().tolist(),
            "groups": model.bar_groups,
            "default_mass": model.total_mass(),
            "total_load": float(np.abs(model.load_vector()).sum()),
        }
    _emit({"ok": True, "models": catalogue})
    return EXIT_OK


def cmd_solve(args: argparse.Namespace) -> int:
    model = _build_model(args)
    result = solve(model, _build_options(args))
    payload = {"ok": True, "command": "solve", **_result_payload(model, result, args.path_points)}
    if args.include_state:
        payload["state"] = _state_payload(model, result)
    _emit(payload)
    return EXIT_OK if result.converged else EXIT_UNTRUSTWORTHY


def cmd_verify(args: argparse.Namespace) -> int:
    model = _build_model(args)
    result = solve(model, _build_options(args))
    payload: dict[str, Any] = {
        "ok": True,
        "command": "verify",
        **_result_payload(model, result, args.path_points),
    }
    if not result.converged:
        payload["verification"] = None
        payload["verdict"] = "not_converged"
        payload["claim_level"] = "smoke"
        _emit(payload)
        return EXIT_UNTRUSTWORTHY
    report = run_verify(
        model,
        result,
        tol_residual=args.tol_residual,
        tol_equilibrium=args.tol_equilibrium,
        jump_factor=args.jump_factor,
        refine=args.refine,
        gci=not args.no_gci,
        gci_n_steps=args.gci_n_steps,
        gci_r=args.gci_r,
    )
    payload["verification"] = report.to_dict()
    payload["verdict"] = report.verdict
    payload["claim_level"] = claim_level(report, result)
    _emit(payload)
    return EXIT_OK if report.verdict == "verified" else EXIT_UNTRUSTWORTHY


def cmd_repair(args: argparse.Namespace) -> int:
    model = _build_model(args)
    outcome = run_repair(
        model,
        _build_options(args),
        target_displacement=args.target_displacement,
        verify_kwargs={
            "tol_residual": args.tol_residual,
            "tol_equilibrium": args.tol_equilibrium,
            "jump_factor": args.jump_factor,
            "refine": args.refine,
            "gci": not args.no_gci,
            "gci_n_steps": args.gci_n_steps,
            "gci_r": args.gci_r,
        },
    )
    verdict = outcome.report.verdict if outcome.report else "not_converged"
    peak = _peak_payload(model, outcome.result) if outcome.result.steps else None
    path = _path(outcome.result, args.path_points) if outcome.result.steps else []

    payload: dict[str, Any] = {
        "ok": True,
        "command": "repair",
        "model": model.name,
        "solved": outcome.solved,
        "verdict": verdict,
        "claim_level": outcome.claim_level_value,
        "peak_load": peak,
        "path": path,
        **outcome.to_dict(),
    }
    if peak:
        claim = payload["claim_level"]
        gci_note = ""
        gci_check = next(
            (c for c in (outcome.report.to_dict()["checks"] if outcome.report else []) if c["name"] == "gci"),
            None,
        )
        if gci_check is not None:
            gci_note = f" GCI status: {gci_check.get('evidence', {}).get('gci_status', 'n/a')}."
        payload["conclusion"] = (
            f"Maximum load carried along the traced equilibrium path: "
            f"{peak['absolute_load']:.1f} N (load factor {peak['load_factor']:.6f}) at control "
            f"value {peak['at_control_value']:.6g}; verification verdict: {verdict}; "
            f"claim level: {claim}."
            + gci_note
        )
    if args.include_state and outcome.solved and outcome.result.u is not None:
        payload["state"] = _state_payload(model, outcome.result)
    _emit(payload)
    return EXIT_OK if outcome.solved else EXIT_UNTRUSTWORTHY


def cmd_cases(args: argparse.Namespace) -> int:
    """Run the labelled case library and report the confusion matrix."""
    from .cases import run_all

    data = run_all(verbose=False)
    _emit({"ok": True, "command": "cases", **data})
    if args.strict:
        summary = data["summary"]
        # --strict means "the system behaved exactly as the library says it
        # should": every detectable error caught, no positive control cried
        # wolf, and the repair chain acted correctly on every case.  These are
        # the three questions summarise() keeps apart on purpose -- the old
        # single "accuracy" scalar that --strict used to read no longer exists
        # (collapsing the three questions into one figure is the failure this
        # project exists to name), so --strict now reads the three lists
        # directly rather than an accuracy number.
        if summary["missed"]:
            _emit({"ok": True, "command": "cases", "strict": "failed",
                   "reason": f"detectable errors missed: {summary['missed']}"})
            return EXIT_UNTRUSTWORTHY
        if summary["controls_false_alarm"]:
            _emit({"ok": True, "command": "cases", "strict": "failed",
                   "reason": f"positive-control false alarms: {summary['controls_false_alarm']}"})
            return EXIT_UNTRUSTWORTHY
        if summary["repair_mismatch"]:
            _emit({"ok": True, "command": "cases", "strict": "failed",
                   "reason": f"repair mismatches: {summary['repair_mismatch']}"})
            return EXIT_UNTRUSTWORTHY
        _emit({"ok": True, "command": "cases", "strict": "passed"})
        return EXIT_OK
    return EXIT_OK



def cmd_checkmodel(args: argparse.Namespace) -> int:
    """Inspect a model for well-posedness and plausibility, without solving it."""
    from .checkmodel import check_model

    model = _build_model(args)
    report = check_model(model)
    _emit({"ok": True, "command": "checkmodel", "model": model.name, **report.to_dict()})
    return EXIT_OK if report.verdict == "ok" else EXIT_UNTRUSTWORTHY


def cmd_mms(args: argparse.Namespace) -> int:
    """Method of Manufactured Solutions: code verification of the operator's convergence order.

    Delegates to the self-contained MMS tool. This is an additive command:
    it does not modify any existing algorithm function.
    """
    import importlib.util
    import os
    import sys
    tool_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools"))
    mms_path = os.path.join(tool_dir, "mms_verification.py")
    spec = importlib.util.spec_from_file_location("mms_verification", mms_path)
    mms_mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules before exec so @dataclass introspection works.
    sys.modules["mms_verification"] = mms_mod
    spec.loader.exec_module(mms_mod)
    del sys.modules["mms_verification"]
    from .models import build as build_model
    model = build_model(args.model)
    report = mms_mod.run_mms(
        model,
        n_steps_list=args.n_steps_list,
        target_displacement=args.target_displacement,
        field_name=args.field,
    )
    # Convert dataclass runs to plain dicts so JSON serialisation works without numpy.
    runs_payload = []
    for r in report.runs:
        runs_payload.append({
            "n_steps": r.n_steps,
            "converged": r.converged,
            "solver_load_factor": r.solver_load_factor if not (isinstance(r.solver_load_factor, float) and (r.solver_load_factor != r.solver_load_factor or r.solver_load_factor in (float('inf'), float('-inf')))) else str(r.solver_load_factor),
            "solver_max_displacement": r.solver_max_displacement if not (isinstance(r.solver_max_displacement, float) and (r.solver_max_displacement != r.solver_max_displacement or r.solver_max_displacement in (float('inf'), float('-inf')))) else str(r.solver_max_displacement),
            "iterations": r.total_iterations,
        })
    payload: dict[str, Any] = {
        "ok": report.error is None,
        "command": "mms",
        "model": report.model_name,
        "field": report.field_name,
        "theory_p": report.theory_p,
        "observed_p": report.observed_p,
        "conclusion": report.conclusion,
        "sympy_source": report.sympy_source,
        "runs": runs_payload,
    }
    if report.error:
        payload["error"] = report.error
    _emit(payload)
    return EXIT_OK if report.error is None else EXIT_BAD_REQUEST


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verisolv",
        description="Self-verifying nonlinear structural analysis",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_models = sub.add_parser("models", help="list the available reference models")
    p_models.set_defaults(func=cmd_models)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--model", default="von_mises_truss", help="model name")
        p.add_argument("--param", action="append", default=[], metavar="KEY=VALUE",
                       help="model parameter override, repeatable")
        p.add_argument("--control", choices=["load", "displacement"], default="load")
        p.add_argument("--n-steps", type=int, default=10)
        p.add_argument("--max-iter", type=int, default=30)
        p.add_argument("--max-cutbacks", type=int, default=12)
        p.add_argument("--tol", type=float, default=1e-8)
        p.add_argument("--adaptive", action=argparse.BooleanOptionalAction, default=True)
        p.add_argument("--line-search", action=argparse.BooleanOptionalAction, default=False)
        p.add_argument("--step-growth", type=float, default=1.0)
        p.add_argument("--control-dof", type=int, default=None)
        p.add_argument("--target-displacement", type=float, default=None)
        p.add_argument("--path-points", type=int, default=10,
                       help="how many equilibrium-path samples to return")
        p.add_argument("--include-state", action=argparse.BooleanOptionalAction, default=False,
                       help="include bar forces, stresses and reaction sums")

    def verification(p: argparse.ArgumentParser) -> None:
        p.add_argument("--tol-residual", type=float, default=1e-6)
        p.add_argument("--tol-equilibrium", type=float, default=1e-6)
        p.add_argument("--jump-factor", type=float, default=20.0)
        p.add_argument("--refine", type=int, default=2)
        p.add_argument("--no-gci", action="store_true",
                       help="disable the GCI (quantified discretisation-error) gate")
        p.add_argument("--gci-n-steps", type=int, default=20,
                       help="base step count for the GCI three-run study (default 20)")
        p.add_argument("--gci-r", type=float, default=1.3,
                       help="fixed geometric refinement ratio r for the GCI (default 1.3)")

    p_solve = sub.add_parser("solve", help="run one analysis and report raw outcome")
    common(p_solve)
    p_solve.set_defaults(func=cmd_solve)

    p_verify = sub.add_parser("verify", help="solve, then check the answer independently")
    common(p_verify)
    verification(p_verify)
    p_verify.set_defaults(func=cmd_verify)

    p_repair = sub.add_parser("repair", help="solve, verify, diagnose, escalate, re-verify")
    common(p_repair)
    verification(p_repair)
    p_repair.set_defaults(func=cmd_repair)

    p_cases = sub.add_parser(
        "cases", help="run the labelled failure/modeling case library and report accuracy"
    )
    p_cases.add_argument("--strict", action="store_true",
                         help="exit non-zero unless every case is classified as expected")
    p_cases.set_defaults(func=cmd_cases)

    p_check = sub.add_parser(
        "checkmodel",
        help="inspect a model for well-posedness and plausibility without running an analysis",
    )
    common(p_check)
    p_check.set_defaults(func=cmd_checkmodel)

    # ------------------------------------------------------------------
    # mms: Method of Manufactured Solutions (additive, new subcommand)
    # ------------------------------------------------------------------
    p_mms = sub.add_parser(
        "mms",
        help="MMS code verification: measure the operator's convergence order",
    )
    p_mms.add_argument("--model", default="cantilever_truss", help="model name")
    p_mms.add_argument("--param", action="append", default=[], metavar="KEY=VALUE",
                       help="model parameter override, repeatable")
    p_mms.add_argument("--field", default="linear_axial",
                       help="name of the manufactured displacement field")
    p_mms.add_argument("--target-displacement", type=float, default=0.01,
                       help="magnitude of the prescribed MMS displacement")
    p_mms.add_argument("--n-steps-list", type=int, nargs="+", default=[10, 20, 40, 80],
                       help="list of n_steps values, fine to coarse")
    p_mms.set_defaults(func=cmd_mms)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (KeyError, ValueError) as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
