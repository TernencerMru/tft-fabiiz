"""Composition providers.

:class:`LocalJsonCompProvider` is the default: it reads a hand-editable JSON
(see ``data/local/comps.sample.json``) so the app works offline and you own
the schema. Every remote provider must normalize into that same schema.

:class:`MetaTFTCompProvider` is a best-effort adapter. MetaTFT has NO public,
documented API: the endpoints its site uses internally change without notice
and their terms should be respected — cache aggressively, identify yourself
with a User-Agent, and treat failures as expected. The robust long-term
alternative is computing comp stats yourself from the official Riot Match API
(developer.riotgames.com) with your own API key.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ...core.models import CompUnit, MetaComp, Role
from ..cache import JsonDiskCache
from .base import ProviderError, http_get_json


def _parse_units(raw_units: list[dict[str, Any]]) -> tuple[CompUnit, ...]:
    units: list[CompUnit] = []
    for u in raw_units:
        champ = u.get("id") or u.get("name")
        if not champ:
            continue
        pos = u.get("position")
        position = (int(pos[0]), int(pos[1])) if isinstance(pos, (list, tuple)) and len(pos) == 2 else None
        try:
            role = Role(str(u.get("role", "flex")).lower())
        except ValueError:
            role = Role.FLEX
        units.append(CompUnit(
            champion_id=str(champ),
            role=role,
            items=tuple(u.get("items") or ()),
            position=position,
        ))
    return tuple(units)


def parse_comps_document(doc: dict[str, Any], source: str) -> list[MetaComp]:
    """Parse the canonical comps schema (the one in comps.sample.json)."""
    comps: list[MetaComp] = []
    for c in doc.get("comps", []):
        units = _parse_units(c.get("units", []))
        if not units:
            continue
        comps.append(MetaComp(
            id=str(c.get("id") or c.get("name") or f"comp{len(comps)}"),
            name=str(c.get("name") or c.get("id") or "Sin nombre"),
            units=units,
            patch=str(doc.get("patch", "")),
            avg_place=c.get("avg_place"),
            play_rate=c.get("play_rate"),
            source=source,
        ))
    return comps


class LocalJsonCompProvider:
    name = "Local (JSON)"

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def fetch_comps(self) -> list[MetaComp]:
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Cannot read comps file {self.path}: {exc}") from exc
        comps = parse_comps_document(doc, source=self.name)
        if not comps:
            raise ProviderError(f"{self.path} contains no valid comps")
        return comps


class MetaTFTCompProvider:
    """UNOFFICIAL. Point ``url`` at the current comps endpoint you observe in
    the Network tab of metatft.com, then adapt :meth:`_normalize` to its
    shape. Shipping-quality parsing of an undocumented API is by definition
    a moving target, so this class fails loudly instead of guessing."""

    name = "MetaTFT (no oficial)"

    def __init__(self, url: str, cache: Optional[JsonDiskCache] = None,
                 cache_ttl: int = 3600) -> None:
        self.url = url
        self.cache = cache
        self.cache_ttl = cache_ttl

    def fetch_comps(self) -> list[MetaComp]:
        raw = None
        if self.cache:
            raw = self.cache.get(f"metatft:{self.url}", max_age=self.cache_ttl)
        if raw is None:
            raw = http_get_json(self.url)
            if self.cache:
                self.cache.set(f"metatft:{self.url}", raw)
        comps = self._normalize(raw)
        if not comps:
            raise ProviderError(
                "No pude interpretar la respuesta de MetaTFT. Su API interna no es "
                "pública y cambia sin aviso: inspecciona el endpoint actual en la "
                "pestaña Network del navegador y adapta MetaTFTCompProvider._normalize()."
            )
        return comps

    def _normalize(self, raw: Any) -> list[MetaComp]:
        # Best effort: accept our canonical schema directly, or a top-level
        # {"results": {...canonical...}} wrapper. Anything else -> [].
        if isinstance(raw, dict):
            if "comps" in raw:
                return parse_comps_document(raw, source=self.name)
            inner = raw.get("results")
            if isinstance(inner, dict) and "comps" in inner:
                return parse_comps_document(inner, source=self.name)
        return []
