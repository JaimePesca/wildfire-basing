"""Empirical risk measures over a solved instance's discrete scenario
loss distribution, for REPORTING (experiments 4 and 6), not for
optimization (the MILP's own CVaR handling is constraints 8a-8c in
section 5.2 and is untouched here).

Why this exists: the solved model's var_level variable is only
meaningful when the CVaR term actually carries objective weight
(mean_risk_weight > 0); at lambda = 0 the objective ignores it, so
constraints 8b leave it free to sit anywhere low, and reading CVaR off
the solution variables would be garbage. Experiments comparing risk
attitudes across lambda therefore need CVaR recomputed EMPIRICALLY from
the loss distribution itself, identically for every lambda.

empirical_cvar implements the standard discrete-distribution CVaR
(Rockafellar and Uryasev 2000, the same source as the objective's
formulation): VaR_alpha is the smallest loss whose cumulative
probability reaches alpha; CVaR_alpha is the mean of the worst
(1 - alpha) tail, with the boundary atom counted fractionally:

    CVaR = (1 / (1 - alpha)) * (sum_{loss_s > VaR} p_s * loss_s
                                + (F(VaR) - alpha) * VaR)

For alpha smaller than the largest atom's exceedance this reduces to
the worst-case loss, e.g. 10 equally likely scenarios at alpha = 0.95
give CVaR = max loss, the expected behavior under SAA with few
scenarios (worth stating in the paper's SAA caveats, not hiding).
"""

from __future__ import annotations


def expected_loss(losses_and_probs: list[tuple[float, float]]) -> float:
    """Plain expectation, sum p_s * loss_s."""
    return sum(loss * prob for loss, prob in losses_and_probs)


def empirical_cvar(losses_and_probs: list[tuple[float, float]], alpha: float) -> float:
    """CVaR_alpha of a discrete loss distribution given as (loss,
    probability) pairs. Probabilities must sum to 1 (within 1e-6), the
    same precondition milp.build_model enforces for the optimization
    side; raises ValueError otherwise, or for alpha outside [0, 1)."""
    if not losses_and_probs:
        raise ValueError("empirical_cvar needs a non-empty loss distribution")
    if not 0.0 <= alpha < 1.0:
        raise ValueError(f"alpha must be in [0, 1), got {alpha}")
    total_prob = sum(prob for _, prob in losses_and_probs)
    if abs(total_prob - 1.0) > 1e-6:
        raise ValueError(f"probabilities sum to {total_prob}, not 1.0")

    ordered = sorted(losses_and_probs, key=lambda lp: lp[0])
    cumulative = 0.0
    var_level = ordered[-1][0]
    var_index = len(ordered) - 1
    for idx, (loss, prob) in enumerate(ordered):
        cumulative += prob
        if cumulative >= alpha - 1e-12:
            var_level = loss
            var_index = idx
            break

    cumulative_at_var = sum(prob for _, prob in ordered[: var_index + 1])
    tail = sum(loss * prob for loss, prob in ordered[var_index + 1 :])
    return (tail + (cumulative_at_var - alpha) * var_level) / (1.0 - alpha)
