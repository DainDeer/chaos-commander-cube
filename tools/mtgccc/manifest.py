"""Manifest schema and load/save functions.

The manifest is the canonical source of truth for a cube. Every other tool
in the project reads from or writes to this format.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# Mana colors. Order matches MTG's WUBRG convention.
Color = Literal["W", "U", "B", "R", "G"]


class CardEntry(BaseModel):
    """A single card in a cube manifest.

    All Scryfall-derived fields are auto-populated by the build script.
    The `tags` field is hand-curated (with some auto-derived tags too).
    """

    # Stable identifier. Format: snake_case(name) + "_" + set_code.lower()
    # Example: "soul_warden_tmp"
    # Does NOT change across reprints — if we swap printings, scryfall_id and
    # set_code change but `id` stays put.
    id: str

    # Display name, exactly as Scryfall reports it (handles Æ, apostrophes, etc.)
    name: str

    # Scryfall's UUID for this specific printing. Useful for re-fetching data.
    scryfall_id: str

    # Set code, uppercase (e.g., "TMP", "M21", "MH3").
    set_code: str

    # URL to the card image. Initially Scryfall CDN; later replaced with R2 URL.
    image_url: str

    # Color identity (commander legality). Empty list = colorless.
    # NOT just "colors" — includes color symbols in rules text.
    color_identity: list[Color] = Field(default_factory=list)

    # Converted mana cost / mana value. For DFCs, this is the front face.
    cmc: float

    # Full type line as Scryfall reports it (e.g., "Creature — Human Cleric").
    type_line: str

    # Convenience flags derived from type_line. Set by builder.
    is_land: bool
    is_basic_land: bool

    # All tags applied to this card. Flat list of strings.
    # Conventions: "category:value" for grouped tags (e.g., "set:tempest"),
    # bare strings for ungrouped (e.g., "lifegain", "signature_card").
    tags: list[str] = Field(default_factory=list)


class CubeManifest(BaseModel):
    """A complete cube manifest.

    Top-level wrapper around the card list. Includes metadata for the cube
    itself (name, version) so seeds can be tied to specific versions.
    """

    # Short cube identifier matching the directory name (e.g., "nicol_bolas").
    cube_id: str

    # Human-readable cube name (e.g., "Nicol Bolas").
    name: str

    # Three-color identity of the cube (e.g., ["U", "B", "R"] for Grixis/Bolas).
    color_identity: list[Color]

    # Version string. Bumps when the card list changes meaningfully.
    # Affects seed reproducibility — seed X under v12 != seed X under v13.
    version: str

    # The actual cards.
    cards: list[CardEntry]

    def by_id(self) -> dict[str, CardEntry]:
        """Index cards by their stable id. Useful for lookups."""
        return {card.id: card for card in self.cards}

    def by_name(self) -> dict[str, CardEntry]:
        """Index cards by name. Note: names should be unique within a cube."""
        return {card.name: card for card in self.cards}


def load_manifest(path: Path) -> CubeManifest:
    """Load a manifest from disk."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return CubeManifest.model_validate(data)


def save_manifest(manifest: CubeManifest, path: Path) -> None:
    """Save a manifest to disk with pretty-printed JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(
            manifest.model_dump(),
            f,
            indent=2,
            ensure_ascii=False,
        )
        f.write("\n")  # POSIX: files end with newline


def make_card_id(name: str, set_code: str) -> str:
    """Generate a stable card id from name + set code.

    Strategy: lowercase + replace non-alphanumeric with underscore + dedupe
    underscores + append set code. Aims for human-readable + collision-free.

    Examples:
        ("Soul Warden", "TMP") -> "soul_warden_tmp"
        ("Æther Vial", "DST") -> "aether_vial_dst"
        ("Lim-Dûl's Vault", "ALL") -> "lim_dul_s_vault_all"
    """
    # Normalize unicode that Scryfall returns to ASCII-friendly forms.
    normalized = (
        name.lower()
        .replace("æ", "ae")
        .replace("û", "u")
        .replace("ü", "u")
        .replace("é", "e")
        .replace("ö", "o")
        .replace("á", "a")
        .replace("í", "i")
        .replace("ñ", "n")
    )

    # Replace non-alphanumeric with underscores.
    chars: list[str] = []
    prev_underscore = False
    for c in normalized:
        if c.isalnum():
            chars.append(c)
            prev_underscore = False
        elif not prev_underscore:
            chars.append("_")
            prev_underscore = True

    slug = "".join(chars).strip("_")
    return f"{slug}_{set_code.lower()}"
