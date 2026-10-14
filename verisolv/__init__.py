"""verisolv -- self-verifying structural simulation and design search.

The package is deliberately small and dependency-light (numpy only):

* :mod:`verisolv.fem`     -- total-Lagrangian plane-truss finite elements
* :mod:`verisolv.solver`  -- Newton-Raphson with load / displacement control
* :mod:`verisolv.repair`  -- diagnosis-driven strategy escalation
* :mod:`verisolv.gci`     -- quantified discretisation-error bands (Richardson/GCI)
* :mod:`verisolv.verify`  -- independent evidence that a result can be trusted
* :mod:`verisolv.optimize`-- constrained design search over bar groups
* :mod:`verisolv.models`  -- reference structures used by the demos
"""

from .fem import (
    E_STEEL,
    RHO_STEEL,
    Bar,
    BarState,
    Model,
    ModelError,
    assemble,
    bar_forces,
    bar_stresses,
    reactions,
    residual,
)
from .gci import (
    GCIResult,
    check_refinement_ratio,
    compute_gci,
    evaluate_quantity_over_steps,
)
from .verify import Check, VerificationReport, claim_level, verify
from .solver import (
    FAILURE_DIVERGED,
    FAILURE_MAX_ITERATIONS,
    FAILURE_NONFINITE,
    FAILURE_SINGULAR_TANGENT,
    FAILURE_STEP_EXHAUSTED,
    SolveResult,
    SolverError,
    SolverOptions,
    limit_point,
    solve,
)

__all__ = [
    "E_STEEL",
    "RHO_STEEL",
    "Bar",
    "BarState",
    "Model",
    "ModelError",
    "assemble",
    "bar_forces",
    "bar_stresses",
    "reactions",
    "residual",
    "SolveResult",
    "SolverError",
    "SolverOptions",
    "solve",
    "limit_point",
    "GCIResult",
    "check_refinement_ratio",
    "compute_gci",
    "evaluate_quantity_over_steps",
    "Check",
    "VerificationReport",
    "claim_level",
    "verify",
    "FAILURE_DIVERGED",
    "FAILURE_MAX_ITERATIONS",
    "FAILURE_NONFINITE",
    "FAILURE_SINGULAR_TANGENT",
    "FAILURE_STEP_EXHAUSTED",
]

__version__ = "0.1.0"
