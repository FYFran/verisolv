# 7-question pre-claim self-check

> **When to use:** before *any* result from verisolv (or any solver) is
> reported, acted on, or handed to a third party as a claim.
>
> **What it does:** forces the operator to confront, in writing, what the
> evidence actually supports — and what it does not.
>
> **How to use:** answer all seven questions. Do not proceed to report
> the result until each answer is explicit in the report. An "I'm not
> sure" is a valid answer; it means the claim level is lower than you
> thought.

---

## The seven questions

### 1. What did I actually check?

Name each gate by its `check.name` in the verification report and state
its severity. Do not say "I verified the result." Say:
> "I ran the residual gate (critical, passed), the global-equilibrium
> gate (major, passed), the path-continuity gate (major, passed), the
> step-refinement gate (major, passed), and the GCI gate (minor, rejected
> because the sequence is degenerate)."

The distinction is: **passed** vs **ran** vs **was attempted**. A gate
that did not run is not a gate that passed.

### 2. What claim level does the evidence support?

Look at `report.claim_level` (or compute it with `claim_level(report,
result)`). Do not state a stronger claim than the claim level supports.

| Claim level | You may say | You may NOT say |
|---|---|---|
| `smoke` | "The solver produced a readable result." | Anything about the result's correctness or reliability. |
| `debug` | "This result localises a symptom; use it to decide what to investigate next." | "This is the answer." "The structure can carry X kN." |
| `engineering` | "The answer is self-consistent under the stated tolerances. No error estimate is available." "The result is stable under load-increment refinement." | "The discretisation error is below X." "The answer is correct." |
| `signoff` | "The answer is self-consistent and a GCI band is available for each QoI. The GCI band is a point estimate, not a bound." | "The error is below the GCI." "The model is validated." "This result is certified." |

### 3. What does NOT hold, that the gates could not have caught?

For each gate you ran, identify the row in `EVIDENCE.md` whose "does NOT
prove" column matches. Write that row's "does NOT prove" text into the
report. This is not optional: it is the iron rule against over-claiming.

The most common gap:
- **Gates 1–4** (residual, equilibrium, continuity, step-refinement) all
  reuse the solver's own element assembly. They are self-consistency
  checks. A formulation error — wrong element, wrong material model, wrong
  boundary condition — passes all four gates and is invisible to them.
- **GCI gate** quantifies the *discretisation* error. It does not
  quantify the *model-form* error. A model that is "consistent with
  itself" (all gates pass) can still be wrong about the physics.

### 4. Is the GCI band usable, or was it refused?

If `gci.status == "reject"`:
- **Non-monotone sequence:** the Richardson recipe does not apply. No band
  is reported. The report must say so explicitly. Do not invent a band.
- **Degenerate sequence** (two finest samples agree to within 1e-12):
  the discretisation error is below the measurable threshold. No GCI can
  be formed. This is *good news reported honestly*: the answer is stable
  at that resolution, but you cannot say *how* stable.
- **p out of band [0.5, 4]:** the sequence is probably not in the
  asymptotic regime. GCI is reported as `conditional`. Flag it.

If `gci.status == "pass"` or `"conditional"`:
- State the per-QoI GCI values. A quantity that converged (GCI = 0.000%)
  is not evidence that *another* quantity converged. Report each QoI
  separately.

### 5. What model assumptions am I NOT checking?

List explicitly:
- [ ] Bar element formulation (2-node truss, no bending)
- [ ] Material model (linear elastic; no plasticity, no creep)
- [ ] Boundary conditions (prescribed displacements / prescribed loads)
- [ ] Load path (the direction and magnitude of the applied reference load)
- [ ] Units (the modulus, density, and load magnitude are all in the same
      consistent unit system)

The closed-form case and the PyNite cross-check cover *some* of these.
State which ones they cover and which ones they do not. A reversed load,
a unit slip, or a mistyped modulus will pass every gate in this tool.
Use `verisolv_checkmodel` for those: it inspects the model without running
the solver and cannot inherit its assumptions.

### 6. What would falsify this result?

A true claim states what evidence would show it is wrong. For a
`signoff` claim, the falsifier is: "if the GCI band were measured on
*independent* code and disagreed with mine by more than the GCI band
itself, my discretisation error estimate is wrong." For an `engineering`
claim, the falsifier is: "if a different solver gave an answer more than
the step-refinement tolerance away from mine, my stability claim is
wrong."

If you cannot name the falsifier, you have not stated the claim precisely
enough. Lower the claim level.

### 7. What am I NOT claiming, that I must say I'm not claiming?

This is the iron-rule self-check. Before the report is final, state
explicitly:

- I am **not** claiming the result is "correct." I am claiming it is
  "consistent under the stated tolerances" (`engineering`) or "consistent
  and quantified to within a GCI band" (`signoff`).
- I am **not** claiming the GCI band is an upper bound on the error.
  It is a point estimate with a stated confidence factor.
- I am **not** claiming that load-increment refinement is grid
  convergence. There is no grid. The "grid" here is the integration
  schedule, not the mesh.
- I am **not** claiming the model formulation is validated. The tool
  cannot distinguish a correct model from a wrong one that is
  internally consistent.

---

## Output template

Copy this block into your report and fill in every line. Do not skip a
line; "N/A" is a valid value, but only if you have thought about it.

```
Pre-claim self-check
====================

1. Gates run: [list each gate, its severity, and pass/fail/refused]
   Gates not run: [list with reason, if any]

2. Claim level supported: [smoke / debug / engineering / signoff]
   Claim level I am reporting: [same or lower]
   Reason for any downgrade: [if lower, state why]

3. What the gates do NOT prove (from EVIDENCE.md):
   - [row number]: [quote the "does NOT prove" text]
   - [row number]: [quote the "does NOT prove" text]

4. GCI band: [usable / refused / conditional]
   Per-QoI GCI values: [quantity: status, p, GCI_fine%, GCI_coarse%]
   Oscillation range (if refused): [range, not a band]

5. Model assumptions not checked: [list]
   Closed-form cross-check covers: [list]
   Closed-form cross-check does NOT cover: [list]

6. Falsifier for this claim: [one sentence]

7. What I am NOT claiming:
   - [ ] "correct" → I claim "consistent under stated tolerances"
   - [ ] "upper bound" → I claim "point estimate with confidence factor"
   - [ ] "grid convergence" → I claim "load-increment refinement"
   - [ ] "validated model" → I claim "internally consistent model"
```
