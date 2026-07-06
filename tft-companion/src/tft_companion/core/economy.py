"""Economy math and advisory heuristics. Pure functions only.

The numeric constants that Riot tunes per set (streak gold, XP thresholds)
should ultimately come from :class:`~tft_companion.core.models.SetData`;
the module-level defaults here match the long-standing values and are used
as fallback when the data file does not provide them.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Optional

from .models import GameState, SetData

BASE_INCOME = 5
MAX_INTEREST = 5
XP_PER_PURCHASE = 4
GOLD_PER_XP_PURCHASE = 4

# streak length -> bonus gold (win or loss). Verify per set.
_STREAK_GOLD = {0: 0, 1: 0, 2: 1, 3: 1, 4: 2}
_STREAK_GOLD_CAP = 3  # for streaks of 5+


def interest(gold: int) -> int:
    """+1 gold per 10 banked, capped at :data:`MAX_INTEREST`."""
    return min(max(gold, 0) // 10, MAX_INTEREST)


def streak_gold(streak: int) -> int:
    length = abs(streak)
    if length >= 5:
        return _STREAK_GOLD_CAP
    return _STREAK_GOLD.get(length, 0)


def round_income(gold: int, streak: int, base: int = BASE_INCOME) -> int:
    """Passive gold you will receive at the end of the current round."""
    return base + interest(gold) + streak_gold(streak)


def next_interest_breakpoint(gold: int) -> Optional[int]:
    """Gold missing to reach the next +1 interest tier (None if capped)."""
    if interest(gold) >= MAX_INTEREST:
        return None
    return ((gold // 10) + 1) * 10 - gold


def gold_to_next_level(state: GameState, set_data: SetData) -> Optional[int]:
    """Gold needed to buy XP up to the next level (None if table unknown)."""
    needed = set_data.xp_to_next_level.get(state.level)
    if not needed:
        return None
    missing = max(needed - state.xp, 0)
    purchases = ceil(missing / XP_PER_PURCHASE)
    return purchases * GOLD_PER_XP_PURCHASE


@dataclass(frozen=True)
class Advice:
    severity: str  # "info" | "warn" | "danger"
    text: str
    reason: str


def advise(state: GameState, set_data: SetData) -> list[Advice]:
    """Human-readable economy guidance. Heuristics, not gospel."""
    out: list[Advice] = []

    if state.health <= 30:
        out.append(Advice(
            "danger",
            "Vida crítica: prioriza estabilizar el tablero ya.",
            f"Con {state.health} HP, perder interés cuesta menos que perder la partida.",
        ))

    if state.gold >= 50:
        out.append(Advice(
            "info",
            "Interés máximo (+5). Todo lo que supere 50 es oro 'gratis' para gastar.",
            f"Tienes {state.gold} de oro; el interés no crece por encima de 50.",
        ))
    else:
        missing = next_interest_breakpoint(state.gold)
        if missing is not None and missing <= 4:
            out.append(Advice(
                "info",
                f"Te faltan {missing} de oro para el siguiente escalón de interés.",
                "Si puedes aguantar una ronda sin gastar, ese oro se paga solo.",
            ))

    lvl_gold = gold_to_next_level(state, set_data)
    if lvl_gold is not None:
        out.append(Advice(
            "info",
            f"Subir a nivel {state.level + 1} cuesta ~{lvl_gold} de oro en XP.",
            "4 de oro compran 4 de XP; el coste real depende de tu XP actual.",
        ))

    if abs(state.streak) >= 3:
        kind = "victorias" if state.streak > 0 else "derrotas"
        out.append(Advice(
            "info",
            f"Racha de {abs(state.streak)} {kind}: +{streak_gold(state.streak)} oro/ronda.",
            "Romper una racha larga tiene coste de oportunidad; decide con intención.",
        ))

    return out
