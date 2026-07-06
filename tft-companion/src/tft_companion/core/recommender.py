"""Purchase recommendation engine.

Design: Strategy pattern. Each :class:`Scorer` evaluates one independent
signal (role in the target comp, upgrade proximity, trait synergy, pool
scarcity...) and returns points plus a human-readable reason. The engine
composes any number of scorers, sums their contributions per shop unit and
returns an explainable ranking — every recommendation carries the *why*.

Adding a new signal = writing one small class. No engine changes needed::

    engine = RecommendationEngine(default_scorers() + [MyItemHolderScorer()])
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, Sequence

from . import economy, odds
from .models import Champion, GameState, MetaComp, Role, SetData


@dataclass(frozen=True)
class ScoreContext:
    state: GameState
    set_data: SetData
    target: Optional[MetaComp]
    champion: Champion


class Scorer(Protocol):
    """One scoring signal. Return ``None`` when the signal does not apply."""

    def score(self, ctx: ScoreContext) -> Optional[tuple[float, str]]:
        ...


# ---------------------------------------------------------------------------
# Built-in scorers
# ---------------------------------------------------------------------------

class RoleScorer:
    """Is the unit part of the target comp, and how important is it?"""

    POINTS = {Role.CARRY: 30.0, Role.CORE: 20.0, Role.FLEX: 10.0}
    LABEL = {Role.CARRY: "carry", Role.CORE: "pieza core", Role.FLEX: "flex"}

    def score(self, ctx: ScoreContext) -> Optional[tuple[float, str]]:
        if ctx.target is None:
            return None
        role = ctx.target.role_of(ctx.champion.id)
        if role is None:
            return None
        return self.POINTS[role], f"Es {self.LABEL[role]} de «{ctx.target.name}»"


class UpgradeProximityScorer:
    """Copies you already hold: being 1 copy away from a star-up is huge."""

    def score(self, ctx: ScoreContext) -> Optional[tuple[float, str]]:
        copies = ctx.state.owned.get(ctx.champion.id, 0)
        if copies <= 0:
            return None
        if copies % 3 == 2:
            return 25.0, f"Tienes {copies} copias: una más completa una subida de estrella"
        return 8.0, f"Ya tienes {copies} copia(s)"


class TraitSynergyScorer:
    """Shares traits with the target comp even if it's not listed in it."""

    POINTS_PER_TRAIT = 3.0
    CAP = 9.0

    def score(self, ctx: ScoreContext) -> Optional[tuple[float, str]]:
        if ctx.target is None:
            return None
        comp_traits: set[str] = set()
        for unit in ctx.target.units:
            champ = ctx.set_data.get(unit.champion_id)
            if champ:
                comp_traits.update(champ.traits)
        shared = sorted(comp_traits.intersection(ctx.champion.traits))
        if not shared:
            return None
        pts = min(len(shared) * self.POINTS_PER_TRAIT, self.CAP)
        return pts, "Comparte sinergias: " + ", ".join(shared)


class ScarcityScorer:
    """Contested units you need: if few copies remain, it's now or never."""

    THRESHOLD = 4

    def score(self, ctx: ScoreContext) -> Optional[tuple[float, str]]:
        if ctx.target is None or ctx.target.role_of(ctx.champion.id) is None:
            return None
        left = odds.champion_copies_remaining(ctx.set_data, ctx.state, ctx.champion.id)
        if 0 < left <= self.THRESHOLD:
            return 10.0, f"Solo quedan {left} copias en el pool"
        return None


def default_scorers() -> list[Scorer]:
    return [RoleScorer(), UpgradeProximityScorer(), TraitSynergyScorer(), ScarcityScorer()]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Recommendation:
    champion_id: str
    name: str
    cost: int
    score: float
    slots: tuple[int, ...]            # shop slot indexes where it appears
    reasons: tuple[str, ...]
    affordable: bool


@dataclass
class RecommendationEngine:
    scorers: Sequence[Scorer] = field(default_factory=default_scorers)

    def recommend_shop(
        self,
        state: GameState,
        set_data: SetData,
        target: Optional[MetaComp],
    ) -> list[Recommendation]:
        """Rank the units currently visible in the shop."""
        by_champ: dict[str, list[int]] = {}
        for idx, champ_id in enumerate(state.shop):
            if champ_id:
                by_champ.setdefault(champ_id, []).append(idx)

        recs: list[Recommendation] = []
        for champ_id, slots in by_champ.items():
            champ = set_data.get(champ_id)
            if champ is None:
                continue
            ctx = ScoreContext(state=state, set_data=set_data, target=target, champion=champ)
            total = 0.0
            reasons: list[str] = []
            for scorer in self.scorers:
                result = scorer.score(ctx)
                if result is None:
                    continue
                points, reason = result
                total += points
                reasons.append(reason)
            if total <= 0:
                continue
            recs.append(Recommendation(
                champion_id=champ.id,
                name=champ.name,
                cost=champ.cost,
                score=round(total, 1),
                slots=tuple(slots),
                reasons=tuple(reasons),
                affordable=champ.cost <= state.gold,
            ))
        recs.sort(key=lambda r: (r.score, -r.cost), reverse=True)
        return recs

    def roll_or_level(
        self,
        state: GameState,
        set_data: SetData,
        target: Optional[MetaComp],
    ) -> list[str]:
        """Coarse "roll vs level vs save" guidance. Honest heuristics."""
        tips: list[str] = []
        if target is None:
            tips.append("Selecciona una composición objetivo para recibir consejos de roll/level.")
            return tips

        total_units = len(target.units) or 1
        owned_units = sum(1 for u in target.units if state.owned.get(u.champion_id, 0) > 0)
        completeness = owned_units / total_units
        tips.append(f"Progreso de la comp: {owned_units}/{total_units} unidades encontradas.")

        # Does the comp need high-cost units you can barely see at this level?
        max_needed_cost = 0
        for unit in target.units:
            champ = set_data.get(unit.champion_id)
            if champ:
                max_needed_cost = max(max_needed_cost, champ.cost)
        p_top = set_data.shop_odds.get(state.level, {}).get(max_needed_cost, 0.0)

        if max_needed_cost >= 4 and p_top < 0.15 and state.level < 8:
            gold_lvl = economy.gold_to_next_level(state, set_data)
            extra = f" (~{gold_lvl} de oro)" if gold_lvl else ""
            tips.append(
                f"La comp depende de unidades de coste {max_needed_cost} y a nivel "
                f"{state.level} solo tienes {p_top:.0%} por slot: prioriza subir de nivel{extra}."
            )
        elif state.gold >= 50 and completeness < 0.7:
            tips.append(
                "Estás sobre 50 de oro con la comp incompleta: puedes rollear el "
                "excedente sin perder interés."
            )
        elif state.gold < 50 and state.health > 40:
            tips.append("Vida estable: sigue haciendo economía hasta 50 antes de rollear fuerte.")

        if state.health <= 30:
            tips.append("Con la vida al límite, rollear para estabilizar pesa más que la economía.")
        return tips
