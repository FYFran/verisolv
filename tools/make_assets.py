"""Generate the figures the demo video depends on, plus the data behind them.

Two figures carry the whole story:

1. the equilibrium path of the shallow truss, with the limit point, the closed
   form peak, and the point where load control died;
2. the design search, showing mass falling while the constraints stay satisfied.

Run from the project root:  python tools/make_assets.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verisolv.fem import E_STEEL  # noqa: E402
from verisolv.models import cantilever_truss, von_mises_truss  # noqa: E402
from verisolv.optimize import Constraints, OptimizeResult, optimize  # noqa: E402
from verisolv.solver import SolverOptions, solve  # noqa: E402

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
matplotlib.rcParams["figure.dpi"] = 160

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
FIGURES = ROOT / "figures"

# von Mises truss parameters, shared with the physics validation script.
HALF_SPAN, RISE, AREA, REFERENCE_LOAD = 1.0, 0.1, 1.0e-4, 20_000.0


def closed_form_force(downward: np.ndarray | float):
    """Analytical apex force for a given downward apex displacement."""
    l0 = float(np.hypot(HALF_SPAN, RISE))
    den = 2.0 * (HALF_SPAN**2 + RISE**2)
    v = np.asarray(downward, dtype=float)
    strain = v * (v - 2.0 * RISE) / den
    return 2.0 * E_STEEL * AREA * l0 * strain * (v - RISE) / (HALF_SPAN**2 + RISE**2)


def figure_equilibrium_path() -> dict:
    """Trace the full path with displacement control and plot it."""
    model = von_mises_truss(HALF_SPAN, RISE, AREA, REFERENCE_LOAD)
    path = solve(
        model,
        SolverOptions(
            control="displacement",
            control_dof=5,
            target_displacement=-0.195,
            n_steps=120,
            tol=1e-10,
        ),
    )
    if not path.converged:
        raise RuntimeError(f"path trace failed: {path.failure}")

    drop = -np.array([s.control_end for s in path.steps])
    force = np.array([s.load_factor * REFERENCE_LOAD for s in path.steps])
    peak = int(np.argmax(force))

    # Where load control died: the last increment it could accept.
    failed = solve(
        model,
        SolverOptions(control="load", n_steps=10, max_iter=30, adaptive=False),
    )
    wall_x = failed.steps[-1].max_displacement
    wall_y = failed.load_factor * REFERENCE_LOAD
    stalled = failed.failures[-1].residual_norm if failed.failures else float("nan")

    # The branch jump: adaptive load control converges onto the far branch.
    jumped = solve(
        model,
        SolverOptions(control="load", n_steps=10, max_iter=30, adaptive=True),
    )
    jx = np.array([s.max_displacement for s in jumped.steps])
    jy = np.array([s.load_factor * REFERENCE_LOAD for s in jumped.steps])
    inc = np.abs(np.diff(jx))
    jump_at = int(np.argmax(inc)) + 1

    fig, ax = plt.subplots(figsize=(9.2, 5.6))
    grid = np.linspace(0.0, 0.195, 400)
    ax.plot(grid, closed_form_force(grid), color="#94a3b8", lw=1.4, ls="--",
            label="Closed form 闭式解", zorder=2)
    ax.plot(drop, force, color="#0369a1", lw=2.8,
            label="Displacement control 位移控制", zorder=3)

    # One red element, not four -- and it stops at the jump.
    #
    # The load-control path was drawn in full, which meant that after the branch
    # jump it climbed almost vertically (x moves 0.2155 -> 0.2201 while force goes
    # 8,000 -> 11,000 and beyond), giving a red line that shot off the top of the
    # chart. A reader counted seven red objects and called it messy; that vertical
    # stroke was most of the reason. What happens after the jump is not part of the
    # story the narration tells, so the path is cut at the landing point.
    # lw is above the blue curve's 2.8 is not needed, but at 1.7 the red left
    # segment sat entirely inside the blue stroke and read as invisible, which
    # left the legend entry unexplained. 2.4 with a longer dash shows through.
    ax.plot(jx[: jump_at + 1], jy[: jump_at + 1], color="#dc2626", lw=2.4,
            ls=(0, (2.4, 2.4)), label="Load control 载荷控制", zorder=5)
    ax.plot([jx[jump_at]], [jy[jump_at]], "o", color="#dc2626", ms=8, zorder=5)

    # The chart carries exactly the three things the narration says: the two axes,
    # the peak, and the jump. The "load control failed here / residual stalled"
    # callout was removed -- the narration never mentions the residual, so on screen
    # it was an unexplained fourth label competing for attention.
    ax.plot([drop[peak]], [force[peak]], "*", color="#b45309", ms=22, zorder=10)
    ax.annotate(
        f"极限载荷 {force[peak]:,.1f} N",
        xy=(drop[peak], force[peak]), xytext=(0.072, 10800),
        fontsize=12, fontweight="bold", color="#b45309",
        arrowprops=dict(arrowstyle="->", color="#b45309", lw=1.5), zorder=11,
        ha="left", va="top",
    )

    # Placed into measured free space: for x > 0.10 the blue curve is below zero
    # while the jump line sits at y ~ 8000, so this band is empty.
    jump_x = 0.5 * (jx[jump_at - 1] + jx[jump_at])
    jump_y = 0.5 * (jy[jump_at - 1] + jy[jump_at])
    ax.annotate(
        f"一步跳 {inc.max():.3f} m",
        xy=(jump_x, jump_y), xytext=(0.112, 4300),
        fontsize=12, fontweight="bold", color="#dc2626",
        arrowprops=dict(arrowstyle="->", color="#dc2626", lw=1.5), zorder=11,
        ha="left", va="top",
    )

    ax.axhline(0, color="#cbd5e1", lw=0.9, zorder=1)
    ax.set_xlabel("顶点下挠  Apex displacement (m)", fontsize=11)
    ax.set_ylabel("顶点载荷  Apex force (N)", fontsize=11)
    ax.set_title("浅拱桁架的平衡路径\nEquilibrium path of a shallow truss",
                 fontsize=13, fontweight="bold")
    ax.legend(loc="lower left", fontsize=10, framealpha=0.95)
    ax.grid(alpha=0.22, zorder=0)
    ax.set_xlim(-0.010, 0.235)
    ax.set_ylim(-9200, 11600)
    fig.tight_layout()
    FIGURES.mkdir(exist_ok=True)
    fig.savefig(FIGURES / "equilibrium_path.png")
    plt.close(fig)

    return {
        "limit_load_N": float(force[peak]),
        "limit_drop_m": float(drop[peak]),
        "closed_form_limit_N": 7963.2,
        "load_control_failed_at_N": float(wall_y),
        "load_control_stalled_residual_N": float(stalled),
        "branch_jump_m": float(inc.max()),
        "branch_jump_ratio": float(inc.max() / np.median(inc)),
        "path_points": int(len(path.steps)),
    }


def figure_optimization() -> dict:
    """Minimise cantilever mass under stress, deflection and buckling limits.

    The buckling check matters: a two-force bar carries no bending stiffness in
    this formulation, so without an explicit Euler check the search would happily
    report a design whose compression diagonals would collapse in service.  The
    search also aims at 98% of each allowable, which costs a little mass and buys
    a design that still passes when somebody else checks it at 100%.
    """
    span, height, tip_load = 4.0, 1.0, -50_000.0

    def make(areas):
        return cantilever_truss(panels=4, span=span, height=height,
                                tip_load=tip_load, areas=areas)

    start = make(None).design_vector()
    constraints = Constraints(
        max_stress=150e6,
        max_deflection=span / 200.0,
        buckling_factor=2.0,
    )
    lower = {g: 1.0e-4 for g in start}
    upper = {g: 1.2e-2 for g in start}

    result: OptimizeResult = optimize(
        make, start, constraints, lower, upper,
        solver_options=SolverOptions(control="load", n_steps=10, max_iter=80, adaptive=True),
        max_iterations=60,
        verify_best=True,
        verbose=False,
    )

    history = result.history
    idx = np.arange(1, len(history) + 1)
    mass = np.array([c.mass for c in history])
    feasible = np.array([c.feasible for c in history])
    stress = np.array([c.max_stress for c in history]) / 1e6
    defl = np.array([c.max_deflection for c in history]) * 1e3

    best_so_far = np.minimum.accumulate(np.where(feasible, mass, np.inf))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.2, 6.6), sharex=True,
                                   gridspec_kw={"height_ratios": [2.1, 1.0]})

    ax1.plot(idx[~feasible], mass[~feasible], "x", color="#dc2626", ms=6,
             label="Infeasible 不可行设计")
    ax1.plot(idx[feasible], mass[feasible], "o", color="#0369a1", ms=4.5,
             label="Feasible 可行设计")
    ax1.plot(idx, best_so_far, color="#f59e0b", lw=2.4, label="Best so far 当前最轻可行")
    if result.best:
        ax1.axhline(result.best.mass, color="#16a34a", lw=1.2, ls="--")
        # "最轻可行" not "最优": pattern_search is a coordinate descent, so this is
        # the lightest feasible design *this search found*, not a global optimum.
        # Labelling it "最优" would claim a guarantee the algorithm does not give.
        ax1.annotate(
            f"最轻可行 {result.best.mass:.1f} kg\n（基线 {make(None).total_mass():.1f} kg，"
            f"减重 {(1-result.best.mass/make(None).total_mass())*100:.1f}%）\n"
            f"坐标模式搜索，非全局最优",
            xy=(len(idx) * 0.62, result.best.mass),
            xytext=(len(idx) * 0.62, result.best.mass + 55),
            fontsize=10.0, fontweight="bold", color="#15803d",
        )
    ax1.set_ylabel("结构质量 Mass (kg)", fontsize=11)
    ax1.set_title("截面寻优（坐标模式搜索）：质量下降，约束始终满足\n"
                  "Sizing optimisation: mass falls while the constraints hold",
                  fontsize=12.5, fontweight="bold")
    ax1.legend(fontsize=9.5)
    ax1.grid(alpha=0.25)

    ax2.plot(idx, stress, color="#7c3aed", lw=1.5, label="最大应力 Stress (MPa)")
    ax2.axhline(constraints.max_stress / 1e6, color="#7c3aed", ls="--", lw=1.1)
    ax2.set_ylabel("应力 Stress (MPa)", fontsize=10, color="#7c3aed")
    ax2.tick_params(axis="y", labelcolor="#7c3aed")
    ax2b = ax2.twinx()
    ax2b.plot(idx, defl, color="#0891b2", lw=1.5, label="最大挠度 Deflection (mm)")
    ax2b.axhline(constraints.max_deflection * 1e3, color="#0891b2", ls="--", lw=1.1)
    ax2b.set_ylabel("挠度 Deflection (mm)", fontsize=10, color="#0891b2")
    ax2b.tick_params(axis="y", labelcolor="#0891b2")

    # The buckling margin belongs on the figure: it is the constraint that stops
    # the search from shaving the compression diagonals to nothing.
    buckling = np.array([
        c.min_buckling_ratio if c.min_buckling_ratio not in (None, float("inf")) else np.nan
        for c in result.history
    ])
    ax2c = ax2.twinx()
    ax2c.spines["right"].set_position(("outward", 46))
    ax2c.plot(idx, buckling, color="#dc2626", lw=1.5, ls="-.",
              label="压杆稳定 Buckling N_cr/|N|")
    ax2c.axhline(constraints.buckling_factor, color="#dc2626", ls="--", lw=1.1)
    ax2c.set_ylabel("N_cr/|N| (要求 ≥2)", fontsize=10, color="#dc2626")
    ax2c.tick_params(axis="y", labelcolor="#dc2626")
    ax2c.set_ylim(0, max(6.0, float(np.nanmax(buckling)) * 1.1 if np.any(~np.isnan(buckling)) else 6.0))

    handles = (
        ax2.get_legend_handles_labels()[0]
        + ax2b.get_legend_handles_labels()[0]
        + ax2c.get_legend_handles_labels()[0]
    )
    ax2.legend(handles=handles, fontsize=8.5, loc="upper right", ncol=3, framealpha=0.95)
    ax2.set_xlabel("设计评估次数 Design evaluations", fontsize=11)
    ax2.grid(alpha=0.25)

    fig.tight_layout()
    FIGURES.mkdir(exist_ok=True)
    fig.savefig(FIGURES / "optimization.png")
    plt.close(fig)

    return {
        "baseline_mass_kg": float(make(None).total_mass()),
        "best_mass_kg": float(result.best.mass) if result.best else None,
        "best_areas": result.best.areas if result.best else None,
        "mass_reduction_pct": (
            float((1 - result.best.mass / make(None).total_mass()) * 100) if result.best else None
        ),
        "evaluations": result.evaluations,
        "verified": result.verified,
        "verdict": result.verdict,
        "constraints": constraints.describe(),
        "stress_limit_MPa": constraints.max_stress / 1e6,
        "deflection_limit_mm": constraints.max_deflection * 1e3,
        "best_max_stress_MPa": float(result.best.max_stress) / 1e6 if result.best else None,
        "best_max_deflection_mm": float(result.best.max_deflection) * 1e3 if result.best else None,
        "best_min_buckling_ratio": (
            float(result.best.min_buckling_ratio) if result.best and result.best.min_buckling_ratio
            else None
        ),
        "best_governing_bar": result.best.governing_bar if result.best else None,
    }


def main() -> int:
    RUNS.mkdir(exist_ok=True)
    FIGURES.mkdir(exist_ok=True)

    print("=== 1/2 equilibrium path ===")
    eq = figure_equilibrium_path()
    for k, v in eq.items():
        print(f"  {k:<34} {v}")

    print("\n=== 2/2 design optimisation ===")
    op = figure_optimization()
    for k, v in op.items():
        print(f"  {k:<34} {v}")

    (RUNS / "video_assets.json").write_text(
        json.dumps({"equilibrium_path": eq, "optimization": op},
                   indent=2, ensure_ascii=False, default=float),
        encoding="utf-8",
    )
    print(f"\nfigures -> {FIGURES}")
    print(f"data    -> {RUNS / 'video_assets.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
