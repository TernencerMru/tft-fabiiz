"""Provider contracts and shared HTTP plumbing.

Two independent axes of data:

* :class:`StaticDataProvider` — champions/traits of the current set
  (CommunityDragon, Data Dragon...).
* :class:`CompProvider` — meta compositions (local JSON, MetaTFT...).

The UI and services only ever see these protocols, so swapping or adding a
source never touches anything above this layer.
"""
from __future__ import annotations

from typing import Any, Protocol

import requests

from ...core.models import Champion, MetaComp, Trait

USER_AGENT = "tft-companion/0.1 (personal learning project)"


class ProviderError(RuntimeError):
    """Raised when a provider cannot deliver usable data."""


def http_get_json(url: str, timeout: float = 15.0) -> Any:
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise ProviderError(f"HTTP error fetching {url}: {exc}") from exc
    except ValueError as exc:
        raise ProviderError(f"Non-JSON response from {url}") from exc


class StaticDataProvider(Protocol):
    name: str

    def fetch_static(self) -> tuple[str, dict[str, Champion], dict[str, Trait]]:
        """Return ``(set_id, champions_by_id, traits_by_id)``."""
        ...


class CompProvider(Protocol):
    name: str

    def fetch_comps(self) -> list[MetaComp]:
        ...
