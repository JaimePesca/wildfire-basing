"""Real-world reference aircraft type for the single-aircraft-type scope
(CLAUDE.md section 4/10, decided 2026-07-23): closes the "no real aircraft
cost/tank/speed sourced yet" gap.

Colombia's Fuerza Aeroespacial Colombiana (FAC), together with UNGRD, is
acquiring two Sikorsky S-70i FIREHAWK helicopters specifically for wildfire
response, the first aircraft of this class in Latin America. A Firehawk is
a snorkel-fill, fixed-belly-tank helicopter, which matches this repo's
water_points (K) design directly: it fills from any body of water at least
45 cm deep in under a minute via a retractable snorkel, it does not need a
long calm-water runway the way an amphibious fixed-wing scooper (e.g. the
Air Tractor AT-802F Fire Boss, also researched and set aside for this
reason) would.

Sources (verified 2026-08-30):
- Acquisition cost: FAC's own announcement
  (fac.mil.co/es/noticias/llega-colombia-el-firehawk-uno-de-los-helicopteros-mas-versatiles-del-mundo-en-atencion-de)
  and presidencia.gov.co, both stating 150,000 millones de pesos (150
  billion COP) for two units, i.e. 75,000,000,000 COP per unit. A
  contemporary secondary report (zona-militar.com, July 2025) states this
  as "approximately 38 million US dollars" total (about 19 million USD per
  unit at the mid-2025 exchange rate at contract signing); this repo keeps
  the COP figure as authoritative since it is the primary-source currency,
  and does not reintroduce exchange-rate drift into a fixed model
  parameter by converting to USD.
- Tank capacity: 1,000 US gallons, confirmed independently by FAC's own
  article, Lockheed Martin's official Firehawk product page
  (lockheedmartin.com/en-us/products/sikorsky-firehawk.html), and
  militaryfactory.com's spec sheet. 1,000 US gallons = 3,785.41 liters.
- Fill time: under 60 seconds from a water source at least 45 cm deep,
  confirmed independently by both FAC's article and militaryfactory.com
  ("filling said tank in under a minute").
- Cruise speed: 150 knots is the figure most consistently reported across
  independent secondary sources (e.g. Fair Lifts' helicopter
  specifications page). Lockheed Martin's own marketing material
  separately rounds this to "approximately 160 mph" (about 139 knots), and
  one secondary source distinguishes a loaded cruise of 130 knots from an
  unloaded cruise of 150 knots, not independently confirmed elsewhere. This
  module uses 150 knots as the single speed[m] scalar; the model does not
  distinguish loaded/unloaded legs (an existing simplification of the
  single-speed[m] design in section 4/5.2, not introduced here). Disclosed,
  not silently picked.
- Drop/positioning overhead (the other half of ops_time, delta, alongside
  the sourced refill time above): no source was found for how long a
  Firehawk's actual water drop plus repositioning takes. 30 seconds is an
  illustrative default, not independently sourced, same honesty standard
  already used for ros_formula.py's slope_coef/wind_coef and
  population.py's buffer radius.

Units convention DECIDED 2026-08-30 (CLAUDE.md section 4): distance in
meters (matching the EPSG:9377 projected CRS already used throughout this
repo), time in hours throughout (window, ops_time, cycle_time,
t_base_fire, t_fire_water, t_arrival). speed[m] is therefore meters per
hour, not meters per second. This was previously undocumented and
ambiguous; made explicit here because this module is the first place a
real, externally-sourced speed value enters the codebase.
"""

from __future__ import annotations

KNOTS_TO_M_PER_HOUR = 1852.0
GALLONS_TO_LITERS = 3.785411784

FIREHAWK_ID = "S70I_FIREHAWK"

# 150,000,000,000 COP for 2 units (FAC/UNGRD acquisition, see module docstring).
FIREHAWK_COST_COP = 75_000_000_000.0

# 1,000 US gallons (FAC, Lockheed Martin, militaryfactory.com).
FIREHAWK_TANK_LITERS = 1000 * GALLONS_TO_LITERS

# 150 knots cruise (see module docstring for the range found across sources).
FIREHAWK_SPEED_M_PER_HOUR = 150 * KNOTS_TO_M_PER_HOUR

# ops_time (delta) = sourced refill time + illustrative drop/positioning
# overhead (see module docstring).
FIREHAWK_REFILL_TIME_H = 60 / 3600
FIREHAWK_DROP_OVERHEAD_H = 30 / 3600  # illustrative, not sourced
FIREHAWK_OPS_TIME_H = FIREHAWK_REFILL_TIME_H + FIREHAWK_DROP_OVERHEAD_H

# Ready-to-use dicts, keyed by aircraft type id, matching
# schema.ModelParams.cost_aircraft/tank/speed and
# travel_times.assemble_model_params's expected shape.
COST_AIRCRAFT: dict[str, float] = {FIREHAWK_ID: FIREHAWK_COST_COP}
TANK: dict[str, float] = {FIREHAWK_ID: FIREHAWK_TANK_LITERS}
SPEED: dict[str, float] = {FIREHAWK_ID: FIREHAWK_SPEED_M_PER_HOUR}
