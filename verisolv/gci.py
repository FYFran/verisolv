"""Grid Convergence Index for load-increment refinement (Richardson extrapolation).

This module quantifies the *discretisation* error of a scalar quantity of
interest (QoI) by re-solving the same analysis at three fixed, geometrically
spaced increment sizes.  It follows the classical Richardson / GCI recipe
(Roache, Ch. 4; ASME V&V 20, solution verification).

Conventions: the three samples are ordered **coarsest to finest** as
``f1`` (coarsest), ``f2`` (medium), ``f3`` (finest), taken at increment
sizes h1 = r^2 * h, h2 = r * h, h3 = h.  With a fixed refinement ratio r
and a convergent sequence f_i = f* + C * h_i^p, the observed order is

* observed order   p  = ln((f2 - f1) / (f3 - f2)) / ln(r)

(the coarse-to-fine increment ratio |f2-f1| / |f3-f2| equals r^p, so a
convergent sequence with shrinking increments yields a **positive** p; a
sequence whose increments *grow* from coarse to fine yields a negative p
and is rejected, not extrapolated), together with

* Richardson value  f* = f3 + (f3 - f2) / (r^p - 1)
* GCI_coarse      = Fs * |(f2 - f1) / (r^p - 1)|,   Fs = 1.25
* GCI_fine        = GCI_coarse / r^p
* GCI_asymptotic  = Fs * |(f3 - f2) / (r^p - 1)|
* consistency ratio  GCI_32 * r^p / GCI_21 (relative form, Celik et al. 2008),
  GCI_21 = Fs * |f2 - f1| / (|f1| * (r^p - 1)),  GCI_32 = Fs * |f3 - f2| / (|f2| * (r^p - 1))

Honesty constraints (kept in the module and in the reported detail strings
so no caller can over-read them):

* This refines the **load increments**, not a spatial mesh.  verisolv models
  are given; the only discretisation parameter available is the number of
  Newton increments.  This is therefore a **load-increment refinement study**,
  and the numbers it produces are **error estimates under the asymptotic
  hypothesis**, not error bounds, and not a grid-convergence study.
* ``p`` is a *measured* quantity.  If the samples are not in the asymptotic
  regime the measured order is meaningless; we report it as ``conditional``
  rather than as a verdict.

The failure modes below are the known GCI traps and are handled *refusing to
extrapolate*:

* ``r`` not (nearly) constant  -> ``reject``  ("refinement ratio not fixed,
  the observed order is not stable"); no extrapolation is attempted
* non-monotone sequence         -> ``reject``; only the oscillation range is
  reported, no formula is forced onto it
* ``p`` outside the [0.5, 4] band -> ``conditional``; "may not be in the
  asymptotic regime"
* degenerate sequence (all three values essentially identical, or f3 - f2 ~ 0)
  -> ``reject``; nothing is measurable
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

# Gate verdicts, three-valued (Wilke v2 adds the half):
#   pass            the estimate is usable and in the asymptotic band
#   conditional     a number exists but is not fully dependable, it is flagged
#   reject          no usable estimate; the reason is in ``detail``
PASS = "pass"
CONDITIONAL = "conditional"
REJECT = "reject"

# Safety band for the observed order: p < 0.5 or p > 4 is treated as
# "probably not in the asymptotic regime".
P_LOW = 0.5
P_HIGH = 4.0

# Safety band for the *relative-form* consistency ratio (Celik et al. 2008),
# GCI_32 * r^p / GCI_21, each GCI relative to its own finer-grid value.
#
# Honest note, kept in the module so no caller can over-read it: when p is
# the *observed* order computed from the same three samples, the relative-
# form consistency ratio reduces algebraically to |f1| / |f2| (because
# |f2-f1|/|f3-f2| = r^p holds exactly by the definition of p).  It is a
# same-magnitude sanity check, NOT an independent asymptotic-regime test;
# with three samples and an observed order, no independent
# asymptotic-regime test is available.  The earlier absolute-form
# "asymptotic ratio" GCI_asymptotic / GCI_fine was an algebraic identity:
# under the earlier sign-inverted order formula it evaluated to r^(2p)
# (the "5.911" once reported on the real n=40/80/160 triple is exactly
# 2^(2*1.2818)), and under the corrected formula it is identically 1.  It
# carried no information beyond p and is no longer used as a gate; it is
# still reported for transparency.
ASYMPTOTIC_RATIO_BAND = (0.7, 3.0)


@dataclass
class GCIResult:
    """One QoI, at a single resolution, with a GCI estimate (or a refusal).

    Field convention: f1 is the **coarsest** sample, f3 the **finest**.
    """

    quantity: str
    status: str                     # pass | conditional | reject | not_run
    detail: str
    # The three coarsest-to-finest samples (f1, f2, f3); absent when rejected.
    f1: float | None = None
    f2: float | None = None
    f3: float | None = None
    r: float | None = None
    p: float | None = None
    f_exact: float | None = None    # Richardson extrapolated value
    gci_fine_pct: float | None = None
    gci_coarse_pct: float | None = None
    gci_asymptotic_pct: float | None = None
    asymptotic_ratio: float | None = None
    consistency_ratio: float | None = None  # relative form, Celik et al. 2008
    oscillation_range: tuple[float, float] | None = None  # on non-monotone refusal
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "quantity": self.quantity,
            "status": self.status,
            "detail": self.detail,
        }
        for name in (
            "f1", "f2", "f3", "r", "p", "f_exact",
            "gci_fine_pct", "gci_coarse_pct", "gci_asymptotic_pct",
            "asymptotic_ratio", "consistency_ratio",
        ):
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        if self.oscillation_range is not None:
            out["oscillation_range"] = list(self.oscillation_range)
        out["evidence"] = dict(self.evidence)
        return out


def _refuse(quantity: str, status: str, detail: str, **extra: Any) -> GCIResult:
    return GCIResult(quantity=quantity, status=status, detail=detail, **extra)


def check_refinement_ratio(steps: Sequence[float], r_expected: float, tol_r: float = 0.05) -> GCIResult | None:
    """Return a refusal when the actual refinement ratio is not (nearly) r.

    ``steps`` is the increment count at each sample, ordered coarsest to
    finest, so the ratio of the increment *sizes* (1/steps) must be roughly r
    on each leg.
    """
    if len(steps) != 3:
        return _refuse(
            "gci",
            REJECT,
            f"expected three samples, got {len(steps)}",
            r=r_expected,
            evidence={"fail_reason": "not_three_samples"},
        )
    h = [1.0 / s for s in steps]  # increment size, coarsest to finest
    legs = [h[i] / h[i + 1] for i in range(len(h) - 1)]
    worst = max(abs(ll / r_expected - 1.0) for ll in legs)
    if worst > tol_r:
        return _refuse(
            "gci",
            REJECT,
            (
                f"refinement ratio is not fixed: expected {r_expected:.3f} between the increment "
                f"sizes on successive legs, measured {legs[0]:.4f} and {legs[1]:.4f}; "
                "the observed order is not stable, so no extrapolation is attempted"
            ),
            r=r_expected,
            evidence={"fail_reason": "r_not_constant", "legs": legs, "worst_dev": worst},
        )
    return None


def compute_gci(
    values: Sequence[float],
    *,
    quantity: str = "quantity",
    r: float = 1.3,
    fs: float = 1.25,
    p_low: float = P_LOW,
    p_high: float = P_HIGH,
    asymptotic_ratio_band: tuple[float, float] = ASYMPTOTIC_RATIO_BAND,
    degenerate_eps: float = 1e-12,
) -> GCIResult:
    """Run the Richardson / GCI estimate on three coarsest-to-finest samples.

    ``values`` must be ordered coarsest -> finest (f1, f2, f3).  This function
    assumes the three samples were actually taken at geometric increment sizes
    with the fixed ratio ``r``; the caller passes the step counts through
    :func:`check_refinement_ratio` first (see :func:`evaluate_quantity_over_steps`).
    """
    name = quantity

    f1, f2, f3 = (float(v) for v in values)

    # degenerate: the two finest samples agree to within the noise floor; the
    # discretisation error is smaller than what is measurable, so no GCI.
    #
    # This refusal is *good news reported honestly*: when two consecutive
    # refinements are indistinguishable, the discretisation error is already
    # below the measurable threshold, which is a stronger statement than any
    # GCI band could make.  It still blocks signoff, because signoff requires
    # a quantified band, and "below the threshold" names a limit on the
    # measurement, not a limit on the error.
    if abs(f3 - f2) <= degenerate_eps * max(abs(f1), abs(f2), abs(f3), 1e-300):
        return _refuse(
            name,
            REJECT,
            (
                "the two finest samples agree to within "
                f"{degenerate_eps:.1e} (sequence is degenerate); no discretisation error "
                "is measurable at this resolution, so no GCI can be formed"
            ),
            f1=f1, f2=f2, f3=f3, r=r,
            evidence={"fail_reason": "degenerate_sequence", "values": [f1, f2, f3]},
        )

    # monotone convergence: the sequence must march toward its limit in one
    # direction.  Non-monotone samples are oscillating, and the Richardson
    # recipe does not apply to an oscillation: report the range, refuse the
    # extrapolation.
    d_fine = f3 - f2
    d_coarse = f2 - f1
    if d_fine * d_coarse < 0.0:
        lo, hi = min(f1, f2, f3), max(f1, f2, f3)
        return _refuse(
            name,
            REJECT,
            (
                "the sequence is not monotone (f1, f2, f3 = "
                f"{f1:.6e}, {f2:.6e}, {f3:.6e} as coarsest to finest); the Richardson "
                "recipe does not apply to oscillating samples.  No extrapolation is "
                "attempted; the reported range brackets the oscillation, it is not an "
                "error band"
            ),
            f1=f1, f2=f2, f3=f3, r=r,
            oscillation_range=(lo, hi),
            evidence={"fail_reason": "non_monotone", "values": [f1, f2, f3]},
        )

    ratio_arg = (f2 - f1) / (f3 - f2)
    if ratio_arg <= 0.0:
        return _refuse(
            name,
            REJECT,
            "the error-difference ratio is not positive; the Richardson recipe "
            "does not apply, no extrapolation attempted",
            f1=f1, f2=f2, f3=f3, r=r,
            evidence={"fail_reason": "negative_ratio_arg", "values": [f1, f2, f3]},
        )

    p = math.log(ratio_arg) / math.log(r)
    # When p is non-positive the samples are not marching toward their limit
    # in the direction the recipe assumes (the increments are growing, not
    # shrinking, from coarsest to finest); that is a signature of
    # oscillation or a non-asymptotic sequence, not a usable estimate.  No
    # GCI is reported; the samples are reported with the raw numbers so the
    # caller can see exactly what happened.
    if p <= 0.0:
        return _refuse(
            name,
            REJECT,
            (
                f"the measured order is p = {p:.3f} (non-positive); the samples do not "
                "march monotonically toward a limit, so the Richardson recipe is not "
                "usable and no GCI is reported"
            ),
            f1=f1, f2=f2, f3=f3, r=r, p=p,
            evidence={"fail_reason": "nonpositive_p", "values": [f1, f2, f3]},
        )
    rp = r ** p

    denom = rp - 1.0
    f_exact = f3 + (f3 - f2) / denom
    gci_coarse = fs * abs((f2 - f1) / denom)
    gci_fine = gci_coarse / rp
    gci_asymptotic = fs * abs((f3 - f2) / denom)
    # relative form, guarded for zero / near-zero values
    scale = max(abs(f1), abs(f2), abs(f3), 1.0)
    gci_fine_pct = 100.0 * gci_fine / scale
    gci_coarse_pct = 100.0 * gci_coarse / scale
    gci_asymptotic_pct = 100.0 * gci_asymptotic / scale

    # Legacy absolute-form ratio, kept for transparency only.  With the
    # corrected observed-order formula it is an algebraic identity: because
    # p is defined from the same three samples, |f2-f1| / |f3-f2| = r^p
    # holds exactly, so gci_asymptotic == gci_fine exactly and this ratio is
    # identically 1.  (Under the earlier sign-inverted order formula it
    # evaluated to r^(2p) -- that is the "5.911" once reported on the real
    # n=40/80/160 triple, which is exactly 2^(2*1.2818).)  Either way it
    # carries no information beyond p and is NOT a gate; the gate below
    # uses the literature's relative-form consistency ratio instead.
    asym_ratio = gci_asymptotic / gci_fine if gci_fine > 0 else float("inf")

    # Consistency ratio in the literature's relative form (Roache 1994;
    # Celik, Pirro et al. 2008, ASME J. Fluids Eng.):
    #   GCI_21 = Fs * |f2 - f1| / (|f1| * (r^p - 1))
    #   GCI_32 = Fs * |f3 - f2| / (|f2| * (r^p - 1))
    #   consistency = GCI_32 * r^p / GCI_21
    # For an *observed* p (computed from these same three samples) this
    # reduces algebraically to |f1| / |f2|: it is a same-magnitude sanity
    # check, not an independent asymptotic-regime test (see module header).
    consistency_ratio = None
    if abs(f1) > 1e-300 and abs(f2) > 1e-300:
        gci_21_rel = fs * abs(f2 - f1) / (abs(f1) * denom) if denom > 0 else None
        gci_32_rel = fs * abs(f3 - f2) / (abs(f2) * denom) if denom > 0 else None
        if gci_21_rel and gci_32_rel:
            consistency_ratio = gci_32_rel * rp / gci_21_rel

    if consistency_ratio is not None:
        base_detail = (
            f"observed order p = {p:.3f}; Richardson value {f_exact:.6e}; "
            f"GCI (fine) = {gci_fine_pct:.3f} % of the sample scale; "
            f"consistency ratio (relative form) = {consistency_ratio:.3f}"
        )
    else:
        base_detail = (
            f"observed order p = {p:.3f}; Richardson value {f_exact:.6e}; "
            f"GCI (fine) = {gci_fine_pct:.3f} % of the sample scale"
        )

    base = GCIResult(
        quantity=name,
        status=PASS,
        detail=base_detail,
        f1=f1, f2=f2, f3=f3, r=r, p=p, f_exact=f_exact,
        gci_fine_pct=gci_fine_pct, gci_coarse_pct=gci_coarse_pct,
        gci_asymptotic_pct=gci_asymptotic_pct, asymptotic_ratio=asym_ratio,
        consistency_ratio=consistency_ratio,
        evidence={
            "fs": fs,
            "values_coarsest_to_finest": [f1, f2, f3],
            "note": (
                "GCI is a discretisation-error *estimate* under the asymptotic hypothesis, "
                "not an error bound; this is a load-increment refinement study, not a "
                "spatial grid-convergence study"
            ),
            "asymptotic_ratio_note": (
                "asymptotic_ratio (legacy, absolute form GCI_asymptotic/GCI_fine) is an "
                "algebraic identity for an observed p -- 1 with the corrected order "
                "formula, r^(2p) under the earlier sign-inverted one -- and carries no "
                "information beyond p. It is reported for transparency only and is not a "
                "gate. consistency_ratio is the relative-form check of Roache/Celik et "
                "al. 2008, which reduces to |f1|/|f2| for an observed p: a same-magnitude "
                "sanity check, not an independent asymptotic-regime test."
            ),
        },
    )

    # conditional flags: the number exists but must not be read as dependable
    if p < p_low or p > p_high:
        base.status = CONDITIONAL
        base.detail += (
            f"  [conditional] measured p = {p:.2f} is outside the "
            f"[{p_low}, {p_high}] band; the samples may not be in the asymptotic regime"
        )
        base.evidence["fail_reason"] = "p_out_of_band"
    elif consistency_ratio is not None and not (
        asymptotic_ratio_band[0] <= consistency_ratio <= asymptotic_ratio_band[1]
    ):
        base.status = CONDITIONAL
        base.detail += (
            f"  [conditional] consistency ratio = {consistency_ratio:.3f} is outside "
            f"[{asymptotic_ratio_band[0]}, {asymptotic_ratio_band[1]}]; the samples may "
            "not be in the asymptotic regime"
        )
        base.evidence["fail_reason"] = "not_in_asymptotic_regime"

    return base


def evaluate_quantity_over_steps(
    model,
    options_template,
    evaluator: Callable[[Any], float],
    *,
    n_steps: int = 20,
    r: float = 1.3,
    quantity: str = "quantity",
    solve_kwargs: dict[str, Any] | None = None,
) -> tuple[list[float], list[float], GCIResult]:
    """Solve three times at fixed geometric increments and compute the GCI.

    ``n_steps`` is the coarsest sample's step count; the three samples are
    taken at ``n_steps`` (coarsest, f1), ``n_steps * r`` (f2) and
    ``n_steps * r**2`` (finest, f3).  ``evaluator(result)`` maps a SolveResult
    to the scalar QoI.  Returns ``(values, steps, result)`` in coarsest-to-
    finest order.
    """
    from .solver import solve

    kwargs = dict(solve_kwargs or {})
    steps = [float(n_steps), float(n_steps) * r, float(n_steps) * r * r]
    refusal = check_refinement_ratio(steps, r)
    values: list[float] = []
    for s in steps:
        options = options_template.replace(n_steps=int(round(s)), **kwargs)
        res = solve(model, options)
        values.append(evaluator(res))

    if refusal is not None:
        return values, steps, refusal

    return values, steps, compute_gci(values, quantity=quantity, r=r)
