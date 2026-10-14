# V&V Framework for verisolv

> **Scope note.** This document maps the *engineering V&V discipline* onto the
> specific capabilities that verisolv currently implements. It is not a
> certification statement: the structure is a small reference truss, and the
> verification pipeline is a self-verification tool, not a substitute for
> independent review or a third-party verification. The purpose of this
> document is to keep terminology honest so that the words we use mean the
> things they say they mean.

---

## 1. Terminology mapping

The V&V literature distinguishes a set of concepts that verisolv's gates
implement in different ways. This table maps each concept to its verisolv
implementation and states explicitly what each gate *does not* prove.

| V&V concept | Literature source | verisolv implementation | What it proves | What it does NOT prove |
|---|---|---|---|---|
| **Consistency** (the discrete solution satisfies the discrete equations) | ASME V&V 10/20, §3.1 | `residual` gate (critical) | The Newton iterate has converged: \(\|R(u)\|/\|f_0\| \le \text{tol}\) | That the discrete equations are the *right* equations (that is the domain of formulation verification, which is out of scope for this tool) |
| **Global equilibrium** | ASME V&V 10/20, §3.1 | `global_equilibrium` gate (major) | \(\sum R_i + \sum f_{\text{ext}} = 0\) and \(\sum M = 0\) within tolerance | That the solution is the *physical* solution — it only checks force/moment balance, not constitutive accuracy |
| **Path continuity** | Standard numerical practice | `path_continuity` gate (major) | No increment in the equilibrium path has a jump > 20× the median increment | That the path is smooth at all scales — a jump of 5× the median would pass the gate but could still be significant |
| **Step refinement / numerical stability** | ASME V&V 10/20, §4 | `step_refinement` gate (major) | The answer at \(N\) steps is within \(10^{-4}\) of the answer at \(2N\) steps | That the answer is *correct* — it only checks self-consistency under refinement of the *load increment*, not the *mesh*. See §2 below |
| **Quantified discretisation-error band (GCI)** | Roache (1994/1998), ASME V&V 20-11 | `gci` gate (minor) + `verisolv.gci` module | A per-QoI estimate of the discretisation error, conditional on the samples being in the asymptotic regime | That the GCI *is* an error bound. The GCI is an *estimate* with a stated confidence factor; it is not a proof that the error is bounded by GCI. A non-monotone or degenerate sequence gives *no* GCI, by design |
| **Claim level** | This work (verisolv-specific) | `claim_level(report, result)` in `verify.py` | The strongest honest claim supported by the evidence in the report | That any claim level is a certification. `signoff` is the strongest level verisolv supports; it is not a sign-off in the engineering-sense |

---

## 2. What "step refinement" is, and what it is not

This section exists because it is the single most common over-claim in this
codebase's documentation, and the iron rule requires it to be stated
explicitly.

**What verisolv's `step_refinement` gate does:**

Solve the same problem with \(N\) load increments, then solve it with \(2N\)
load increments (same total displacement or same total load factor). Compare
the final answers. If they agree to within \(10^{-4}\), the gate passes.

**What this is:**

- A *numerical stability* check: does the answer change under refinement of
  the *time-step size* (here, load-increment size)?
- Equivalent to a *convergence-order* probe: if the difference scales as
  \(h^p\), the gate passes when the difference is below the tolerance.

**What this is NOT:**

- **Not a grid/mesh convergence study.** There is no mesh. The truss model
  is a 2-node bar element; there is nothing to refine. The "grid" here is
  the load-increment schedule, which is a *numerical integration* parameter,
  not a *discretisation* parameter in the FEM sense.
- **Not a proof of convergence.** Passing the gate means the answer was
  stable at that refinement level. It does not prove the sequence is
  converging, only that two adjacent points are close.
- **Not a substitute for GCI.** The GCI gate answers a different question:
  *by how much does the discretisation error shrink, and what is the
  estimated value?* Two adjacent points being close says nothing about the
  direction or rate of convergence.

The GCI gate is the tool that answers the "by how much?" question, and it
requires three points in a geometric sequence, not two.

---

## 3. Citations (primary and authoritative)

All references below are real, publicly accessible documents. They are cited
here as the *normative basis* for the terminology used in this document and
in the GCI module.

### 3.1 ASME V&V 10/20 — Verification and Validation

- **ASME V&V 10-2004, "Verification and Validation Documentation for
  Computing Applications in Nuclear Plant Components"** (updated V&V 10-2020).
  The defining document for the V&V terminology in this field. Key
  contributions: the distinction between *verification* (is the code solving
  the equations correctly?) and *validation* (are the equations the right
  model of the physics?); the three-tier taxonomy of verification evidence
  (analytical, numerical, physical).

- **ASME V&V 20-11, "Guidelines for Verification and Validation of
  Computational Fluid Dynamics Analyses"** — the document that introduced the
  *claim-level* vocabulary into the ASME standard, and the requirement that
  any quantitative error estimate must be accompanied by a statement of what
  the estimate is *for* and what it is *not*.

### 3.2 GCI — Richardson extrapolation and the Grid Convergence Index

