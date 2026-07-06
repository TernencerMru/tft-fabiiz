"""Unit tests for core.odds — pure math, verified by hand."""
import math
import random

from tft_companion.core.models import Champion, GameState, SetData
from tft_companion.core import odds


def toy_set() -> SetData:
    champs = {
        "A": Champion(id="A", name="Alpha", cost=1, traits=("Bruiser",)),
        "B": Champion(id="B", name="Beta", cost=1, traits=("Mage",)),
        "C": Champion(id="C", name="Gamma", cost=2, traits=("Mage",)),
    }
    return SetData(
        set_id="test", patch="0.0", champions=champs,
        pool_sizes={1: 10, 2: 5},
        shop_odds={5: {1: 0.6, 2: 0.4}},
        reroll_cost=2,
    )


def test_pool_accounting():
    sd = toy_set()
    state = GameState(level=5, owned={"A": 2}, taken_by_others={"B": 3})
    assert odds.champion_copies_remaining(sd, state, "A") == 8
    assert odds.champion_copies_remaining(sd, state, "B") == 7
    assert odds.tier_copies_remaining(sd, state, 1) == 15
    assert odds.tier_copies_remaining(sd, state, 2) == 5


def test_per_slot_and_shop_probability():
    sd = toy_set()
    state = GameState(level=5, owned={"A": 2}, taken_by_others={"B": 3})
    p_slot = odds.p_champion_per_slot(sd, state, "A")
    assert math.isclose(p_slot, 0.6 * 8 / 15)
    p_shop = odds.p_in_next_shop(sd, state, "A")
    assert math.isclose(p_shop, 1 - (1 - p_slot) ** 5)


def test_exhausted_pool_is_zero():
    sd = toy_set()
    state = GameState(level=5, owned={"C": 5})
    assert odds.p_champion_per_slot(sd, state, "C") == 0.0
    assert odds.p_hit_copies_with_gold(sd, state, "C", 1, 100) == 0.0


def test_wrong_level_tier_is_zero():
    sd = toy_set()
    state = GameState(level=3)  # no odds row for level 3 in the toy table
    assert odds.p_champion_per_slot(sd, state, "A") == 0.0


def test_binomial_at_least():
    assert math.isclose(odds.binomial_at_least(5, 0.5, 1), 1 - 0.5 ** 5)
    assert odds.binomial_at_least(10, 0.0, 1) == 0.0
    assert odds.binomial_at_least(0, 0.9, 1) == 0.0
    assert odds.binomial_at_least(10, 0.3, 0) == 1.0
    # P(X>=2), X~Bin(3, 0.5) = 0.5
    assert math.isclose(odds.binomial_at_least(3, 0.5, 2), 0.5)


def test_hit_copies_with_gold_matches_binomial():
    sd = toy_set()
    state = GameState(level=5)
    p_slot = odds.p_champion_per_slot(sd, state, "A")  # 0.6 * 10/20 = 0.3
    assert math.isclose(p_slot, 0.3)
    expected = odds.binomial_at_least(25, p_slot, 3)  # 10 gold -> 5 rolls -> 25 slots
    got = odds.p_hit_copies_with_gold(sd, state, "A", 3, 10)
    assert math.isclose(got, expected)


def test_simulation_close_to_analytic_when_pool_is_deep():
    sd = toy_set()
    state = GameState(level=5)
    rng = random.Random(42)
    mc = odds.simulate_rolldown(sd, state, "A", gold=10, copies_needed=1,
                                iterations=4000, rng=rng)
    analytic = odds.p_hit_copies_with_gold(sd, state, "A", 1, 10)
    assert abs(mc - analytic) < 0.05


def test_expected_gold_per_copy():
    sd = toy_set()
    state = GameState(level=5)
    # p_slot = 0.3 -> expected = 2 / (5 * 0.3)
    assert math.isclose(odds.expected_gold_per_copy(sd, state, "A"), 2 / 1.5)
    state_empty = GameState(level=5, owned={"A": 10})
    assert odds.expected_gold_per_copy(sd, state_empty, "A") == math.inf
