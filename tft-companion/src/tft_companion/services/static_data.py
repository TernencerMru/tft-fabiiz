"""Assemble the SetData the whole app runs on.

Champions/traits come from a network provider (CommunityDragon); pool sizes
and shop odds come from the bundled per-set JSON (Riot does not publish them
via any API — they are patch-note / in-game-UI knowledge). If the network is
down the app still opens with an empty roster and a visible warning, because
a planning tool that refuses to start offline is a bad planning tool.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import AppConfig
from ..core.models import MetaComp, SetData, CompUnit
from ..data.cache import JsonDiskCache
from ..data.providers.base import ProviderError
from ..data.providers.cdragon import CDragonProvider

LOCAL_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "local"


def load_local_odds(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["pool_sizes"] = {int(k): int(v) for k, v in doc.get("pool_sizes", {}).items()}
    doc["shop_odds"] = {
        int(level): {cost + 1: pct / 100.0 for cost, pct in enumerate(row)}
        for level, row in doc.get("shop_odds", {}).items()
    }
    doc["xp_to_next_level"] = {
        int(k): int(v) for k, v in doc.get("xp_to_next_level", {}).items()
    }
    return doc


def load_set_data(config: AppConfig, cache: JsonDiskCache) -> tuple[SetData, list[str]]:
    """Returns (set_data, warnings)."""
    warnings: list[str] = []
    odds_doc = load_local_odds(config.local_odds_file)

    champions, traits, set_id = {}, {}, str(odds_doc.get("set", "?"))
    try:
        provider = CDragonProvider(cache=cache, url_template=config.cdragon_url)
        set_id, champions, traits = provider.fetch_static()
    except ProviderError as exc:
        warnings.append(
            f"Sin datos de campeones (CDragon): {exc}. "
            "La app funciona, pero añade conexión o revisa la URL."
        )

    if set_id != str(odds_doc.get("set")):
        warnings.append(
            f"Los campeones son del Set {set_id} pero el fichero de odds es del "
            f"Set {odds_doc.get('set')} — actualiza {config.local_odds_file.name}."
        )

    set_data = SetData(
        set_id=set_id,
        patch=str(odds_doc.get("patch", "?")),
        champions=champions,
        traits=traits,
        pool_sizes=odds_doc["pool_sizes"],
        shop_odds=odds_doc["shop_odds"],
        xp_to_next_level=odds_doc["xp_to_next_level"],
        reroll_cost=int(odds_doc.get("reroll_cost", 2)),
    )
    return set_data, warnings


def resolve_comp(set_data: SetData, comp: MetaComp) -> tuple[MetaComp, list[str]]:
    """Map unit names/ids in a comp to canonical champion ids of the set.

    Comps files may reference units by display name; this normalizes them so
    the rest of the app can rely on ids. Unknown units are kept (with a
    warning) so a stale comps file degrades gracefully.
    """
    warnings: list[str] = []
    resolved: list[CompUnit] = []
    for unit in comp.units:
        champ = set_data.get(unit.champion_id) or set_data.by_name(unit.champion_id)
        if champ is None:
            warnings.append(f"«{unit.champion_id}» no existe en el Set {set_data.set_id}")
            resolved.append(unit)
        else:
            resolved.append(CompUnit(
                champion_id=champ.id,
                role=unit.role,
                items=unit.items,
                position=unit.position,
            ))
    return (
        MetaComp(
            id=comp.id, name=comp.name, units=tuple(resolved), patch=comp.patch,
            avg_place=comp.avg_place, play_rate=comp.play_rate, source=comp.source,
        ),
        warnings,
    )
