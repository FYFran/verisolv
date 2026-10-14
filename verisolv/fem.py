"""Plane-truss finite element core (total-Lagrangian, geometrically nonlinear).

The formulation is intentionally the *real* one: Green-Lagrange strain, second
Piola-Kirchhoff stress and an analytically consistent tangent stiffness.  That
matters for this project because geometric nonlinearity is what makes the
Newton-Raphson iteration genuinely able to diverge -- the failure mode the
agent has to detect and repair.

Units are SI throughout: metres, newtons, pascals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

# Structural steel, used as the default material.
E_STEEL = 210.0e9          # Young's modulus (Pa)
FY_STEEL = 235.0e6         # yield strength, Q235 (Pa)
RHO_STEEL = 7850.0         # density (kg/m^3)


class ModelError(ValueError):
    """Raised when a model definition is internally inconsistent."""


@dataclass
class Bar:
    """A two-node bar element with constant axial area."""

    i: int
    j: int
    area: float
    modulus: float = E_STEEL
    density: float = RHO_STEEL
    group: str = "default"
    yield_stress: float = FY_STEEL

    def length(self, coords: np.ndarray) -> float:
        return float(np.linalg.norm(coords[self.j] - coords[self.i]))

    def mass(self, coords: np.ndarray) -> float:
        return self.area * self.density * self.length(coords)


@dataclass
class Model:
    """A plane truss with supports and a single reference load case."""

    coords: np.ndarray          # (n_nodes, 2) reference coordinates
    bars: list[Bar]
    fixed: dict[int, tuple[bool, bool]]   # node -> (x restrained, y restrained)
    loads: np.ndarray           # (n_nodes, 2) reference load vector
    name: str = "unnamed"

    def __post_init__(self) -> None:
        self.coords = np.asarray(self.coords, dtype=float)
        self.loads = np.asarray(self.loads, dtype=float)
        if self.coords.ndim != 2 or self.coords.shape[1] != 2:
            raise ModelError("coords must have shape (n_nodes, 2)")
        if self.loads.shape != self.coords.shape:
            raise ModelError("loads must have the same shape as coords")
        for bar in self.bars:
            for node in (bar.i, bar.j):
                if not 0 <= node < self.node_count:
                    raise ModelError(f"bar references unknown node {node}")
            if bar.i == bar.j:
                raise ModelError("bar cannot connect a node to itself")
            if bar.area <= 0.0:
                raise ModelError("bar area must be positive")
        if not self.bars:
            raise ModelError("model has no bars")

    # ---- basic properties -------------------------------------------------

    @property
    def node_count(self) -> int:
        return int(self.coords.shape[0])

    @property
    def dof_count(self) -> int:
        return 2 * self.node_count

    @property
    def bar_groups(self) -> list[str]:
        seen: list[str] = []
        for bar in self.bars:
            if bar.group not in seen:
                seen.append(bar.group)
        return seen

    def dofs_of(self, bar: Bar) -> list[int]:
        return [2 * bar.i, 2 * bar.i + 1, 2 * bar.j, 2 * bar.j + 1]

    def free_dofs(self) -> np.ndarray:
        """Indices of DOFs that are not restrained."""
        restrained = np.zeros(self.dof_count, dtype=bool)
        for node, (rx, ry) in self.fixed.items():
            if rx:
                restrained[2 * node] = True
            if ry:
                restrained[2 * node + 1] = True
        return np.flatnonzero(~restrained)

    def constrained_dofs(self) -> np.ndarray:
        restrained = np.zeros(self.dof_count, dtype=bool)
        for node, (rx, ry) in self.fixed.items():
            if rx:
                restrained[2 * node] = True
            if ry:
                restrained[2 * node + 1] = True
        return np.flatnonzero(restrained)

    def load_vector(self) -> np.ndarray:
        return self.loads.reshape(-1).copy()

    def total_mass(self, areas: dict[str, float] | None = None) -> float:
        """Mass of the structure; ``areas`` optionally overrides group areas."""
        total = 0.0
        for bar in self.bars:
            area = bar.area if areas is None else areas.get(bar.group, bar.area)
            total += area * bar.density * bar.length(self.coords)
        return total

    def with_group_areas(self, areas: dict[str, float]) -> "Model":
        """Return a copy of the model with per-group bar areas replaced."""
        if not areas:
            return self
        bars = [
            Bar(
                i=bar.i,
                j=bar.j,
                area=float(areas.get(bar.group, bar.area)),
                modulus=bar.modulus,
                density=bar.density,
                group=bar.group,
            )
            for bar in self.bars
        ]
        return Model(
            coords=self.coords.copy(),
            bars=bars,
            fixed=dict(self.fixed),
            loads=self.loads.copy(),
            name=self.name,
        )

    def design_vector(self) -> dict[str, float]:
        areas: dict[str, float] = {}
        for bar in self.bars:
            areas.setdefault(bar.group, bar.area)
        return areas


# ---------------------------------------------------------------------------
# Element level
# ---------------------------------------------------------------------------


@dataclass
class BarState:
    """Per-bar results at a given displacement state."""

    index: int
    length: float
    reference_length: float
    stretch: float              # lambda = L / L0
    strain: float               # Green-Lagrange strain
    stress: float               # second Piola-Kirchhoff stress (Pa)
    engineering_stress: float   # first Piola-Kirchhoff = N / A0 = S * lambda
    axial_force: float          # current axial force (N); positive = tension
    area: float
    group: str

    @property
    def in_compression(self) -> bool:
        return self.axial_force < 0.0


def bar_response(bar: Bar, coords: np.ndarray, ue: np.ndarray) -> tuple[np.ndarray, np.ndarray, BarState]:
    """Internal force vector and tangent stiffness of one bar.

    Returns ``(f_int, K, state)`` in the element's 4-DOF ordering
    ``[u_ix, u_iy, u_jx, u_jy]``.
    """
    xi_ref = coords[bar.i]
    xj_ref = coords[bar.j]
    dx_ref = xj_ref - xi_ref
    l0 = float(np.linalg.norm(dx_ref))
    if l0 <= 0.0:
        raise ModelError("bar has zero reference length")

    xi = xi_ref + ue[0:2]
    xj = xj_ref + ue[2:4]
    dx = xj - xi
    length = float(np.linalg.norm(dx))
    if length <= 0.0:
        raise ModelError("bar has collapsed to zero length")

    inv_l0_sq = 1.0 / (l0 * l0)

    # Green-Lagrange strain and its gradient w.r.t. element DOFs.
    #
    # Written as ``(L^2 - L0^2) / (2 L0^2)`` this suffers catastrophic
    # cancellation: for small strains L^2 and L0^2 agree to almost every digit,
    # so the difference keeps only the rounding noise.  The residual then floors
    # at a level the convergence test can never reach, and the driver responds by
    # cutting the step until it gives up -- a failure that looks like a solver
    # defect but is really lost precision.
    #
    # Expanding about the reference configuration removes the cancellation
    # exactly:  L^2 - L0^2 = 2 dX.du + du.du  uses only the displacement, which
    # is itself small, so every term keeps full relative accuracy.
    du = ue[2:4] - ue[0:2]
    delta_l_sq = 2.0 * float(dx_ref @ du) + float(du @ du)
    strain = delta_l_sq * 0.5 * inv_l0_sq

    b = np.concatenate((-dx, dx)) * inv_l0_sq

    stress = bar.modulus * strain
    force = bar.area * l0 * stress * b

    # dB/du is constant for this parameterisation.
    db_du = np.array(
        [
            [1.0, 0.0, -1.0, 0.0],
            [0.0, 1.0, 0.0, -1.0],
            [-1.0, 0.0, 1.0, 0.0],
            [0.0, -1.0, 0.0, 1.0],
        ]
    ) * inv_l0_sq

    # Material part (outer product) + geometric part (initial stress).
    tangent = bar.area * l0 * (np.outer(b, bar.modulus * b) + stress * db_du)

    # Stretch ratio, and the stress measures that follow from it.
    #
    # The constitutive law returns the second Piola-Kirchhoff stress S, which is
    # *not* the measure an allowable-stress check is written against.  The axial
    # force in the current configuration is N = A0 * S * lambda, so the stress on
    # the reference area -- the engineering (nominal) stress, and the first
    # Piola-Kirchhoff stress -- is sigma = S * lambda.  That is the measure the
    # design codes use, and the one worth comparing against an allowable.
    #
    # Note this is engineering stress, not Cauchy stress: Cauchy would divide by
    # the *current* area.  A bar element here carries no lateral-contraction
    # kinematics, so A = A0 throughout and the two would differ only by the
    # Poisson effect the model does not represent.  The name matters because a
    # reader who sees "cauchy = S * lambda" is right to object.
    stretch = length / l0
    engineering_stress = stress * stretch

    state = BarState(
        index=-1,
        length=length,
        reference_length=l0,
        stretch=stretch,
        strain=strain,
        stress=stress,
        engineering_stress=engineering_stress,
        axial_force=bar.area * engineering_stress,
        area=bar.area,
        group=bar.group,
    )
    return force, tangent, state


# ---------------------------------------------------------------------------
# Global assembly
# ---------------------------------------------------------------------------


def assemble(model: Model, u: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[BarState]]:
    """Assemble the internal force vector and tangent stiffness matrix."""
    ndof = model.dof_count
    f_int = np.zeros(ndof)
    k_mat = np.zeros((ndof, ndof))
    states: list[BarState] = []

    for index, bar in enumerate(model.bars):
        idx = model.dofs_of(bar)
        fe, ke, state = bar_response(bar, model.coords, u[idx])
        f_int[idx] += fe
        k_mat[np.ix_(idx, idx)] += ke
        state.index = index
        states.append(state)

    return f_int, k_mat, states


def residual(model: Model, u: np.ndarray, load_factor: float) -> tuple[np.ndarray, np.ndarray, list[BarState]]:
    """Out-of-balance force ``f_int(u) - lambda * f_ext`` and the tangent."""
    f_int, k_mat, states = assemble(model, u)
    return f_int - load_factor * model.load_vector(), k_mat, states


def reactions(model: Model, u: np.ndarray, load_factor: float) -> np.ndarray:
    """Support reactions: full internal force vector restricted to restrained DOFs."""
    f_int, _, _ = assemble(model, u)
    r = np.zeros(model.dof_count)
    constrained = model.constrained_dofs()
    r[constrained] = f_int[constrained] - load_factor * model.load_vector()[constrained]
    return r


def bar_forces(model: Model, u: np.ndarray) -> np.ndarray:
    """Axial force in every bar (positive = tension)."""
    _, _, states = assemble(model, u)
    return np.array([s.axial_force for s in states], dtype=float)


def bar_stresses(model: Model, u: np.ndarray) -> np.ndarray:
    """Second Piola-Kirchhoff stress in every bar.

    This is the constitutive measure, **not** the one to compare against an
    allowable.  Use :func:`bar_engineering_stresses` for design checks.  Both are
    exposed because they answer different questions, and reporting only one
    without saying which is how a reader ends up comparing the wrong number.
    """
    _, _, states = assemble(model, u)
    return np.array([s.stress for s in states], dtype=float)


def bar_engineering_stresses(model: Model, u: np.ndarray) -> np.ndarray:
    """Engineering (nominal) stress N/A0 in every bar -- the design-check measure."""
    _, _, states = assemble(model, u)
    return np.array([s.engineering_stress for s in states], dtype=float)


def bar_states(model: Model, u: np.ndarray) -> list[BarState]:
    """Full per-bar state, for callers that need several measures at once."""
    _, _, states = assemble(model, u)
    return states
