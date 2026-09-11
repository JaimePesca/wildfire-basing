"""Generate the manuscript's figures (paper/figures/*.pdf) from the
repo's real data and results CSVs. Print-oriented matplotlib: vector
PDF, serif text, thin recessive grids, one axis per panel, categorical
colors from a CVD-validated trio (Okabe-Ito blue/vermillion/green,
validated with the dataviz palette checker 2026-09-11; neutral gray is
context ink only, never a series identity).

Inputs (all real, none synthetic):
- data/processed/events_2024-full.csv        (2,413 ST-DBSCAN events)
- data/processed/candidate_bases.csv         (120 sites)
- data/processed/candidate_water.csv         (5,449 sites)
- results/experiment4_expectation_vs_cvar.csv
- results/experiment6_sensitivity.csv
- results/tune_matheuristic.csv

Run from the repo root: python paper/make_figures.py
"""

from __future__ import annotations

import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

BLUE = "#0072B2"
VERMILLION = "#D55E00"
GREEN = "#009E73"
GRAY = "#666666"
LIGHTGRAY = "#BBBBBB"

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.size": 9,
        "axes.titlesize": 9,
        "axes.labelsize": 9,
        "legend.fontsize": 8,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": "#DDDDDD",
        "grid.linewidth": 0.4,
        "figure.dpi": 150,
    }
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIGS = ROOT / "paper" / "figures"
FIGS.mkdir(parents=True, exist_ok=True)


def fig_study_area() -> None:
    events = pd.read_csv(ROOT / "data/processed/events_2024-full.csv")
    bases = pd.read_csv(ROOT / "data/processed/candidate_bases.csv")
    water = pd.read_csv(ROOT / "data/processed/candidate_water.csv")

    fig, ax = plt.subplots(figsize=(5.2, 5.0))
    km = 1e-3
    ax.scatter(
        water["x_utm"] * km, water["y_utm"] * km, s=2, c=LIGHTGRAY,
        linewidths=0, label="Candidate water points (5,449)", rasterized=True,
    )
    ax.scatter(
        events["x_utm"] * km, events["y_utm"] * km, s=4, c=VERMILLION, alpha=0.45,
        linewidths=0, label="Fire events 2024 (2,413)", rasterized=True,
    )
    ax.scatter(
        bases["x_utm"] * km, bases["y_utm"] * km, s=28, c=BLUE, marker="^",
        edgecolors="white", linewidths=0.4, label="Candidate bases (120)",
    )
    ax.set_xlabel("Easting, km (EPSG:9377)")
    ax.set_ylabel("Northing, km (EPSG:9377)")
    ax.set_aspect("equal")
    ax.legend(loc="upper left", frameon=True, framealpha=0.9, edgecolor="#CCCCCC")
    fig.tight_layout()
    fig.savefig(FIGS / "fig_study_area.pdf", bbox_inches="tight")
    plt.close(fig)


def fig_exp4() -> None:
    df = pd.read_csv(ROOT / "results/experiment4_expectation_vs_cvar.csv")
    fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.5), sharex=True)

    ax = axes[0]
    ax.plot(df["mean_risk_weight"], df["expected_loss"], "-o", color=BLUE, ms=5, lw=1.5)
    ax.set_xlabel(r"$\lambda$ (mean-risk weight)")
    ax.set_ylabel("Expected loss (persons)")
    ax.annotate(
        "dominated plan\nat pure CVaR",
        xy=(1.0, df["expected_loss"].iloc[-1]),
        xytext=(0.45, df["expected_loss"].iloc[-1] * 0.97),
        fontsize=7.5, color=GRAY,
        arrowprops=dict(arrowstyle="->", lw=0.7, color=GRAY),
    )

    ax = axes[1]
    ax.plot(df["mean_risk_weight"], df["empirical_cvar"], "-o", color=VERMILLION, ms=5, lw=1.5)
    ax.set_xlabel(r"$\lambda$ (mean-risk weight)")
    ax.set_ylabel(r"Empirical CVaR$_{0.95}$ (persons)")
    lo = df["empirical_cvar"].min()
    ax.set_ylim(lo * 0.994, lo * 1.006)

    fig.tight_layout()
    fig.savefig(FIGS / "fig_exp4.pdf", bbox_inches="tight")
    plt.close(fig)


