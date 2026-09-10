"""Tests for src/model/risk.py's empirical CVaR, against hand-computed
values (the fractional-atom formula, Rockafellar and Uryasev 2000)."""

from __future__ import annotations

import pytest

from src.model.risk import empirical_cvar, expected_loss


def test_expected_loss_is_plain_expectation():
    assert expected_loss([(0.0, 0.5), (100.0, 0.5)]) == pytest.approx(50.0)


def test_cvar_three_equal_scenarios_alpha_half():
    """Hand derivation: losses {0, 10, 100} each with prob 1/3, alpha=0.5.
    F(10) = 2/3 >= 0.5 so VaR = 10; the worst half of the mass is
    {100 w.p. 1/3, 10 w.p. 1/6}, mean = (100/3 + 10/6) / 0.5 = 70."""
    dist = [(0.0, 1 / 3), (10.0, 1 / 3), (100.0, 1 / 3)]
    assert empirical_cvar(dist, alpha=0.5) == pytest.approx(70.0)


def test_cvar_at_high_alpha_with_few_scenarios_is_worst_case():
    """10 equally likely scenarios at alpha=0.95: the tail mass (0.05) is
    smaller than one atom (0.1), so CVaR collapses to the worst loss,
    the documented SAA-with-few-scenarios behavior."""
    dist = [(float(i), 0.1) for i in range(10)]
    assert empirical_cvar(dist, alpha=0.95) == pytest.approx(9.0)


def test_cvar_alpha_zero_is_expectation():
    dist = [(0.0, 0.25), (4.0, 0.25), (8.0, 0.25), (20.0, 0.25)]
    assert empirical_cvar(dist, alpha=0.0) == pytest.approx(expected_loss(dist))


def test_cvar_order_of_input_does_not_matter():
    dist = [(100.0, 1 / 3), (0.0, 1 / 3), (10.0, 1 / 3)]
    assert empirical_cvar(dist, alpha=0.5) == pytest.approx(70.0)


def test_cvar_rejects_bad_inputs():
    with pytest.raises(ValueError):
        empirical_cvar([], alpha=0.5)
    with pytest.raises(ValueError):
        empirical_cvar([(1.0, 1.0)], alpha=1.0)
    with pytest.raises(ValueError):
        empirical_cvar([(1.0, 0.4)], alpha=0.5)  # probs sum to 0.4
