"""CommunityDragon static data provider.

CDragon mirrors the game files and publishes a consolidated TFT JSON at::

    https://raw.communitydragon.org/latest/cdragon/tft/<locale>.json

It contains every set's champions (apiName, name, cost, traits) and traits.
This is the recommended source for static data: no API key, always tracks
"latest", and stays in sync with the live patch. Riot's Data Dragon
(``ddragon.leagueoflegends.com``) is a valid alternative with a similar
shape but usually lags a bit and carries less TFT detail.
"""
from __future__ import annotations

from typing import Any, Optional

from ...core.models import Champion, Trait
from ..cache import JsonDiskCache
from .base import ProviderError, http_get_json

DEFAULT_URL = "https://raw.communitydragon.org/latest/cdragon/tft/{locale}.json"


class CDragonProvider:
    name = "CommunityDragon"

    def __init__(
        self,
        cache: Optional[JsonDiskCache] = None,
        locale: str = "en_us",
        url_template: str = DEFAULT_URL,
    ) -> None:
        self.cache = cache
        self.url = url_template.format(locale=locale)

    # ------------------------------------------------------------------
    def fetch_static(self) -> tuple[str, dict[str, Champion], dict[str, Trait]]:
        raw = self._raw()
        set_entry = self._pick_current_set(raw)
        if set_entry is None:
            raise ProviderError("CDragon payload had no usable setData entry")

        champions: dict[str, Champion] = {}
        for item in set_entry.get("champions", []):
            cost = item.get("cost")
            traits = tuple(item.get("traits") or ())
            api_name = item.get("apiName") or item.get("characterName")
            name = item.get("name") or api_name
            # cost 1..5 + at least one trait filters out minions/props/specials
            if not api_name or not traits or not isinstance(cost, int) or not 1 <= cost <= 5:
                continue
            champions[api_name] = Champion(id=api_name, name=name, cost=cost, traits=traits)

        traits: dict[str, Trait] = {}
        for item in set_entry.get("traits", []):
            api_name = item.get("apiName")
            if not api_name:
                continue
            breakpoints = tuple(
                eff.get("minUnits") for eff in item.get("effects", [])
                if isinstance(eff.get("minUnits"), int)
            )
            traits[api_name] = Trait(
                id=api_name,
                name=item.get("name") or api_name,
                breakpoints=breakpoints,
            )

        set_id = str(set_entry.get("number", "?"))
        if not champions:
            raise ProviderError(f"No champions parsed for set {set_id}")
        return set_id, champions, traits

    # ------------------------------------------------------------------
    def _raw(self) -> dict[str, Any]:
        if self.cache:
            cached = self.cache.get(self.url)
            if cached is not None:
                return cached
        data = http_get_json(self.url)
        if self.cache:
            self.cache.set(self.url, data)
        return data

    @staticmethod
    def _pick_current_set(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Latest set = highest ``number``; among variants (tutorial/revival
        mutators share the number) keep the one with the largest roster."""
        entries = [e for e in raw.get("setData", []) if e.get("champions")]
        if not entries:
            return None
        top = max(e.get("number", 0) for e in entries)
        candidates = [e for e in entries if e.get("number", 0) == top]
        return max(candidates, key=lambda e: len(e.get("champions", [])))
