"""Reference structural models used by the solver and the agent.

Two models are provided on purpose:

``von_mises_truss``
    A shallow two-bar truss.  Its equilibrium path has a limit point: as the
    apex is pushed down the required force rises to a maximum and then falls.
    Load-controlled Newton-Raphson *cannot* pass that maximum -- the tangent
    stiffness goes singular.  It is the smallest honest example of a solver
    that fails for a physical reason rather than a numerical accident.

``cantilever_truss``
    A multi-panel cantilever.  Bars are grouped so that a handful of
    cross-sectional areas become design variables for the optimisation task.

Units: metres, newtons, pascals (steel by default).
"""

from __future__ import annotations

import numpy as np

from .fem import E_STEEL, RHO_STEEL, Bar, Model


def von_mises_truss(
    half_span: float = 1.0,
    rise: float = 0.1,
    area: float = 1.0e-4,
    reference_load: float = 20_000.0,
    modulus: float = E_STEEL,
) -> Model:
    """Shallow two-bar truss with a downward reference load at the apex.

    Supports sit at ``(-half_span, 0)`` and ``(+half_span, 0)``; the apex is at
    ``(0, rise)``.  The apex is restrained horizontally so the model keeps a
    single active degree of freedom, which makes the limit point easy to see.
    """
    coords = np.array(
        [
            [-half_span, 0.0],
            [half_span, 0.0],
            [0.0, rise],
        ]
    )
    bars = [
        Bar(i=0, j=2, area=area, modulus=modulus, density=RHO_STEEL, group="chord"),
        Bar(i=1, j=2, area=area, modulus=modulus, density=RHO_STEEL, group="chord"),
    ]
    loads = np.array([[0.0, 0.0], [0.0, 0.0], [0.0, -reference_load]])
    return Model(
        coords=coords,
        bars=bars,
        fixed={0: (True, True), 1: (True, True), 2: (True, False)},
        loads=loads,
        name="von_mises_truss",
    )


def cantilever_truss(
    panels: int = 4,
    span: float = 4.0,
    height: float = 1.0,
    areas: dict[str, float] | None = None,
    tip_load: float = -50_000.0,
    modulus: float = E_STEEL,
) -> Model:
    """Multi-panel cantilever truss fixed at the left-hand end.

    The bottom and top chords run the full span; verticals carry the shear at
    each station; diagonals brace every panel.  Bars are grouped into
    ``bottom``, ``top``, ``vertical`` and ``diagonal`` so the optimiser has four
    design variables.
    """
    if panels < 1:
        raise ValueError("panels must be >= 1")
    areas = areas or {
        "bottom": 2.0e-3,
        "top": 2.0e-3,
        "vertical": 1.0e-3,
        "diagonal": 1.0e-3,
    }
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

    fixed = {bot(0): (True, True), topp(0): (True, True)}

    return Model(
        coords=coords,
        bars=bars,
        fixed=fixed,
        loads=loads,
        name=f"cantilever_truss_p{panels}",
    )


MODELS = {
    "von_mises_truss": von_mises_truss,
    "cantilever_truss": cantilever_truss,
}


def build(name: str, **kwargs) -> Model:
    """Instantiate a registered model by name."""
    if name not in MODELS:
        raise KeyError(f"unknown model {name!r}; available: {sorted(MODELS)}")
    return MODELS[name](**kwargs)