def fig_exp6_budget() -> None:
    df = pd.read_csv(ROOT / "results/experiment6_sensitivity.csv")
    center = df[df["axis"] == "center"].iloc[0]
    bud = df[df["axis"] == "budget"].copy()
    rows = pd.concat(
        [
            pd.DataFrame(
                [
                    {
                        "value": 150e9,
                        "objective_value": center["objective_value"],
                        "timed_out": center["timed_out"],
                        "n_aircraft_total": center["n_aircraft_total"],
                    }
                ]
            ),
            bud[["value", "objective_value", "timed_out", "n_aircraft_total"]],
        ]
    ).sort_values("value")

    fig, ax = plt.subplots(figsize=(4.6, 2.9))
    x = rows["value"] / 1e9
    proven = rows[~rows["timed_out"]]
    bound = rows[rows["timed_out"]]
    ax.plot(x, rows["objective_value"], "-", color=GRAY, lw=0.9, zorder=1)
    ax.scatter(
        proven["value"] / 1e9, proven["objective_value"], s=42, c=BLUE, zorder=3,
        label="Proven optimum",
    )
    ax.scatter(
        bound["value"] / 1e9, bound["objective_value"], s=48, facecolors="white",
        edgecolors=VERMILLION, linewidths=1.6, zorder=3,
        label="Best incumbent at 1,800 s (upper bound)",
    )
    for _, r in rows.iterrows():
        ax.annotate(
            f"{int(r['n_aircraft_total'])} acft",
            xy=(r["value"] / 1e9, r["objective_value"]),
            xytext=(0, 8), textcoords="offset points",
            ha="center", fontsize=7.5, color=GRAY,
        )
    ax.set_xlabel(r"Budget ($10^9$ COP)")
    ax.set_ylabel("Objective (mean-risk, persons)")
    ax.legend(frameon=True, framealpha=0.9, edgecolor="#CCCCCC", loc="lower left", fontsize=7.5)
    fig.tight_layout()
    fig.savefig(FIGS / "fig_exp6_budget.pdf", bbox_inches="tight")
    plt.close(fig)


def fig_runtime() -> None:
    # Wall-clock of the DIRECT integrated Gurobi solve at 20 bases / 50
    # water points / 10 scenarios (81 fires) as the fleet regime grows.
    # Values from results/experiment6_sensitivity.csv (150/225/300 G COP)
    # and CLAUDE.md section 10 (the killed un-limited two-aircraft run).
    labels = [
        "1 aircraft (B = 150 G): proven optimal",
        "2 aircraft (B = 225 G): cut at limit, gap 100%",
        "3 aircraft (B = 300 G): cut at limit, gap 100%",
        "2 aircraft, no limit: killed unproven",
    ]
    seconds = [279.5, 1802.9, 1802.7, 57000.0]
    proven = [True, False, False, False]

    fig, ax = plt.subplots(figsize=(6.2, 2.3))
    colors = [BLUE if p else VERMILLION for p in proven]
    y = range(len(labels))[::-1]
    ax.barh(list(y), seconds, color=colors, height=0.55)
    ax.set_xscale("log")
    ax.set_xlim(10, 2e5)
    ax.set_xlabel("Wall-clock seconds (log scale)")
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=8)
    ax.grid(axis="y", visible=False)
    for yi, s in zip(y, seconds):
        txt = f"{s/3600:.1f} h" if s >= 3600 else f"{s:.0f} s"
        ax.annotate(txt, xy=(s, yi), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=7.5, color=GRAY)
    fig.tight_layout()
    fig.savefig(FIGS / "fig_runtime.pdf", bbox_inches="tight")
    plt.close(fig)


def fig_tuning() -> None:
    df = pd.read_csv(ROOT / "results/tune_matheuristic.csv")
    fig, ax = plt.subplots(figsize=(4.4, 2.7))
    for nb, color, marker in ((5, BLUE, "o"), (10, GREEN, "s")):
        sub = (
            df[df["n_bases_per_neighborhood"] == nb]
            .groupby("n_water_per_neighborhood")["mean_time_s"]
            .mean()
            .reset_index()
        )
        ax.plot(
            sub["n_water_per_neighborhood"], sub["mean_time_s"], marker=marker,
            color=color, lw=1.5, ms=5,
            label=f"{nb} bases per neighborhood",
        )
    ax.set_xlabel("Water points per neighborhood")
    ax.set_ylabel("Mean run time, s (100 iterations)")
    ax.set_xticks([10, 25, 50])
    ax.legend(frameon=True, framealpha=0.9, edgecolor="#CCCCCC", fontsize=7.5)
    fig.tight_layout()
    fig.savefig(FIGS / "fig_tuning.pdf", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    fig_study_area()
    fig_exp4()
    fig_exp6_budget()
    fig_runtime()
    fig_tuning()
    print("Wrote figures to", FIGS)
