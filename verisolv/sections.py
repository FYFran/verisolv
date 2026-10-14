"""Cross-section shape families, and the buckling check they make possible.

A truss sizing problem is only meaningful if a smaller area is also a weaker
section in bending.  If area and second moment of area were independent knobs,
an optimiser would happily produce members that cannot be manufactured and that
would buckle long before reaching the allowable stress.  Each family here fixes
a *shape* and derives the second moment from the area, so:

* every candidate design corresponds to a real, makeable section;
* the Euler buckling load follows from the section, not from a guess;
* slenderness grows as the area shrinks, so the optimiser is finally working
  against the constraint that governs real slender members.

The reference model throughout is a plane truss of two-force bars, so only
axial behaviour is represented.  Buckling is therefore applied as an explicit
*check* on the axial force rather than as a stiffness reduction -- which is the
honest thing to do rather than pretending the element can capture it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol


class Section(Protocol):
    """A shape family. Everything is derived from the cross-sectional area."""

    name: str

    def second_moment(self, area: float) -> float: ...

    def outer_size(self, area: float) -> float: ...

    def describe(self) -> dict[str, float | str]: ...


@dataclass(frozen=True)
class CircularTube:
    """Hollow circular section with a fixed wall-to-diameter ratio.

    Fixing ``t/D`` is what makes area a single design variable: a family of
    geometrically similar tubes.  Small ``t/D`` gives efficient material use but
    local buckling at low stress; 0.05 is a conservative, ordinary value.
    """

    t_over_D: float = 0.05
    name: str = "circular_tube"

    def __post_init__(self) -> None:
        if not 0.0 < self.t_over_D < 0.5:
            raise ValueError("t_over_D must lie strictly between 0 and 0.5")

    def outer_diameter(self, area: float) -> float:
        if area <= 0.0:
            raise ValueError("area must be positive")
        c = self.t_over_D
        return math.sqrt(area / (math.pi * c * (1.0 - c)))

    def outer_size(self, area: float) -> float:
        """The section's characteristic dimension (its outer diameter)."""
        return self.outer_diameter(area)

    def second_moment(self, area: float) -> float:
        d = self.outer_diameter(area)
        inner = d * (1.0 - 2.0 * self.t_over_D)
        return math.pi / 64.0 * (d**4 - inner**4)

    def radius_of_gyration(self, area: float) -> float:
        return math.sqrt(self.second_moment(area) / area)

    def describe(self) -> dict[str, float | str]:
        return {"shape": self.name, "t_over_D": self.t_over_D}


def slenderness(area: float, length: float, section: Section, k_factor: float = 1.0) -> float:
    """Effective slenderness ratio KL/r."""
    return k_factor * length / section.radius_of_gyration(area)


def transition_slenderness(modulus: float, yield_stress: float) -> float:
    """Slenderness at which a column stops buckling elastically.

    This is the standard critical slenderness ``C_c = pi sqrt(2 E / fy)``, the
    point where the Johnson parabola is *tangent* to the Euler hyperbola.  Both
    branches then give exactly ``fy / 2`` there.

    A common mis-statement uses ``pi sqrt(E / fy)``.  That value is where the
    Euler *stress* equals the yield strength, but it is not where the two design
    curves meet: at ``pi sqrt(E/fy)`` the Johnson parabola gives ``0.75 fy``
    against Euler's ``fy``, a 25% discontinuity.  Switching there would leave a
    step in the capacity curve and make the check depend on which side of an
    arbitrary line the member fell.
    """
    return math.pi * math.sqrt(2.0 * modulus / yield_stress)


def critical_stress(modulus: float, yield_stress: float, slenderness: float) -> float:
    """Critical compressive stress, with the elastic/inelastic transition.

    Euler's formula is only valid for slender columns.  Applied below ``C_c`` it
    returns a stress above the yield strength -- a capacity the material cannot
    reach -- and the error grows as the member gets stockier.  This project's
    members sit at ``KL/r`` around 75 against ``C_c`` of about 133, i.e. inside
    the inelastic range, so evaluating Euler there would inflate the reported
    safety factor by roughly a factor of two.

    The Johnson parabola is used below ``C_c``.  It meets Euler tangentially, and
    returns exactly ``fy`` at zero slenderness, so stocky members become
    yield-controlled automatically.
    """
    if slenderness <= 0.0:
        return yield_stress
    if slenderness <= transition_slenderness(modulus, yield_stress):
        return yield_stress - (yield_stress * slenderness) ** 2 / (4.0 * math.pi**2 * modulus)
    return math.pi**2 * modulus / slenderness**2


def critical_load(
    modulus: float,
    yield_stress: float,
    area: float,
    length: float,
    section: Section,
    k_factor: float = 1.0,
) -> float:
    """Buckling load for this section, valid in both the elastic and inelastic ranges."""
    lam = slenderness(area, length, section, k_factor)
    return area * critical_stress(modulus, yield_stress, lam)
