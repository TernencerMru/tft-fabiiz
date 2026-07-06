"""Shop probability math. All functions here are pure and side-effect free.

Model
-----
Each of the 5 shop slots independently (1) rolls a cost tier using the
level-based odds table, then (2) draws uniformly among the *remaining copies*
of that tier in the shared pool::

    p_slot(champ) = P(tier | level) * copies_left(champ) / copies_left(tier)

Copies are removed from the pool when any player holds them (bench or board),
so scouting data (``GameState.taken_by_others``) directly improves accuracy.

Multi-slot / multi-roll answers use the binomial approximation: slots are
treated as independent draws with replacement. The exact process shrinks the
pool as copies are drawn, so the approximation is slightly optimistic when
few copies remain; it is the same model most community calculators use.
:func:`simulate_rolldown` is the Monte Carlo alternative that models pool
depletion when you want tighter numbers.
"""
from __future__ import annotations

import math
import random
from typing import Optional

from .models import GameState, SetData

SHOP_SLOTS = 5


# ---------------------------------------------------------------------------
# Pool accounting
# ---------------------------------------------------------------------------

def champion_copies_remaining(set_data: SetData, state: GameState, champion_id: str) -> int:
    champ = set_data.get(champion_id)
    if champ is None:
        return 0
    per_champ = set_data.pool_sizes.get(champ.cost, 0)
    return max(per_champ - state.copies_out_of_pool(champion_id), 0)


def tier_copies_remaining(set_data: SetData, state: GameState, cost: int) -> int:
    per_champ = set_data.pool_sizes.get(cost, 0)
    total = 0
    for champ in set_data.champions_of_cost(cost):
        total += max(per_champ - state.copies_out_of_pool(champ.id), 0)
    return total


# ---------------------------------------------------------------------------
# Single-slot / single-shop probabilities
# ---------------------------------------------------------------------------

def tier_odds(set_data: SetData, level: int) -> dict[int, float]:
    """Probability that one shop slot rolls each cost tier at ``level``."""
    return dict(set_data.shop_odds.get(level, {}))


def p_champion_per_slot(
    set_data: SetData,
    state: GameState,
    champion_id: str,
    level: Optional[int] = None,
) -> float:
    """Probability that ONE shop slot shows ``champion_id``."""
    champ = set_data.get(champion_id)
    if champ is None:
        return 0.0
    lvl = state.level if level is None else level
    p_tier = set_data.shop_odds.get(lvl, {}).get(champ.cost, 0.0)
    if p_tier <= 0:
        return 0.0
    mine = champion_copies_remaining(set_data, state, champion_id)
    tier_total = tier_copies_remaining(set_data, state, champ.cost)
    if mine <= 0 or tier_total <= 0:
        return 0.0
    return p_tier * mine / tier_total


def p_in_next_shop(
    set_data: SetData,
    state: GameState,
    champion_id: str,
    level: Optional[int] = None,
) -> float:
    """Probability of AT LEAST one copy appearing in the next 5-slot shop."""
    p = p_champion_per_slot(set_data, state, champion_id, level)
    return 1.0 - (1.0 - p) ** SHOP_SLOTS


def shop_probabilities(set_data: SetData, state: GameState) -> dict[str, float]:
    """``p_in_next_shop`` for every champion in the set, keyed by champion id."""
    return {
        champ_id: p_in_next_shop(set_data, state, champ_id)
        for champ_id in set_data.champions
    }


# ---------------------------------------------------------------------------
# Multi-roll planning
# ---------------------------------------------------------------------------

def binomial_at_least(n: int, p: float, k: int) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    if k <= 0:
        return 1.0
    if n <= 0 or p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0 if n >= k else 0.0
    # Complement is cheaper when k is small (the common case here).
    miss = 0.0
    for i in range(min(k, n + 1)):
        miss += math.comb(n, i) * (p ** i) * ((1.0 - p) ** (n - i))
    return max(0.0, min(1.0, 1.0 - miss))


def p_hit_copies_with_gold(
    set_data: SetData,
    state: GameState,
    champion_id: str,
    copies_needed: int,
    gold: int,
) -> float:
    """Probability of finding >= ``copies_needed`` copies spending ``gold`` on rerolls.

    Binomial approximation; capped by the copies actually left in the pool.
    """
    left = champion_copies_remaining(set_data, state, champion_id)
    if copies_needed > left:
        return 0.0
    rolls = gold // max(set_data.reroll_cost, 1)
    slots = rolls * SHOP_SLOTS
    p = p_champion_per_slot(set_data, state, champion_id)
    return binomial_at_least(slots, p, copies_needed)


def expected_gold_per_copy(set_data: SetData, state: GameState, champion_id: str) -> float:
    """Rough expected reroll gold to see one copy (infinity if impossible)."""
    p = p_champion_per_slot(set_data, state, champion_id)
    if p <= 0:
        return math.inf
    return set_data.reroll_cost / (SHOP_SLOTS * p)


def simulate_rolldown(
    set_data: SetData,
    state: GameState,
    champion_id: str,
    gold: int,
    copies_needed: int = 1,
    iterations: int = 3000,
    rng: Optional[random.Random] = None,
) -> float:
    """Monte Carlo rolldown that models pool depletion of the target champion.

    Only the target's copies are removed as they are "bought" (other pool
    movement during a real rolldown is second-order). Returns the estimated
    probability of hitting ``copies_needed`` copies with ``gold``.
    """
    champ = set_data.get(champion_id)
    if champ is None:
        return 0.0
    rng = rng or random.Random()
    p_tier = set_data.shop_odds.get(state.level, {}).get(champ.cost, 0.0)
    start_copies = champion_copies_remaining(set_data, state, champion_id)
    start_tier_total = tier_copies_remaining(set_data, state, champ.cost)
    if p_tier <= 0 or start_copies <= 0 or start_tier_total <= 0:
        return 0.0
    slots_total = (gold // max(set_data.reroll_cost, 1)) * SHOP_SLOTS

    successes = 0
    for _ in range(iterations):
        copies = start_copies
        tier_total = start_tier_total
        hits = 0
        for _ in range(slots_total):
            if hits >= copies_needed:
                break
            if rng.random() >= p_tier:
                continue
            if rng.random() < copies / tier_total:
                hits += 1
                copies -= 1
                tier_total -= 1
                if copies <= 0:
                    break
        if hits >= copies_needed:
            successes += 1
    return successes / iterations
