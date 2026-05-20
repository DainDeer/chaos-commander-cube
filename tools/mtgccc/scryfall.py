"""Scryfall API client.

Rate-limited (10 req/sec per Scryfall's API guidelines) with persistent
local caching to disk. Re-running the manifest builder shouldn't re-hit the
API for cards we've already resolved.

Scryfall API docs: https://scryfall.com/docs/api
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

# Scryfall asks for a User-Agent identifying the application. Be polite.
USER_AGENT = "ChaosCommanderCube/0.1 (https://github.com/<your-github>/chaos-commander-cube)"

# Scryfall guideline: 50-100ms between requests. 100ms is the safe choice.
MIN_REQUEST_INTERVAL_SEC = 0.1


@dataclass
class ScryfallCard:
    """A subset of Scryfall card data, just the fields we care about.

    Scryfall's full card object has 30+ fields; we only need these for the
    manifest. If we ever need more (oracle_text for mechanic tagging, etc),
    add them here.
    """

    scryfall_id: str
    name: str
    set_code: str  # Scryfall returns lowercase; we upper() it
    color_identity: list[str]
    cmc: float
    type_line: str
    image_url: str
    oracle_text: str  # For mechanic auto-tagging later

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> ScryfallCard:
        """Parse a Scryfall card object from API JSON.

        Handles single-faced and double-faced cards. For DFCs, uses the front
        face's image_uris (the top-level image_uris is missing on DFCs).
        """
        # Image URL handling: single-faced cards have top-level image_uris,
        # double-faced cards have card_faces[i].image_uris instead.
        image_url = ""
        if "image_uris" in data:
            image_url = data["image_uris"].get("normal", "")
        elif "card_faces" in data and data["card_faces"]:
            front_face = data["card_faces"][0]
            if "image_uris" in front_face:
                image_url = front_face["image_uris"].get("normal", "")

        # Oracle text: DFCs combine both faces' text with "\n//\n" separator.
        oracle_text = data.get("oracle_text", "")
        if not oracle_text and "card_faces" in data:
            oracle_text = "\n//\n".join(
                face.get("oracle_text", "") for face in data["card_faces"]
            )

        # cmc on DFCs is the front face's mana value.
        cmc = float(data.get("cmc", 0.0))

        return cls(
            scryfall_id=data["id"],
            name=data["name"],
            set_code=data["set"].upper(),
            color_identity=data.get("color_identity", []),
            cmc=cmc,
            type_line=data.get("type_line", ""),
            image_url=image_url,
            oracle_text=oracle_text,
        )


class ScryfallClient:
    """Rate-limited, caching Scryfall API client.

    Usage:
        client = ScryfallClient(cache_dir=Path(".scryfall_cache"))
        card = client.get_card_by_name("Soul Warden")
        print(card.set_code)  # "TMP"
    """

    BASE_URL = "https://api.scryfall.com"

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_request_time: float = 0.0
        self._client = httpx.Client(
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ScryfallClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_card_by_name(self, name: str) -> ScryfallCard | None:
        """Resolve a card by name. Returns None if not found.

        Uses Scryfall's /cards/named?exact= endpoint. Caches the response
        locally so subsequent calls for the same name don't hit the API.
        """
        cache_key = self._cache_key("named", name)
        cached = self._read_cache(cache_key)
        if cached is not None:
            if cached.get("_not_found"):
                return None
            return ScryfallCard.from_api_response(cached)

        # Cache miss — hit the API.
        self._rate_limit_wait()
        response = self._client.get(
            f"{self.BASE_URL}/cards/named",
            params={"exact": name},
        )

        if response.status_code == 404:
            # Card not found. Cache the negative result so we don't re-query.
            self._write_cache(cache_key, {"_not_found": True, "query_name": name})
            return None

        response.raise_for_status()
        data = response.json()
        self._write_cache(cache_key, data)
        return ScryfallCard.from_api_response(data)

    def _rate_limit_wait(self) -> None:
        """Sleep just long enough to stay under Scryfall's rate limit."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL_SEC:
            time.sleep(MIN_REQUEST_INTERVAL_SEC - elapsed)
        self._last_request_time = time.monotonic()

    def _cache_key(self, endpoint: str, param: str) -> str:
        """Generate a filesystem-safe cache filename for a query."""
        hashed = hashlib.sha256(f"{endpoint}:{param}".encode()).hexdigest()[:16]
        return f"{endpoint}_{hashed}"

    def _read_cache(self, key: str) -> dict[str, Any] | None:
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            with path.open(encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # Corrupt cache entry — ignore and re-fetch.
            return None

    def _write_cache(self, key: str, data: dict[str, Any]) -> None:
        path = self.cache_dir / f"{key}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f)
