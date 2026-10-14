"""A labelled library of failure and modelling cases, and the confusion matrix they produce.

The project's whole claim is that it can tell a trustworthy answer from an
untrustworthy one.  That claim is only as good as the diagnoser behind it -- and
until now the diagnoser had never itself been tested.  This module closes that
gap the only honest way: by constructing cases whose root cause is known *by
construction*, running the diagnoser on them, and reporting where it is wrong.

Two layers, because they fail for different reasons and need different fixes:

**Layer A -- solver failures.**
    Cases where the iteration genuinely cannot proceed: a limit point, a
    runaway increment, a singular tangent, non-finite arithmetic, an exhausted
    step.  These are the diagnoser's home ground, and the repair chain should
    be able to rescue most of them.  A case here that the diagnoser mislabels
    is a defect in the diagnoser.

**Layer B -- modelling errors.**
    Cases where the *input* is wrong: a missing restraint turns the structure
    into a mechanism, a reversed load sign, a unit slip, a material typo.  These
    are the honest limit of what numerical verification can do.  A reversed load
    still produces a perfectly converged, perfectly self-consistent, perfectly
    reproducible answer -- to the wrong question.  Layer B is where a rule-based
    diagnoser runs out and an agent that can inspect the model has to take over,
    and it is the experiment that decides whether the agent earns its place.

Each case is deterministic: same inputs, same verdict, every run.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from .fem import E_STEEL, Bar, Model
from .repair import (
    BRANCH_JUMP,
    DIVERGENCE,
    INCREMENT_EXHAUSTED,
    LIMIT_POINT,
    MECHANISM,
    NONFINITE,
    SINGULAR,
    UNKNOWN,
    diagnose,
    repair,
)
from .solver import (
    FAILURE_MAX_ITERATIONS,
    FAILURE_SINGULAR_TANGENT,
    SolverOptions,
    solve,
)
from .verify import verify

# Labels that are not produced by diagnose() but are legitimate outcomes.
CONVERGED_VERIFIED = "converged_verified"
CONVERGED_UNVERIFIED = "converged_unverified"
MODEL_REJECTED = "model_rejected"

ALL_LABELS = [
    LIMIT_POINT,
    DIVERGENCE,
    SINGULAR,
    MECHANISM,
    NONFINITE,
    INCREMENT_EXHAUSTED,
    BRANCH_JUMP,
    UNKNOWN,
    CONVERGED_VERIFIED,
    CONVERGED_UNVERIFIED,
    MODEL_REJECTED,
]


@dataclass
class Case:
    """One labelled experiment.

    ``root_cause`` is the ground truth: what is actually wrong.  It is known by
    construction, not inferred from what the software said.  ``detectable_by``
    records which subsystem *should* be able to notice, which is the column the
    whole exercise turns on -- a case that nothing can detect is not a bug in the
    detector, it is a fact about the class of error.

    For Layer A, ``root_cause`` is the solver's failure mode and the diagnoser is
    expected to name it.  For Layer B, ``root_cause`` is the *modelling* mistake,
    and the interesting question is whether any check can see it at all.
    """

    name: str
    layer: str                       # "solver" | "modelling"
    root_cause: str                  # the true error, known by construction
    expected: list[str]              # acceptable observed labels
    build: Callable[[], tuple[Model, SolverOptions, dict[str, Any]]]
    repair_should_help: bool         # is a strategy switch the right answer?
    injection: str                   # what was done to create the case
    detectable_by: str = "diagnoser" # diagnoser | verification | model_check | intent_only
    test_class: str = "failure"      # normal | boundary | failure
    # A non-trivial normal comparison: given the solve result, return
    # (what the solver computed, what it should be). Without one of these, the
    # "normal" class only proves the answer is self-consistent, never that it is
    # right. The verification gates are all internal or homologous; agreement with
    # a closed form is the one thing they cannot fake.
    analytical: Callable[[Any], tuple[float, float]] | None = None
    analytical_tolerance: float = 1e-9
    analytical_quantity: str = ""
    note: str = ""


# ---------------------------------------------------------------------------
# Layer A -- solver failures
# ---------------------------------------------------------------------------


def _shallow(half_span: float, rise: float, area: float, load: float) -> Model:
    coords = np.array([[-half_span, 0.0], [half_span, 0.0], [0.0, rise]])
    bars = [
        Bar(i=0, j=2, area=area, group="chord"),
        Bar(i=1, j=2, area=area, group="chord"),
    ]
    loads = np.array([[0.0, 0.0], [0.0, 0.0], [0.0, -load]])
    return Model(
        coords=coords,
        bars=bars,
        fixed={0: (True, True), 1: (True, True), 2: (True, False)},
        loads=loads,
        name=f"shallow_h{rise:g}",
    )


def layer_a() -> list[Case]:
    cases: list[Case] = []

    # --- limit point: load control driven into the fold -------------------
    for name, rise, load, steps in (
        ("A01_limit_point_baseline", 0.10, 20_000.0, 10),
        ("A02_limit_point_shallower", 0.06, 8_000.0, 10),
        ("A03_limit_point_fine_steps", 0.10, 20_000.0, 40),
    ):
        cases.append(
            Case(
                name=name,
                layer="solver",
                root_cause=LIMIT_POINT,
                detectable_by="verification",
                # Either outcome is a correct system response. The iteration may
                # refuse to proceed (diagnoser gets its turn), or it may escape to
                # the far branch and *converge* -- in which case the verification
                # layer is what catches it. Requiring only the first would mark a
                # correct catch as a miss.
                expected=[LIMIT_POINT, CONVERGED_UNVERIFIED],
                build=lambda r=rise, p=load, s=steps: (
                    _shallow(1.0, r, 1.0e-4, p),
                    SolverOptions(control="load", n_steps=s, max_iter=30, adaptive=False),
                    {},
                ),
                repair_should_help=True,
                injection=f"load control past the limit point (rise={rise}, {steps} steps)",
                note=(
                    "the shallower arch converges onto the far branch, so this case is "
                    "caught by verification rather than by the diagnoser"
                ),
            )
        )

    # --- tiny load: a regression guard, not a failure ---------------------
    # These two cases used to fail with step_exhausted.  The cause was
    # catastrophic cancellation in the strain measure (L^2 - L0^2), which put a
    # floor under the residual that the convergence test could never reach.  With
    # the cancellation-free form they converge and verify, so the correct label
    # now is a clean pass -- and the case exists to keep it that way.
    for name, load in (("A04_tiny_load_regression", 50.0), ("A05_tinier_load_regression", 5.0)):
        cases.append(
            Case(
                name=name,
                layer="solver",
                root_cause=CONVERGED_VERIFIED,
                detectable_by="none_expected",
                test_class="normal",
                expected=[CONVERGED_VERIFIED],
                build=lambda p=load: (
                    _shallow(1.0, 0.1, 1.0e-4, p),
                    SolverOptions(control="load", n_steps=10, max_iter=120, adaptive=True),
                    {},
                ),
                repair_should_help=False,
                injection=f"reference load {load:g} N",
                note=(
                    "regression guard for the cancellation bug in fem.bar_response: "
                    "this must stay converged and verified"
                ),
            )
        )

    # --- runaway increment -------------------------------------------------
    cases.append(
        Case(
            name="A06_divergence_single_step",
            layer="solver",
            root_cause=DIVERGENCE,
            detectable_by="diagnoser",
            expected=[DIVERGENCE, LIMIT_POINT, INCREMENT_EXHAUSTED],
            build=lambda: (
                _shallow(1.0, 0.1, 1.0e-4, 20_000.0),
                SolverOptions(control="load", n_steps=1, max_iter=6, adaptive=False),
                {},
            ),
            repair_should_help=True,
            injection="the whole load in one increment with a tiny iteration budget",
            note="few iterations at a huge step: the residual grows rather than settling",
        )
    )

    # --- singular tangent at zero load: a mechanism, not a limit point -----
    def mechanism_model() -> Model:
        """The cantilever with the base x-restraint removed: free to translate."""
        m = _cantilever()
        m.fixed[0] = (False, True)          # base bottom node no longer held in x
        return m

    cases.append(
        Case(
            name="A07_singular_mechanism_zero_load",
            layer="modelling",
            root_cause="missing_restraint_mechanism",
            detectable_by="model_check",
            expected=[MECHANISM, SINGULAR, UNKNOWN],
            build=lambda: (
                mechanism_model(),
                SolverOptions(control="load", n_steps=4, max_iter=30, adaptive=False),
                {},
            ),
            repair_should_help=False,
            injection="remove the base x-restraint -> rigid-body translation mode",
            note=(
                "the tangent is singular at ZERO load, which is the signature that "
                "distinguishes a mechanism from a limit point. The repair chain "
                "switching control variable cannot fix this, and should not."
            ),
        )
    )

    return cases


# ---------------------------------------------------------------------------
# Layer B -- modelling errors
# ---------------------------------------------------------------------------


def _cantilever(
    tip_load: float = -50_000.0,
    modulus: float = E_STEEL,
    panels: int = 4,
    span: float = 4.0,
    height: float = 1.0,
) -> Model:
    """The reference cantilever truss, parameterised for the modelling cases."""
    areas = {"bottom": 2.0e-3, "top": 2.0e-3, "vertical": 1.0e-3, "diagonal": 1.0e-3}
    step = span / panels
    bottom = [np.array([k * step, 0.0]) for k in range(panels + 1)]
    top = [np.array([k * step, height]) for k in range(panels + 1)]
    coords = np.array(bottom + top)

    def bot(k: int) -> int:
        return k

    def topp(k: int) -> int:
        return panels + 1 + k

    bars: list[Bar] = []
    for k in range(panels):
        bars.append(Bar(bot(k), bot(k + 1), areas["bottom"], modulus, group="bottom"))
        bars.append(Bar(topp(k), topp(k + 1), areas["top"], modulus, group="top"))
    for k in range(panels + 1):
        bars.append(Bar(bot(k), topp(k), areas["vertical"], modulus, group="vertical"))
    for k in range(panels):
        bars.append(Bar(bot(k), topp(k + 1), areas["diagonal"], modulus, group="diagonal"))

    loads = np.zeros_like(coords)
    loads[bot(panels), 1] = tip_load
    return Model(
        coords=coords,
        bars=bars,
        fixed={bot(0): (True, True), topp(0): (True, True)},
        loads=loads,
        name="cantilever_case",
    )


def layer_b() -> list[Case]:
    cases: list[Case] = []
    opts = lambda: SolverOptions(control="load", n_steps=10, max_iter=60, adaptive=True)

    # A reversed load converges beautifully -- to the wrong problem.  No amount
    # of residual or equilibrium checking can see it.
    cases.append(
        Case(
            name="B01_load_direction_reversed",
            layer="modelling",
            root_cause="load_direction_reversed",
            detectable_by="intent_only",
            expected=[CONVERGED_VERIFIED, CONVERGED_UNVERIFIED],
            build=lambda: (_cantilever(tip_load=+50_000.0), opts(), {}),
            repair_should_help=False,
            injection="tip load sign flipped to +Y (upward)",
            note=(
                "converges, verifies, and is still the answer to the wrong question. "
                "Numerical verification is structurally blind to this class; only a "
                "check on the model itself can catch it."
            ),
        )
    )

    # A unit slip: the load was written in kN but the solver reads newtons.
    cases.append(
        Case(
            name="B02_unit_slip_load_x1000",
            layer="modelling",
            root_cause="unit_slip_load_x1000",
            detectable_by="intent_only",
            expected=[CONVERGED_VERIFIED, CONVERGED_UNVERIFIED, LIMIT_POINT, DIVERGENCE,
                      INCREMENT_EXHAUSTED, BRANCH_JUMP],
            build=lambda: (_cantilever(tip_load=-50_000_000.0), opts(), {}),
            repair_should_help=False,
            injection="tip load written in kN, read as N (x1000)",
            note="nothing about the numbers looks wrong; they are simply not the asked-for load",
        )
    )

    # A material typo: E off by 1000x.
    cases.append(
        Case(
            name="B03_material_typo_E_x1000",
            layer="modelling",
            root_cause="material_typo_E_x1000",
            detectable_by="model_check",
            expected=[CONVERGED_VERIFIED, CONVERGED_UNVERIFIED, LIMIT_POINT, DIVERGENCE,
                      INCREMENT_EXHAUSTED, BRANCH_JUMP],
            build=lambda: (_cantilever(modulus=E_STEEL * 1000.0), opts(), {}),
            repair_should_help=False,
            injection="Young's modulus entered as 210 TPa instead of 210 GPa",
            note="deflections come out ~1000x too small and every check still passes",
        )
    )

    # A structure with no restraint at all in one direction: pure mechanism.
    def free_translation() -> Model:
        m = _cantilever()
        m.fixed[0] = (False, True)
        m.fixed[5] = (False, True)
        return m

    cases.append(
        Case(
            name="B04_missing_x_restraint",
            layer="modelling",
            root_cause="missing_x_restraint",
            detectable_by="model_check",
            expected=[MECHANISM, SINGULAR, UNKNOWN],
            build=lambda: (free_translation(), opts(), {}),
            repair_should_help=False,
            injection="both base nodes released in x -> unsupported translation",
        )
    )

    return cases


def layer_nominal_and_boundary() -> list[Case]:
    """Cases at the two ends of ordinary use: a clean job, and an edge.

    The competition asks for test samples in three classes -- normal, boundary and
    failure -- and building them from a different source than the failure cases
    would let the two drift apart. They come from the same library, so a change to
    the solver moves all three together.

    **Normal** cases are the ones a user actually has in mind: a service load, well
    inside the structure's capacity, which must converge and verify. They are
    positive controls in the strict sense -- if the system ever flags one of these,
    the system is wrong, not the structure.

    **Boundary** cases sit where the answer changes character. A load exactly at
    the limit point is the knife edge: one newton more and there is no equilibrium
    at all. A vanishing load probes the convergence test near zero, where the
    residual is compared against a number that has itself gone to nothing.
    """
    cases: list[Case] = []

    def opts(**overrides: Any) -> SolverOptions:
        base: dict[str, Any] = {
            "control": "load",
            "n_steps": 10,
            "max_iter": 60,
            "adaptive": True,
        }
        base.update(overrides)
        return SolverOptions(**base)

    # --- normal: work that should simply succeed --------------------------
    cases.append(
        Case(
            name="N01_nominal_cantilever_service_load",
            layer="modelling",
            root_cause="nominal_service_load",
            detectable_by="none_expected",
            expected=[CONVERGED_VERIFIED],
            build=lambda: (_cantilever(tip_load=-20_000.0), opts(), {}),
            repair_should_help=False,
            injection="a 20 kN tip load on the cantilever: 40% of what it carried before",
            test_class="normal",
            note=(
                "the ordinary case. It must converge and verify; if the system ever "
                "flags this, the system is wrong rather than the structure"
            ),
        )
    )
    cases.append(
        Case(
            name="N02_nominal_arch_below_limit",
            layer="modelling",
            root_cause="nominal_load_below_limit",
            detectable_by="none_expected",
            expected=[CONVERGED_VERIFIED],
            build=lambda: (
                _shallow(1.0, 0.10, 1.0e-4, 4_000.0),
                opts(n_steps=12),
                {},
            ),
            repair_should_help=False,
            injection="4 kN on the shallow arch: roughly half its limit load of 7.96 kN",
            test_class="normal",
            note="well inside the capacity, so equilibrium exists and is unique on this branch",
        )
    )

    # --- boundary: exactly at the limit point -----------------------------
    # The limit load of this arch was measured at 7963.16 N by displacement
    # control. Asking for precisely that, in a single load increment, puts the
    # iteration on the knife edge: the tangent is singular at the answer, so
    # whether it converges is a matter of arithmetic luck rather than method.
    # Either outcome is acceptable provided the system says which happened.
    cases.append(
        Case(
            name="E01_boundary_load_exactly_at_limit",
            layer="modelling",
            root_cause="load_exactly_at_limit_point",
            detectable_by="verification",
            expected=[LIMIT_POINT, CONVERGED_UNVERIFIED, CONVERGED_VERIFIED],
            build=lambda: (
                _shallow(1.0, 0.10, 1.0e-4, 7_963.16),
                SolverOptions(control="load", n_steps=1, max_iter=60, adaptive=False),
                {},
            ),
            # Load control pressing on the limit point is exactly the situation
            # displacement control exists for, so the escalation helping here is
            # the correct behaviour rather than a surprise.
            repair_should_help=True,
            injection="the measured limit load, applied in one increment",
            test_class="boundary",
            note=(
                "the knife edge: the tangent is singular at the solution itself. Any "
                "of the three outcomes is honest; silently reporting a number without "
                "saying the tangent was singular is not"
            ),
        )
    )

    # --- boundary: a load so small the convergence test operates on nothing
    cases.append(
        Case(
            name="E02_boundary_zero_load",
            layer="modelling",
            root_cause="degenerate_zero_load",
            detectable_by="none_expected",
            expected=[CONVERGED_VERIFIED],
            build=lambda: (_shallow(1.0, 0.10, 1.0e-4, 0.0), opts(n_steps=5), {}),
            repair_should_help=False,
            injection="a reference load of exactly zero",
            test_class="boundary",
            note=(
                "the residual test divides by max(force, 1 N) precisely so this case "
                "does not produce 0/0. The answer is trivially zero displacement; the "
                "test is that the machinery survives a degenerate input rather than "
                "raising or looping"
            ),
        )
    )

    # --- boundary: the pair that brackets the limit point ------------------
    # A boundary test that sits only *on* the boundary shows the point is special,
    # not that the system can tell which side of it a case is on. The informative
    # comparison is one either side: just below must converge and verify, just
    # above must fail and be recognised as having failed. A one-percent margin is
    # six orders of magnitude outside the solver tolerance (1e-10) and far outside
    # the uncertainty in the measured limit load (7963.16 N), so neither case is a
    # coin flip that could make the suite flaky.
    limit = 7963.16
    cases.append(
        Case(
            name="E00_boundary_just_below_limit",
            layer="modelling",
            root_cause="load_just_below_limit_point",
            detectable_by="none_expected",
            test_class="boundary",
            expected=[CONVERGED_VERIFIED],
            build=lambda: (
                _shallow(1.0, 0.10, 1.0e-4, limit * 0.99),
                opts(n_steps=20),
                {},
            ),
            repair_should_help=False,
            injection=f"{limit * 0.99:,.1f} N, one percent below the measured limit load",
            note=(
                "equilibrium exists and is reachable, so this must converge and verify. "
                "A system that flags it is crying wolf near the edge"
            ),
        )
    )
    cases.append(
        Case(
            name="E03_boundary_just_above_limit",
            layer="modelling",
            root_cause="load_just_above_limit_point",
            detectable_by="diagnoser",
            test_class="boundary",
            expected=[LIMIT_POINT, CONVERGED_UNVERIFIED, DIVERGENCE, INCREMENT_EXHAUSTED],
            build=lambda: (
                _shallow(1.0, 0.10, 1.0e-4, limit * 1.01),
                opts(n_steps=20),
                {},
            ),
            # Past the limit point no equilibrium exists at all, so a change of
            # control variable has nothing to find. Where load control fails
            # honestly the right answer is to report the limit load -- which E01
            # and A01 already establish -- not to chase a solution that is not
            # there.
            repair_should_help=False,
            injection=f"{limit * 1.01:,.1f} N, one percent above the measured limit load",
            note=(
                "no equilibrium exists at this load, so a recognised failure is the "
                "honest outcome. Reporting a converged answer here would be the single "
                "most dangerous thing this system could do"
            ),
        )
    )

    return cases


def exact_apex_force(
    downward: float,
    half_span: float = 1.0,
    rise: float = 0.1,
    area: float = 1.0e-4,
    modulus: float = E_STEEL,
) -> float:
    """Closed-form downward apex force of the shallow two-bar truss.

    Textbook kinematics with a Green-Lagrange strain measure: no finite element
    anywhere in it. That independence is the whole point -- the four verification
    gates all either reuse the solver's own assembly or re-run the same code, so
    they can confirm a solution is self-consistent but never that the formulation
    is right. Only an outside calculation can do that.
    """
    l0 = math.hypot(half_span, rise)
    denominator = 2.0 * (half_span**2 + rise**2)
    strain = downward * (downward - 2.0 * rise) / denominator
    return (
        2.0
        * modulus
        * area
        * l0
        * strain
        * (downward - rise)
        / (half_span**2 + rise**2)
    )


def layer_reference() -> list[Case]:
    """Normal cases whose answer is known independently of the solver.

    These exist because of a gap a reader of this library pointed out: every other
    "normal" case shows that the solver converges and that its own checks accept
    the result, which is a statement about the solver's opinion of itself. None of
    them shows the number is *right*. A library that can only test self-consistency
    is testing the wrong thing, and on a project whose entire claim is "this answer
    can be trusted", that is the one gap worth closing.

    Displacement control is prescribed to a series of apex drops, and the force the
    solver reports at each is compared against the closed form. Agreement to 1e-9
    relative is a demanding bar: it would fail immediately if the strain measure,
    the tangent, or the stress recovery were wrong.
    """
    cases: list[Case] = []
    for index, drop in enumerate((0.02, 0.08, 0.15), start=1):
        cases.append(
            Case(
                name=f"R0{index}_reference_apex_force_at_{drop:.2f}m",
                layer="solver",
                root_cause="analytical_agreement",
                detectable_by="none_expected",
                test_class="normal",
                expected=[CONVERGED_VERIFIED],
                build=lambda v=drop: (
                    _shallow(1.0, 0.10, 1.0e-4, 20_000.0),
                    SolverOptions(
                        control="displacement",
                        control_dof=5,
                        target_displacement=-v,
                        n_steps=40,
                        tol=1e-10,
                        max_iter=40,
                    ),
                    {},
                ),
                repair_should_help=False,
                injection=f"displacement control to an apex drop of {drop} m",
                analytical=lambda result, v=drop: (
                    result.load_factor * 20_000.0,
                    exact_apex_force(v),
                ),
                analytical_quantity="apex force [N]",
                note=(
                    "the force at a prescribed apex drop, against a closed form that "
                    "contains no finite element: the only check here that can detect a "
                    "wrong formulation rather than an inconsistent one"
                ),
            )
        )
    return cases


def build_cases() -> list[Case]:
    """Every case, in a stable order."""
    return layer_a() + layer_nominal_and_boundary() + layer_reference() + layer_b()


# ---------------------------------------------------------------------------
# Running them
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    name: str
    layer: str
    root_cause: str
    observed: str
    converged: bool
    verdict: str | None
    diagnosis: str | None
    diagnosis_summary: str
    repair_helped: bool | None
    matched: bool
    detail: dict[str, Any] = field(default_factory=dict)
    # Filled in by run_case once the model checker has also had its say.
    detectable_by: str = "diagnoser"
    test_class: str = "failure"      # normal | boundary | failure
    model_check_verdict: str = "not_run"
    model_check_findings: list[str] = field(default_factory=list)
    caught_by: list[str] = field(default_factory=list)
    as_expected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "layer": self.layer,
            "root_cause": self.root_cause,
            "observed": self.observed,
            "converged": self.converged,
            "verdict": self.verdict,
            "diagnosis": self.diagnosis,
            "diagnosis_summary": self.diagnosis_summary,
            "repair_helped": self.repair_helped,
            "matched": self.matched,
            "detectable_by": self.detectable_by,
            "test_class": self.test_class,
            "model_check_verdict": self.model_check_verdict,
            "model_check_findings": list(self.model_check_findings),
            "caught_by": list(self.caught_by),
            "as_expected": self.as_expected,
            **self.detail,
        }


def _analytical_agreement(case: Case, result: SolveResult) -> dict[str, Any] | None:
    """Compare the solver's answer against the case's closed form, if it has one."""
    if case.analytical is None:
        return None
    try:
        computed, exact = case.analytical(result)
    except Exception as exc:  # noqa: BLE001
        return {
            "quantity": case.analytical_quantity,
            "passed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    scale = max(abs(exact), 1e-12)
    relative = abs(computed - exact) / scale
    return {
        "quantity": case.analytical_quantity,
        "computed": computed,
        "closed_form": exact,
        "relative_error": relative,
        "tolerance": case.analytical_tolerance,
        "passed": relative <= case.analytical_tolerance,
    }


def _which_layers_caught(
    result: CaseResult, model_verdict: str
) -> list[str]:
    """Name every subsystem that flagged this case.  Empty means nothing did."""
    caught: list[str] = []
    if result.diagnosis and result.diagnosis not in ("converged", "converged_verified"):
        caught.append("diagnoser")
    if result.verdict is not None and result.verdict != "verified":
        caught.append("verification")
    if model_verdict in ("ill_posed", "suspicious", "rejected_at_construction"):
        caught.append("model_check")
    return caught


def run_case(case: Case) -> CaseResult:
    """Solve one case, classify the outcome, and see whether it matches.

    Also runs the model checker, because "did anything notice?" is the question
    the library exists to answer, and three separate subsystems can notice.
    """
    result = _solve_case(case)

    try:
        model, _, _ = case.build()
        from .checkmodel import check_model

        report = check_model(model)
        result.model_check_verdict = report.verdict
        result.model_check_findings = [f.check for f in report.failures()]
    except Exception as exc:  # noqa: BLE001
        result.model_check_verdict = "rejected_at_construction"
        result.model_check_findings = [f"{type(exc).__name__}: {exc}"]

    result.detectable_by = case.detectable_by
    result.test_class = case.test_class
    result.caught_by = _which_layers_caught(result, result.model_check_verdict)

    # A case is "as expected" if the subsystems behaved the way this case says
    # they should: detected when something could detect it; quiet when nothing
    # could, or when it is a positive control with nothing wrong to find. A case
    # carrying a closed form must also actually agree with it -- converging and
    # passing the internal gates is not enough when an outside answer exists.
    agreement = result.detail.get("analytical")
    agrees = agreement is None or bool(agreement.get("passed"))
    if case.detectable_by in ("intent_only", "none_expected"):
        result.as_expected = not result.caught_by and agrees
    else:
        result.as_expected = bool(result.caught_by) and agrees

    return result


def _solve_case(case: Case) -> CaseResult:
    """Solve one case and classify the raw outcome, before the model check."""
    try:
        model, options, _ = case.build()
    except Exception as exc:  # noqa: BLE001 - validation rejections are a result
        return CaseResult(
            name=case.name,
            layer=case.layer,
            root_cause=case.root_cause,
            observed=MODEL_REJECTED,
            converged=False,
            verdict=None,
            diagnosis=None,
            diagnosis_summary=f"model rejected at construction: {type(exc).__name__}: {exc}",
            repair_helped=None,
            matched=MODEL_REJECTED in case.expected,
            detail={"rejected": True},
        )

    result = solve(model, options)

    if result.converged:
        report = verify(model, result)
        observed = CONVERGED_VERIFIED if report.verdict == "verified" else CONVERGED_UNVERIFIED
        diagnosis_kind = BRANCH_JUMP if report.verdict != "verified" else None
        summary = (
            "converged and verified"
            if report.verdict == "verified"
            else f"converged but verification verdict is {report.verdict}"
        )
        detail: dict[str, Any] = {"checks_failed": [c.name for c in report.failures()]}
        agreement = _analytical_agreement(case, result)
        if agreement is not None:
            detail["analytical"] = agreement
            if not agreement["passed"]:
                summary += (
                    f"; DISAGREES with the closed form by "
                    f"{agreement['relative_error']:.3e} relative"
                )
        return CaseResult(
            name=case.name,
            layer=case.layer,
            root_cause=case.root_cause,
            observed=observed,
            converged=True,
            verdict=report.verdict,
            diagnosis=diagnosis_kind,
            diagnosis_summary=summary,
            repair_helped=None,
            matched=observed in case.expected,
            detail=detail,
        )

    diagnosis = diagnose(model, result)
    outcome = repair(model, options)
    return CaseResult(
        name=case.name,
        layer=case.layer,
        root_cause=case.root_cause,
        observed=diagnosis.kind,
        converged=False,
        verdict=None,
        diagnosis=diagnosis.kind,
        diagnosis_summary=diagnosis.summary,
        repair_helped=outcome.solved,
        matched=diagnosis.kind in case.expected,
        detail={
            "solver_failure": result.failure,
            "accepted_increments": len(result.steps),
            "rejected_increments": len(result.failures),
            "repair_strategy": outcome.attempts[-1].strategy if outcome.attempts else None,
            "repair_should_help": case.repair_should_help,
        },
    )


def confusion_matrix(results: list[CaseResult]) -> dict[str, dict[str, int]]:
    """true label -> observed label -> count."""
    matrix: dict[str, dict[str, int]] = {}
    for r in results:
        matrix.setdefault(r.root_cause, {})
        matrix[r.root_cause][r.observed] = matrix[r.root_cause].get(r.observed, 0) + 1
    return matrix


def summarise(results: list[CaseResult]) -> dict[str, Any]:
    matched = sum(1 for r in results if r.matched)
    by_layer: dict[str, list[CaseResult]] = {}
    for r in results:
        by_layer.setdefault(r.layer, []).append(r)

    # The question that decides whether an agent earns its place: on cases the
    # rule table was never written for, can a control switch rescue anything?
    layer_b_helped = sum(1 for r in by_layer.get("modelling", []) if r.repair_helped)

    detectable = [r for r in results if r.detectable_by not in ("intent_only", "none_expected")]
    intent_only = [r for r in results if r.detectable_by == "intent_only"]
    controls = [r for r in results if r.detectable_by == "none_expected"]
    caught = [r for r in detectable if r.caught_by]

    # Repair is only expected to act where the first solve actually failed: if it
    # converged, verification is what caught the problem and the escalation has
    # nothing to do. Counting that as a mismatch would be a metric artefact.
    repair_mismatch = [
        r.name
        for r in results
        if not r.converged and bool(r.repair_helped) != bool(r.detail.get("repair_should_help"))
    ]

    # Only cases where an expectation is meaningful count towards this. An
    # intent-only error has nothing to expect -- nothing can detect it -- so
    # scoring it would make a documented limitation look like a failure, which is
    # the opposite of what the library is for.
    meaningful = [r for r in results if r.detectable_by != "intent_only"]

    return {
        # The three questions, kept apart on purpose. Folding "how much does the
        # system catch" into a single accuracy figure would sound authoritative
        # and mean nothing -- which is the failure this project exists to name.
        "total_cases": len(results),
        "detectable_errors": len(detectable),
        "detected": len(caught),
        "detection_rate": (len(caught) / len(detectable)) if detectable else 0.0,
        "missed": [r.name for r in detectable if not r.caught_by],
        "undetectable_by_design": len(intent_only),
        "undetectable_cases": [r.name for r in intent_only],
        "unexpectedly_detected_anyway": [r.name for r in intent_only if r.caught_by],
        "positive_controls": len(controls),
        "controls_clean": len([r for r in controls if not r.caught_by]),
        "controls_false_alarm": [r.name for r in controls if r.caught_by],
        "repair_behaviour_correct": len(results) - len(repair_mismatch),
        "repair_mismatch": repair_mismatch,
        "as_expected": sum(1 for r in meaningful if r.as_expected),
        "as_expected_of": len(meaningful),
        "by_expected_detector": dict(Counter(r.detectable_by for r in results)),
        "by_layer": {
            layer: {
                "total": len(rs),
                "matched": sum(1 for r in rs if r.matched),
                "repair_rescued": sum(1 for r in rs if r.repair_helped),
            }
            for layer, rs in by_layer.items()
        },
        "observed_label_counts": dict(Counter(r.observed for r in results)),
        "legacy_matched": matched,
    }


def run_all(verbose: bool = False) -> dict[str, Any]:
    """Run every case and return the rows, the confusion matrix and the summary.

    Single source of truth: the CLI, the AGH tool and the plotting script all read
    this, so the numbers they report cannot drift apart.  They did once -- the CLI
    returned one summary shape and the tool another, and the AGH tool read fields
    that were not there.  One shape, one place.
    """
    cases = build_cases()
    results: list[CaseResult] = []
    for case in cases:
        r = run_case(case)
        results.append(r)
        if verbose:
            mark = "ok  " if r.as_expected else "MISS"
            caught = ",".join(r.caught_by) or "-- nothing --"
            print(
                f"[{mark}] {r.name:<34} true={r.root_cause:<28} "
                f"observed={r.observed:<24} caught by {caught}"
            )
    return {
        "cases": [r.to_dict() for r in results],
        "confusion": confusion_matrix(results),
        "summary": summarise(results),
    }
