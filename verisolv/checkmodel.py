"""Model sanity checks -- the class of error numerical verification cannot see.

Everything in :mod:`verisolv.verify` asks "is this answer consistent with the
model it came from?".  That question is silent about whether the model was the
right one.  A load entered with the wrong sign, a unit slip, a material constant
typed a thousand times too large: all of them produce answers that are converged,
self-consistent, reproducible, and about the wrong problem.

Numerical verification is *structurally* blind to this, not merely weak at it. No
amount of residual checking can detect that the input was mis-typed, because
nothing in the arithmetic is wrong.

This module asks the complementary question -- "is this model well-posed and
plausible?" -- using only deterministic checks over the model definition.  It is
deliberately separate from the solver: it never runs an analysis, so it can be
consulted when the analysis has already failed, and its verdicts are independent
of whatever the solver concluded.

What it can and cannot do is worth stating plainly.  It detects ill-posedness
(mechanisms, non-positive properties) with certainty, because those are
structural facts.  For the plausibility checks it produces *suspicions with
reasons*, not verdicts: a stiffness a thousand times out of family is a reason to
look, not proof of a typo.  Reporting it as proof would be the same overreach the
rest of this project exists to avoid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .fem import Model, assemble

CRITICAL = "critical"
MAJOR = "major"
MINOR = "minor"


@dataclass
class Finding:
    check: str
    passed: bool
    severity: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "passed": self.passed,
            "severity": self.severity,
            "detail": self.detail,
            "evidence": self.evidence,
        }


@dataclass
class ModelReport:
    findings: list[Finding]
    verdict: str
    rigid_body_modes: int
    static_indeterminacy: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "rigid_body_modes": self.rigid_body_modes,
            "static_indeterminacy": self.static_indeterminacy,
            "findings": [f.to_dict() for f in self.findings],
        }

    def failures(self) -> list[Finding]:
        return [f for f in self.findings if not f.passed]


def _verdict(findings: list[Finding]) -> str:
    if any(not f.passed and f.severity == CRITICAL for f in findings):
        return "ill_posed"
    if any(not f.passed for f in findings):
        return "suspicious"
    return "ok"


# ---------------------------------------------------------------------------
# Structural checks -- these are certain, not heuristic
# ---------------------------------------------------------------------------


def check_degrees_of_freedom(model: Model) -> tuple[Finding, int]:
    """Count restraints against the rigid-body modes a plane truss can have.

    A free plane truss has two translations and one rotation available, so it
    needs at least three independent restraints and no mechanism.  The count
    `m + r - 2j` gives the static indeterminacy and is the classical first look,
    but a non-negative count does *not* prove stability -- restraints can be
    arranged so that a mode survives anyway -- which is why the rank check below
    is the one that decides.
    """
    m = len(model.bars)
    j = model.node_count
    r = int(len(model.constrained_dofs()))
    indeterminacy = m + r - 2 * j

    needs = 3
    if r < needs:
        return (
            Finding(
                "degrees_of_freedom",
                False,
                CRITICAL,
                (
                    f"only {r} restrained degree(s) of freedom: a plane truss needs at "
                    f"least {needs} independent restraints, so rigid-body motion remains possible"
                ),
                {"bars": m, "nodes": j, "restraints": r, "static_indeterminacy": indeterminacy},
            ),
            indeterminacy,
        )
    return (
        Finding(
            "degrees_of_freedom",
            True,
            CRITICAL,
            (
                f"{r} restraints for {j} nodes: statically "
                f"{'indeterminate' if indeterminacy > 0 else 'determinate' if indeterminacy == 0 else 'under-determined'} "
                f"(m + r - 2j = {indeterminacy})"
            ),
            {"bars": m, "nodes": j, "restraints": r, "static_indeterminacy": indeterminacy},
        ),
        indeterminacy,
    )


def check_rigid_body_modes(model: Model, threshold: float = 1e-12) -> tuple[Finding, int]:
    """Count zero-stiffness modes of the free-free tangent at zero load.

    This is the check that actually catches a mechanism.  A structure that can
    move without straining any member produces a singular stiffness matrix
    *before any load is applied* -- and that is precisely what separates it from
    a limit point, where the tangent only becomes singular once the structure has
    been pushed far enough to lose stability.
    """
    _, k_mat, _ = assemble(model, np.zeros(model.dof_count))
    free = model.free_dofs()
    if free.size == 0:
        return (
            Finding("rigid_body_modes", True, CRITICAL, "no free degrees of freedom", {}),
            0,
        )

    k_free = k_mat[np.ix_(free, free)]
    singular_values = np.linalg.svd(k_free, compute_uv=False)
    largest = float(singular_values[0])
    if largest <= 0.0:
        modes = int(free.size)
    else:
        modes = int(np.sum(singular_values / largest < threshold))

    if modes > 0:
        return (
            Finding(
                "rigid_body_modes",
                False,
                CRITICAL,
                (
                    f"{modes} zero-stiffness mode(s) at zero load: the structure is a "
                    f"mechanism. It is free to move without straining, so no load can be "
                    f"carried and no change of increment or control variable will help -- "
                    f"a restraint is missing"
                ),
                {
                    "modes": modes,
                    "free_dofs": int(free.size),
                    "smallest_singular_value_ratio": float(singular_values[-1] / largest)
                    if largest > 0
                    else 0.0,
                },
            ),
            modes,
        )
    return (
        Finding(
            "rigid_body_modes",
            True,
            CRITICAL,
            "no zero-stiffness mode: the structure is stable at zero load",
            {
                "smallest_singular_value_ratio": float(singular_values[-1] / largest),
                "condition_number": float(largest / singular_values[-1]),
            },
        ),
        0,
    )


def check_member_properties(model: Model, min_length: float = 1e-9) -> Finding:
    """Every member must have a positive length, area, modulus and yield stress."""
    problems: list[str] = []
    for index, bar in enumerate(model.bars):
        length = bar.length(model.coords)
        if length <= min_length:
            problems.append(f"bar {index}: zero or near-zero length ({length:.3e} m)")
        if bar.area <= 0.0:
            problems.append(f"bar {index}: non-positive area ({bar.area:.3e} m2)")
        if bar.modulus <= 0.0:
            problems.append(f"bar {index}: non-positive modulus ({bar.modulus:.3e} Pa)")
        if bar.yield_stress <= 0.0:
            problems.append(f"bar {index}: non-positive yield stress ({bar.yield_stress:.3e} Pa)")

    passed = not problems
    return Finding(
        "member_properties",
        passed,
        CRITICAL,
        "all members have positive length, area, modulus and yield stress"
        if passed
        else f"{len(problems)} invalid member(s): " + "; ".join(problems[:5]),
        {"problems": problems},
    )


# ---------------------------------------------------------------------------
# Plausibility checks -- suspicions with reasons, not verdicts
# ---------------------------------------------------------------------------


def check_material_plausibility(model: Model) -> Finding:
    """Are the material constants inside the range real solids occupy?

    A typo in a modulus does not make the arithmetic wrong, so nothing in the
    solver or the verifier can see it -- the answer is simply computed from the
    wrong material.  It is, however, visible here: no structural material has a
    Young's modulus of 210 TPa, and a density of 7.85 kg/m3 is a gas.

    The bands are wide on purpose.  They are meant to catch orders-of-magnitude
    slips, not to adjudicate unusual materials.
    """
    # Wide bounds for any solid: polymer foams sit near 1 MPa, diamond near 1 TPa.
    E_BAND = (1.0e6, 1.0e12)
    RHO_BAND = (10.0, 25_000.0)
    FY_BAND = (1.0e5, 5.0e9)

    problems: list[str] = []
    for index, bar in enumerate(model.bars):
        if not (E_BAND[0] <= bar.modulus <= E_BAND[1]):
            problems.append(
                f"bar {index}: Young's modulus {bar.modulus:.4g} Pa is outside the range any "
                f"solid occupies ({E_BAND[0]:.0e}-{E_BAND[1]:.0e} Pa)"
            )
        if not (RHO_BAND[0] <= bar.density <= RHO_BAND[1]):
            problems.append(
                f"bar {index}: density {bar.density:.4g} kg/m3 is outside "
                f"{RHO_BAND[0]:.0f}-{RHO_BAND[1]:.0f} kg/m3"
            )
        if not (FY_BAND[0] <= bar.yield_stress <= FY_BAND[1]):
            problems.append(
                f"bar {index}: yield stress {bar.yield_stress:.4g} Pa is outside "
                f"{FY_BAND[0]:.0e}-{FY_BAND[1]:.0e} Pa"
            )

    passed = not problems
    return Finding(
        "material_plausibility",
        passed,
        MAJOR,
        "material constants are within physically plausible bands"
        if passed
        else "; ".join(problems[:4]),
        {
            "problems": problems,
            "youngs_modulus_band_Pa": list(E_BAND),
            "density_band_kg_m3": list(RHO_BAND),
            "note": (
                "catches orders-of-magnitude slips in a material constant; the solver and "
                "the verifier are both blind to this because the arithmetic stays correct"
            ),
        },
    )


def check_scale_consistency(model: Model) -> Finding:
    """Flag loads so large that the structure would move far beyond its own span.

    These are heuristics and are reported as such.  A load a thousand times too
    large and a genuinely heavy structure look identical to this check; what it
    can say is that the resulting displacement is far outside the range in which
    a small-strain truss model means anything, which is worth a human look
    regardless of the cause.

    History (do not rewrite): this check used to estimate the displacement as
    ``max_node_load / sum(E*A/L over all bars)`` -- the sum of every bar's
    axial stiffness, not the structure's stiffness.  For the reference
    cantilever that sum is 5.0e9 N/m while the tip actually feels 5.6e6 N/m,
    off by a factor of ~890, so the check *never* fired on load-type overload:
    it stayed PASSED up through a 1000x load (the 890x underestimate hid it).
    The only load it actually caught was a stiffness collapse (material typo,
    where the sum itself falls off).  This was found by a blind diagnosis run
    and fixed on 2026-10-09: the estimate is now a *linear* solve of the
    assembled stiffness matrix against the applied load (one
    ``np.linalg.solve``, not a Newton iteration, not a path), which is exact
    in the linear regime and an *over*-estimate for large deflections -- the
    right direction for a warning.  A singular free-block (a mechanism) makes
    the linear system unsolvable; that is caught honestly as "cannot estimate"
    and is not re-reported as a FAIL here, because ``check_rigid_body_modes``
    already owns that diagnosis and this check must not double-count it.
    """
    load_vector = model.load_vector()
    load = float(np.max(np.abs(load_vector))) if load_vector.size else 0.0
    lengths = [bar.length(model.coords) for bar in model.bars]
    span = max(lengths) if lengths else 0.0

    free = model.free_dofs()
    reasons: list[str] = []
    evidence: dict[str, Any] = {
        "max_node_load_N": load,
        "characteristic_span_m": span,
        "estimate_method": "linear solve of the assembled stiffness matrix",
    }

    estimated: float | None
    if free.size == 0:
        # Nothing is free to move: the displacement is exactly zero.
        estimated = 0.0
        evidence["note"] = "no free degrees of freedom; displacement is identically zero"
    elif load == 0.0:
        estimated = 0.0
        evidence["note"] = "no load applied; displacement is identically zero"
    else:
        _, k_mat, _ = assemble(model, np.zeros(model.dof_count))
        k_free = k_mat[np.ix_(free, free)]
        f_free = load_vector[free]
        load_norm = float(np.linalg.norm(f_free))
        # A rigid-body mode makes k_free *numerically* singular: the smallest
        # singular value drops to a threshold (1e-12, matching
        # check_rigid_body_modes) relative to the largest.  Exact singularity
        # raises LinAlgError; near-singularity solves "successfully" to a
        # fake number 8e6 m huge.  Both must be treated as "cannot estimate".
        singular_values = np.linalg.svd(k_free, compute_uv=False)
        largest_sv = float(singular_values[0]) if singular_values.size else 0.0
        is_singular = (
            largest_sv == 0.0 or float(singular_values[-1] / largest_sv) < 1e-12
        )
        if is_singular:
            # Singular free-block: a rigid-body mode (check_rigid_body_modes has
            # already named it).  Do not invent a number, do not double-report.
            estimated = None
            evidence["note"] = (
                "free-block stiffness is singular (a rigid-body mode); displacement "
                "cannot be estimated.  Not re-reported here: check_rigid_body_modes "
                "owns that diagnosis"
            )
            evidence["cannot_estimate"] = True
            return Finding("scale_consistency", True, MINOR,
                          "scale cannot be estimated: the free-block stiffness matrix is singular; "
                          "a mechanism is already diagnosed by rigid_body_modes",
                          evidence)
        try:
            u_free = np.linalg.solve(k_free, f_free)
            estimated = float(np.max(np.abs(u_free)))
            evidence["linear_tip_displacement_m"] = estimated
        except np.linalg.LinAlgError:
            # Truly singular (exact zero mode): catch and report honestly.
            estimated = None
            evidence["note"] = (
                "free-block stiffness is singular (a rigid-body mode); displacement "
                "cannot be estimated.  Not re-reported here: check_rigid_body_modes "
                "owns that diagnosis"
            )
            evidence["cannot_estimate"] = True
            return Finding("scale_consistency", True, MINOR,
                          "scale cannot be estimated: the free-block stiffness matrix is singular; "
                          "a mechanism is already diagnosed by rigid_body_modes",
                          evidence)

    if estimated is not None and span > 0.0 and estimated > 0.1 * span:
        reasons.append(
            f"the applied load would move the structure about {estimated / span:.2f} of its own "
            f"span even in a *linear* analysis, far outside the range where a small-strain "
            f"model is meaningful"
        )
    if estimated is not None and estimated <= 0.0 and load > 0.0:
        reasons.append("zero estimated displacement from a non-zero load")

    passed = not reasons
    return Finding(
        "scale_consistency",
        passed,
        MINOR,
        "load and stiffness are within a plausible range of each other"
        if passed
        else "; ".join(reasons),
        evidence,
    )


def check_support_reaction_feasibility(model: Model) -> Finding:
    """A load with no restraint opposing it cannot be equilibrated."""
    applied = model.load_vector().reshape(-1, 2)
    total = applied.sum(axis=0)
    constrained = set(model.constrained_dofs().tolist())

    unsupported: list[str] = []
    for axis, name in ((0, "x"), (1, "y")):
        if abs(total[axis]) <= 0.0:
            continue
        restrained = any(2 * node + axis in constrained for node in range(model.node_count))
        if not restrained:
            unsupported.append(
                f"net {name}-load {total[axis]:.4g} N with no {name}-restraint anywhere"
            )

    passed = not unsupported
    return Finding(
        "reaction_feasibility",
        passed,
        CRITICAL,
        "every net load component has a restraint that can react it"
        if passed
        else "; ".join(unsupported),
        {"net_applied_N": total.tolist(), "restrained_dofs": sorted(constrained)},
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def check_model(model: Model) -> ModelReport:
    """Run every model check and summarise. Never runs an analysis."""
    findings: list[Finding] = []

    dof_finding, indeterminacy = check_degrees_of_freedom(model)
    findings.append(dof_finding)

    mode_finding, modes = check_rigid_body_modes(model)
    findings.append(mode_finding)

    findings.append(check_member_properties(model))
    findings.append(check_material_plausibility(model))
    findings.append(check_support_reaction_feasibility(model))
    findings.append(check_scale_consistency(model))

    return ModelReport(
        findings=findings,
        verdict=_verdict(findings),
        rigid_body_modes=modes,
        static_indeterminacy=indeterminacy,
    )
