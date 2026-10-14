---
name: structural-analysis
description: Run a nonlinear structural analysis with the verisolv tools and report an answer that can be defended. Use when asked for a limit load, a deflection, a stress, or whether a design is adequate.
---

# Running a structural analysis you can defend

You have four tools. They are not interchangeable, and the order matters.

| Tool | What it does | When to use it |
| --- | --- | --- |
| `verisolv_models` | Lists the structures available | Once, if you do not know what to analyse |
| `verisolv_solve` | One analysis, raw outcome | A first look, or when you want to see the failure yourself |
| `verisolv_verify` | Solve, then test the answer four ways | When you have a specific load case and need a verdict |
| `verisolv_repair` | The whole loop, ending in a verified answer | **When you want an answer to report** |

## The default path

For any question of the form "how much can this carry" or "is this design
adequate", call **`verisolv_repair` once** and read two fields: `conclusion` and
`peak_load`. That single call solves, verifies, diagnoses any failure, escalates
through repair strategies, and verifies again.

Do **not** call it repeatedly with different `n_steps`. It already searches the
equilibrium path and reports the maximum load it carried; re-sampling the same
curve with finer steps does not improve the answer and wastes the session.

Do **not** read the solver source to work out what happened. The `conclusion`,
`verdict` and per-check detail are the complete answer.

## Reading the result

- `peak_load.absolute_load` — the largest load carried anywhere on the traced
  path, in newtons. This is the number to report.
- `peak_load.interior` — `true` means the peak lies *inside* the path, so the
  structure loses stability there rather than simply reaching the load asked
  for. That distinction matters: a limit point is a property of the structure,
  not a failure of the analysis.
- `verdict` — `verified` means four independent checks passed. `suspect` means at
  least one did not. **Never report a number from a `suspect` or `rejected`
  result without saying so.**

## A limit point is not an error

When load control fails with the residual stalling rather than growing, the
structure has reached a maximum of its equilibrium path. The load cannot be
increased past that point — not because the solver is weak, but because no
equilibrium exists. The repair layer recognises this and switches control
variable. If you see `diagnosis: limit_point`, that is the system working.

## When something looks wrong

If a result is surprising — a stress far below what the load seems to imply, a
deflection that barely moves when the load changes, an analysis that fails for no
visible reason — call **`verisolv_checkmodel` before trusting or reporting
anything**. It inspects the model without solving: missing restraints, material
constants outside the range real solids occupy, loads nothing can react.

This is not a formality. A reversed load sign, a unit slip or a mistyped modulus
produces an answer that converges, passes every numerical check, and is about the
wrong problem. Only a check on the model itself can see it.

## Reporting

State the number, the equilibrium-path origin of it, and the verification verdict
in the same breath. "The limit load is 7958 N, from the traced equilibrium path,
verification verdict verified" is defensible. "The limit load is 7958 N" is not,
because it invites the reader to assume a confidence you have not established.
