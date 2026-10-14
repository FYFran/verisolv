---
name: result-verification
description: Decide whether a computed result can be believed, and explain what each verification gate actually proves. Use when a number will be reported, acted on, or challenged.
---

# Deciding whether a result can be believed

## The premise

A solver returning `converged: true` is a **claim**, not evidence. Nonlinear
solvers fail in two ways and only one of them is loud:

- **Loud failure** — divergence, a singular matrix, non-finite arithmetic. The
  run stops and you know.
- **Silent failure** — the iteration converges onto a *different* equilibrium
  branch and reports success. The equilibrium path it claims to have traced is
  broken, and every number downstream is wrong while looking perfectly healthy.

Silent failures are the reason this verification layer exists.

## The four gates, and what each one is worth

Called "gates", not "independent verifications" — because two of them are not
independent, and claiming otherwise would be the exact kind of overstatement this
project is about.

| Gate | What it establishes | Limitation |
| --- | --- | --- |
| `residual` | The reported state really does satisfy the equilibrium equations | Rebuilds from the same element assembly, so a formulation error passes |
| `global_equilibrium` | Force **and moment** balance against the support reactions | Same shared assembly; also a formulation error passes |
| `path_continuity` | No increment is wildly larger than its neighbours | A heuristic detector with a calibrated threshold, not a proof |
| `step_refinement` | Re-running with a different step size gives the same answer | Same solver, so a consistent bug is invisible |

Two of the four reuse the solver's own assembly. They are **self-consistency
checks**: they catch a solver that has lost its way, not one that was built
wrong. That job belongs to the external comparisons — the closed-form solution
and the independent library — which share no code with the solver at all.

**Say it that way.** "Four gates, two of which are internal consistency and two
of which are external reference comparisons" is a true statement about a real
system. "Four independent verifications" is not.

## How to read a verdict

- **`verified`** — every gate passed. Report the number.
- **`suspect`** — a gate failed. Something is wrong but the run completed. Do not
  report the number as an answer; report the finding. `path_continuity` failing
  with a large ratio is the branch-jump signature: the solver converged onto the
  wrong branch.
- **`rejected`** — a critical gate failed. The state is not an equilibrium at all.

## A gate that cannot run is not a gate that passed

If a check cannot be evaluated — too few increments to judge continuity, no
solution state to test — it reports a **failure with a reason**, not a pass.
Returning "ok" for "could not assess" is fail-open behaviour and it is the one
thing this module must never do.

## Two things verification cannot see

1. **A formulation error.** Every gate either reuses the solver's assembly or
   compares against the same wrong answer. This is why the closed-form case and
   the PyNite cross-check exist, and why they are reported separately.
2. **A modelling error.** A reversed load, a unit slip, a mistyped modulus: the
   arithmetic is correct, the answer is self-consistent, and it answers the wrong
   question. Use `verisolv_checkmodel`, which never runs the solver and so cannot
   inherit its assumptions.

## Reporting a result honestly

Give the number, its origin, and the verdict together — and when a gate failed,
say which one and what it means rather than quietly dropping the number.
Silence about a failed gate is worse than the failure.
