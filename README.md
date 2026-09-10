# wildfire-basing

Companion code repository for a paper on joint aerial suppression base and
water refill point location under uncertainty (Cundinamarca, Colombia).
Two-stage stochastic program with a mean-risk CVaR objective, solved via a
big-M linearized MILP and a fix-and-optimize/LNS matheuristic.

**CLAUDE.md is the binding contract** for notation, decisions, and their
provenance. Code and manuscript must use the same symbols; every decision,
data source, and disclosed limitation is recorded there. Read it first.

## Layout

| Path | What |
|---|---|
| `CLAUDE.md` | The contract: notation, model (section 5.2), decisions, data sources, experiment design. |
| `config/` | Pipeline parameters (CRS, ST-DBSCAN eps, confidence filter) and model parameters. |
| `src/pipeline/` | FIRMS/VIIRS download, cleaning, projection (EPSG:9377), ST-DBSCAN event clustering, candidate site catalogs. |
| `src/scenarios/` | Events to SAA scenarios: bootstrap day scenarios, ros[f] (land cover, slope, wind), value_at_risk[f] (WorldPop), assembly. |
| `src/model/` | The section 5.2 MILP (PuLP, CBC/Gurobi), the literal bilinear formulation (gurobipy), real aircraft/cost constants, real-data runner. |
| `src/matheuristic/` | Fix-and-optimize with LNS over first-stage variables; makes the full 120-base/5,449-water-point catalog tractable. |
| `src/experiments/` | The section 9 experiments (experiment 2 implemented so far). |
| `tests/` | Full suite; hand-verified synthetic instances, never real data. |

## Setup

```bash
pip install -r requirements.txt
copy .env.example .env   # then put your own FIRMS MAP_KEY in .env
pytest -q
```

Real data (FIRMS, WorldCover, SRTM, WorldPop, candidate sites) is not
committed; `data/` holds only `.gitkeep` placeholders. See CLAUDE.md
sections 5 and 8 for every source and how each was verified.
