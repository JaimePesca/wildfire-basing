"""cost_base[i] and cost_water[k] (CLAUDE.md section 4): DECIDED 2026-08-30
to be treated as swept sensitivity parameters, uniform across all
candidate bases/water points respectively, the same honesty treatment
already used for initial_fire_area (A0), liters_per_sqm (c), and
ros_scale (CLAUDE.md section 3/9): no Colombia-specific source exists for
the cost of opening a candidate base or enabling a candidate water point,
despite a real web search for one (see CLAUDE.md section 8/10).

Illustrative ranges below anchor on the closest benchmarks actually found:
U.S. wildfire helibase construction (USDA Forest Service's Payson
Helibase, Arizona, USD 4.9 million for a single small helibase; the
Hollister Air Attack Base/Bear Valley Helitack Base complex, California,
over USD 200 million for a large multi-aircraft site) and portable
helicopter water source infrastructure (mobile dip tanks USD 65,000 to
95,000; heli-hydrants around USD 300,000 per unit). Both benchmarks are
scaled down here, because this repo's candidate bases and water points are
already-EXISTING sites (Aerocivil aerodromes, CACOM-4 military bases,
OSM/CAR water bodies, CLAUDE.md section 8), not raw land: "opening" a base
or "enabling" a water point should cost meaningfully less than building
one from scratch. That scaling-down is this repo's own judgment call, not
itself an independently sourced figure; disclosed as such, not presented
as calibrated.

COST_BASE_RANGE_COP: roughly 300 million to 6,000 million COP per base
(about USD 100,000 to 2,000,000 at the 2026-08-30 TRM of approximately
3,200 COP/USD, Banco de la Republica).
COST_WATER_RANGE_COP: roughly 15 million to 300 million COP per water
point (about USD 5,000 to 100,000).

Both ranges are swept in experiment 6 (CLAUDE.md section 9) alongside
initial_fire_area, liters_per_sqm and ros_scale, not fixed at a single
value.
"""

from __future__ import annotations

COST_BASE_RANGE_COP = (300_000_000.0, 6_000_000_000.0)
COST_WATER_RANGE_COP = (15_000_000.0, 300_000_000.0)


def uniform_cost(site_ids: list[str], value: float) -> dict[str, float]:
    """Apply a single swept cost value uniformly across every site id, since
    no per-site cost source exists (see module docstring). This is an
    explicit simplification, not a per-site cost model: every candidate
    base (or every candidate water point) gets the same cost_base[i] (or
    cost_water[k]) for a given sweep point."""
    return {site_id: value for site_id in site_ids}