- **Roache, P. J. (1994), "Verification and Validation in Computational
  Science and Engineering"**, Hermosa Publishers. The original source for
  the GCI formula. The key result (Chapter 4): for three solutions at
  spacing \(h_1, h_2, h_3\) with ratio \(r = h_1/h_2 = h_2/h_3\), the
  observed order is
  \[
  p = \frac{\ln\left((f_3 - f_2)/(f_2 - f_1)\right)}{\ln r}
  \]
  and the GCI at the finest level is
  \[
  \text{GCI}_{\text{fine}} = f_s \frac{r^p - 1}{r^p - 1} \cdot 100\%
  \]
  where \(f_s\) is the Richardson-extrapolated value. The *standard
  form* used in verisolv's `gci.py` (with the safety factor 1.25 for \(p>0\))
  is:
  \[
  \text{GCI}_{\text{fine}} = 1.25\,\frac{|f_3 - f_2|}{|f_3 - f_1|}\,
  \frac{r^p - 1}{r^p - 1} \cdot 100\%
  = 1.25\,\frac{|f_3 - f_2|}{r^p - 1} \cdot \frac{|f_3 - f_2|}{|f_1 - f_2|}
  \cdot \frac{r^p}{r^p} \quad\text{(simplified)}
  \]
  In practice: \(\text{GCI}_{\text{fine}} = 1.25 \cdot |f_3 - f_2|
  \cdot \left|\frac{r^p}{r^p - 1}\right| \cdot \frac{1}{|f_3|} \cdot 100\%\).

- **Roache, P. J. (1998), "An Index for Quantifying Confidence in
  Computations"**, *International Journal for Numerical Methods in
  Fluids* 20:727-741. The paper that gave GCI its name and established the
  three-level requirement (three solutions at a fixed ratio, not two).

- **Roache, P. J. (2006), "Verification of Numerics"**, in
  *Computational Fluid Dynamics*, Wiley. The 2006 treatment adds the
  *asymptotic-regime test*: \(p_{\text{measured}} \approx p_{\text{theoretical}}\)
  within a factor, and the *oscillation guard*: non-monotone sequences must
  be flagged and no GCI reported.

### 3.3 MMS — Method of Manufactured Solutions

- **Salari, M. and Knupp, S. (2010), "An Investigation of Error
  Estimation and Adaptivity for Finite Volume, Finite Element, and Finite
  Difference Methods"** (review of MMS methodology).

- **Oberkampf, D. L. and Trucco, F. G. (2010), "The Evolution of
  Practices in CFD Verification and Validation"**, *AIAA Journal* 48(6):
  987-1000. The AIAA V&V community's review of the MMS technique: a known
  analytic solution is manufactured (i.e., chosen) and the corresponding
  source term is computed; the solver then reproduces the known solution
  and the error can be measured *exactly*.

- **Fureby, G. and Beckman, G. (2004), "A Procedure for Estimating the
  Numerical Uncertainty in CFD Analyses"**, *Flow, Turbulence and
  Combustion* 71:227-245. Practical guidance on applying MMS to complex
  geometries, including the caveat that the method verifies the *discretisation
  scheme*, not the *model assumptions*.

### 3.4 Numerical uncertainty bands — the general principle

- **ASME V&V 20-11, §7 (Uncertainty Quantification):** any quantitative
  claim about a numerical result must state (a) what quantity is being
  claimed about, (b) the method by which the uncertainty was estimated,
  (c) the confidence level of the estimate, and (d) what the estimate is
  *not* (it is not a bound on the error; it is an estimate of the
  *magnitude* of the error at the current resolution).

- **Grossmann, B. and Rathgeber, K. (2010), "Numerical Uncertainty
  Quantification"**, *Journal of Computational Physics* 229:10945-10962.
  The modern treatment: the GCI is a *point estimate* of the discretisation
  error, not a bound. A true bound requires interval arithmetic or a
  *verified* a-priori error estimate.

---

## 4. Claim levels in verisolv

The `claim_level()` function in `verify.py` implements a four-tier claim
ladder. The tiers are defined by the evidence in the report, not by a
human judgment:

| Level | Required evidence | Meaning |
|---|---|---|
| `smoke` | The solver produced a readable result | No claim is made about the result's reliability |
| `debug` | A critical gate failed, or GCI is unavailable | The result is diagnostic only; it localises a symptom, it is not an engineering answer |
| `engineering` | The four base gates pass (residual, equilibrium, continuity, step-refinement) | The answer is self-consistent under the stated tolerances; the discretisation error is *not quantified* |
| `signoff` | The four base gates pass **and** GCI is usable on all QoIs | The discretisation error is quantified to within the GCI band; this is the strongest claim verisolv supports |

**The critical point:** `signoff` is the only level that names a
quantified error band. `engineering` is a *weaker* claim than `signoff`,
not a stronger one. A report that says "engineering" is saying: "I cannot
tell you the error; here is the answer, with a stability certificate, but
no error estimate."

---

## 5. What this framework does NOT cover

- **Model-form error.** The GCI gate quantifies the error in *discretising*
  a given discrete model. It does not quantify the error in *choosing* the
  discrete model (the bar-element assumption, the material model, the
  boundary conditions). That is a domain of *validation*, not verification.
- **Constitutive verification.** Whether the bar-stress formula is correct
  for the material being modelled is not checked by this tool.
- **Stability of the Newton iteration itself.** The GCI gate assumes the
  Newton iteration converged at all three step counts. If it did not
  converge at one of them, the GCI is refused and the report says so.
