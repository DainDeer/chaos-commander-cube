"""Tests for the manifest schema and helpers."""

from __future__ import annotations

from pathlib import Path

from ccc.manifest import (
    CardEntry,
    CubeManifest,
    load_manifest,
    make_card_id,
    save_manifest,
)


def test_make_card_id_simple() -> None:
    assert make_card_id("Soul Warden", "TMP") == "soul_warden_tmp"


def test_make_card_id_with_punctuation() -> None:
    assert make_card_id("Zndrsplt, Eye of Wisdom", "BBD") == "zndrsplt_eye_of_wisdom_bbd"


def test_make_card_id_with_apostrophe() -> None:
    assert make_card_id("Lim-Dûl's Vault", "ALL") == "lim_dul_s_vault_all"


def test_make_card_id_with_ae_ligature() -> None:
    assert make_card_id("Æther Vial", "DST") == "aether_vial_dst"


def test_card_entry_round_trips(tmp_path: Path) -> None:
    """Saving and re-loading a manifest preserves all data."""
    manifest = CubeManifest(
        cube_id="test_cube",
        name="Test Cube",
        color_identity=["U", "B", "R"],
        version="v1",
        cards=[
            CardEntry(
                id="lightning_bolt_lea",
                name="Lightning Bolt",
                scryfall_id="abc-123",
                set_code="LEA",
                image_url="https://example.com/bolt.jpg",
                color_identity=["R"],
                cmc=1.0,
                type_line="Instant",
                is_land=False,
                is_basic_land=False,
                tags=["burn", "iconic", "set:lea"],
            )
        ],
    )

    path = tmp_path / "manifest.json"
    save_manifest(manifest, path)
    loaded = load_manifest(path)

    assert loaded == manifest


def test_manifest_indexing() -> None:
    """by_id and by_name lookup helpers work correctly."""
    manifest = CubeManifest(
        cube_id="test",
        name="Test",
        color_identity=["U", "B", "R"],
        version="v1",
        cards=[
            CardEntry(
                id="lightning_bolt_lea",
                name="Lightning Bolt",
                scryfall_id="abc",
                set_code="LEA",
                image_url="https://example.com/bolt.jpg",
                color_identity=["R"],
                cmc=1.0,
                type_line="Instant",
                is_land=False,
                is_basic_land=False,
            ),
            CardEntry(
                id="counterspell_lea",
                name="Counterspell",
                scryfall_id="def",
                set_code="LEA",
                image_url="https://example.com/counter.jpg",
                color_identity=["U"],
                cmc=2.0,
                type_line="Instant",
                is_land=False,
                is_basic_land=False,
            ),
        ],
    )

    by_id = manifest.by_id()
    assert by_id["lightning_bolt_lea"].name == "Lightning Bolt"

    by_name = manifest.by_name()
    assert by_name["Counterspell"].cmc == 2.0
