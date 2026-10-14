"""Run the labelled case library and draw the catch matrix.

This script deliberately owns no analysis of its own. It calls
``verisolv.cases.run_all`` and draws whatever comes back.

That is a correction, not a style preference. An earlier version of this file
carried its own copy of the summary and of the per-case row construction, and the
two copies drifted: the CLI grew a ``test_class`` field and a closed-form
comparison, this file did not, and the JSON evidence it wrote silently lacked
both. The AGH tool then read fields from one shape while the CLI emitted the
other. Three separate defects, one cause -- two implementations of one truth.

So: one implementation, in ``verisolv/cases.py``. This file plots and prints.

Run from the project root:  python tools/run_case_library.py
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verisolv.cases import run_all  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
FIGURES = ROOT / "figures"

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
matplotlib.rcParams["figure.dpi"] = 160

DETECTORS = ["diagnoser", "verification", "model_check"]


def figure(rows: list[dict]) -> None:
    """A catch matrix: case down the side, detector across the top."""
    grid = np.zeros((len(rows), len(DETECTORS)))
    for i, row in enumerate(rows):
        for j, detector in enumerate(DETECTORS):
            grid[i, j] = 1.0 if detector in (row.get("caught_by") or []) else 0.0

    fig, ax = plt.subplots(figsize=(8.4, max(4.6, 0.40 * len(rows))))
    ax.imshow(grid, cmap="Blues", vmin=0, vmax=1.6, aspect="auto")
    ax.set_xticks(range(len(DETECTORS)))
    ax.set_xticklabels(
        ["诊断器\nDiagnoser", "验证层\nVerification", "模型检查\nModel check"], fontsize=10
    )
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(
        [f"{r['name'].split('_', 1)[0]}  {r['root_cause']}" for r in rows], fontsize=8
    )

    for i, row in enumerate(rows):
        for j, detector in enumerate(DETECTORS):
            if detector in (row.get("caught_by") or []):
                ax.text(j, i, "X", ha="center", va="center", fontsize=11,
                        fontweight="bold", color="#1e3a8a")
        if not row.get("caught_by"):
            if row.get("analytical"):
                agreement = row["analytical"]
                label = (
                    f"closed form: agrees to {agreement['relative_error']:.1e}"
                    if agreement.get("passed")
                    else f"closed form: DISAGREES {agreement['relative_error']:.1e}"
                )
                colour = "#166534" if agreement.get("passed") else "#b91c1c"
            elif row.get("detectable_by") == "intent_only":
                label = "nothing can detect this: an intent mismatch, not a defect"
                colour = "#b91c1c"
            else:
                label = "positive control: nothing should be flagged"
                colour = "#166534"
            ax.text(1, i, label, ha="center", va="center", fontsize=7.6,
                    color=colour, style="italic")

    ax.set_title(
        "哪一层抓得住哪一类错误  Which layer catches which class of error",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout()
    FIGURES.mkdir(exist_ok=True)
    fig.savefig(FIGURES / "catch_matrix.png")
    plt.close(fig)


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    RUNS.mkdir(exist_ok=True)

    data = run_all(verbose=True)
    rows = data["cases"]
    summary = data["summary"]

    print()
    for key in (
        "total_cases", "detected", "detectable_errors", "detection_rate",
        "undetectable_by_design", "undetectable_cases", "unexpectedly_detected_anyway",
        "positive_controls", "controls_clean", "controls_false_alarm",
        "repair_behaviour_correct", "repair_mismatch", "missed",
        "as_expected", "as_expected_of", "by_expected_detector",
    ):
        print(f"  {key:<32} {summary.get(key)}")

    reference = [r for r in rows if r.get("analytical")]
    if reference:
        print()
        print("  closed-form agreement (independent of the solver's own assembly):")
        for row in reference:
            a = row["analytical"]
            mark = "AGREES" if a.get("passed") else "DISAGREES"
            print(
                f"    {row['name']:<42} {a['quantity']:<16} "
                f"{a['relative_error']:.2e} relative  {mark}"
            )

    figure(rows)
    (RUNS / "case_library.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=float), encoding="utf-8"
    )
    print(f"\nfigure -> {FIGURES / 'catch_matrix.png'}")
    print(f"data   -> {RUNS / 'case_library.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
