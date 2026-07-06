"""Pure domain models.

This module must stay free of Qt, network and file I/O so that the whole
`core` package can be unit-tested and reused (CLI, web, bots...) as-is.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional


class Role(str, Enum):
    """Importance of a unit inside a target composition."""

    CARRY = "carry"
    CORE = "core"
    FLEX = "flex"


@dataclass(frozen=True)
class Champion:
    """A champion as defined by the current set's static data."""

    id: str                      # canonical id, e.g. CDragon apiName "TFT17_Ahri"
    name: str                    # display name, e.g. "Ahri"
    cost: int                    # shop tier, 1..5
    traits: tuple[str, ...] = ()


@dataclass(frozen=True)
class Trait:
    id: str
    name: str
    breakpoints: tuple[int, ...] = ()


@dataclass
class SetData:
    """Static data for one set + patch: champions, pool sizes and shop odds.

    ``pool_sizes`` maps cost -> copies of EACH champion of that cost in the
    shared pool. ``shop_odds`` maps player level -> {cost: probability 0..1}
    that a single shop slot rolls that cost tier. Both change between sets
    (and sometimes between patches), which is why they live in data files
    instead of code — see ``data/local/shop_odds.set17.json``.
    """

    set_id: str
    patch: str
    champions: dict[str, Champion] = field(default_factory=dict)
    traits: dict[str, Trait] = field(default_factory=dict)
    pool_sizes: dict[int, int] = field(default_factory=dict)
    shop_odds: dict[int, dict[int, float]] = field(default_factory=dict)
    xp_to_next_level: dict[int, int] = field(default_factory=dict)
    reroll_cost: int = 2

    # -- lookups ----------------------------------------------------------
    def champions_of_cost(self, cost: int) -> list[Champion]:
        return [c for c in self.champions.values() if c.cost == cost]

    def get(self, champion_id: str) -> Optional[Champion]:
        return self.champions.get(champion_id)

    def by_name(self, name: str) -> Optional[Champion]:
        needle = name.strip().lower()
        for champ in self.champions.values():
            if champ.name.lower() == needle or champ.id.lower() == needle:
                return champ
        return None


@dataclass(frozen=True)
class CompUnit:
    """One unit inside a (meta) composition."""

    champion_id: str                       # id or display name; resolved later
    role: Role = Role.FLEX
    items: tuple[str, ...] = ()
    position: Optional[tuple[int, int]] = None  # (row, col); row 0 = front line


@dataclass(frozen=True)
class MetaComp:
    """A target composition, typically fetched from a comps provider."""

    id: str
    name: str
    units: tuple[CompUnit, ...] = ()
    patch: str = ""
    avg_place: Optional[float] = None
    play_rate: Optional[float] = None
    source: str = "local"

    def unit_ids(self) -> set[str]:
        return {u.champion_id for u in self.units}

    def role_of(self, champion_id: str) -> Optional[Role]:
        for unit in self.units:
            if unit.champion_id == champion_id:
                return unit.role
        return None


@dataclass
class GameState:
    """Everything the app knows about the current match.

    ``owned`` counts raw copies you hold (a 2-star counts as 3 copies).
    ``taken_by_others`` is scouting info: copies you have seen on enemy
    boards/benches, which are removed from the shared pool.
    """

    level: int = 1
    gold: int = 0
    xp: int = 0
    stage: int = 1
    round: int = 1
    health: int = 100
    streak: int = 0                                   # >0 win streak, <0 loss streak
    owned: dict[str, int] = field(default_factory=dict)
    taken_by_others: dict[str, int] = field(default_factory=dict)
    shop: list[Optional[str]] = field(default_factory=lambda: [None] * 5)

    def copies_out_of_pool(self, champion_id: str) -> int:
        return self.owned.get(champion_id, 0) + self.taken_by_others.get(champion_id, 0)

    def copy(self) -> "GameState":
        return replace(
            self,
            owned=dict(self.owned),
            taken_by_others=dict(self.taken_by_others),
            shop=list(self.shop),
        )


@dataclass(frozen=True)
class GameSnapshot:
    """Partial observation produced by a :class:`~tft_companion.game.source.GameDataSource`.

    Every field is optional: sources report only what they can actually see,
    and the tracker merges snapshots from several sources into a GameState.
    """

    source: str
    level: Optional[int] = None
    gold: Optional[int] = None
    stage: Optional[int] = None
    round: Optional[int] = None
    health: Optional[int] = None
    streak: Optional[int] = None
    shop: Optional[list[Optional[str]]] = None
