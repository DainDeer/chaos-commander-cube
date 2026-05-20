"""Tests for the Cube Cobra parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtgccc.cube_cobra import deduplicate_names, parse_cube_cobra_txt


def test_parses_simple_export(tmp_path: Path) -> None:
    """Basic export with mainboard section."""
    file = tmp_path / "cube.txt"
    file.write_text(
        "# mainboard\n"
        "Lightning Bolt\n"
        "Counterspell\n"
        "Soul Warden\n"
    )
    result = parse_cube_cobra_txt(file)
    assert result == ["Lightning Bolt", "Counterspell", "Soul Warden"]


def test_handles_windows_line_endings(tmp_path: Path) -> None:
    """Cube Cobra exports use \\r\\n on Windows."""
    file = tmp_path / "cube.txt"
    file.write_bytes(
        b"# mainboard\r\nLightning Bolt\r\nCounterspell\r\n"
    )
    result = parse_cube_cobra_txt(file)
    assert result == ["Lightning Bolt", "Counterspell"]


def test_skips_blank_lines(tmp_path: Path) -> None:
    """Blank lines between cards are ignored."""
    file = tmp_path / "cube.txt"
    file.write_text(
        "# mainboard\n"
        "Lightning Bolt\n"
        "\n"
        "Counterspell\n"
        "\n"
        "\n"
        "Soul Warden\n"
    )
    result = parse_cube_cobra_txt(file)
    assert result == ["Lightning Bolt", "Counterspell", "Soul Warden"]


def test_skips_multiple_section_headers(tmp_path: Path) -> None:
    """Multi-section exports (rare but possible)."""
    file = tmp_path / "cube.txt"
    file.write_text(
        "# mainboard\n"
        "Lightning Bolt\n"
        "# maybeboard\n"
        "Soul Warden\n"
    )
    result = parse_cube_cobra_txt(file)
    # Maybeboard contents are included; we don't separate sections (for now).
    assert result == ["Lightning Bolt", "Soul Warden"]


def test_handles_special_characters_in_names(tmp_path: Path) -> None:
    """Cards with apostrophes, commas, hyphens, accents."""
    file = tmp_path / "cube.txt"
    file.write_text(
        "# mainboard\n"
        "Zndrsplt, Eye of Wisdom\n"
        "Lim-Dûl's Vault\n"
        "Æther Vial\n"
    )
    result = parse_cube_cobra_txt(file)
    assert result == [
        "Zndrsplt, Eye of Wisdom",
        "Lim-Dûl's Vault",
        "Æther Vial",
    ]


def test_deduplicate_no_duplicates() -> None:
    names = ["Lightning Bolt", "Counterspell", "Soul Warden"]
    deduped, dupes = deduplicate_names(names)
    assert deduped == names
    assert dupes == []


def test_deduplicate_with_duplicates() -> None:
    names = ["Lightning Bolt", "Counterspell", "Lightning Bolt", "Soul Warden", "Counterspell"]
    deduped, dupes = deduplicate_names(names)
    assert deduped == ["Lightning Bolt", "Counterspell", "Soul Warden"]
    assert set(dupes) == {"Lightning Bolt", "Counterspell"}


def test_deduplicate_preserves_first_occurrence_order() -> None:
    names = ["Counterspell", "Lightning Bolt", "Counterspell", "Soul Warden"]
    deduped, _ = deduplicate_names(names)
    assert deduped == ["Counterspell", "Lightning Bolt", "Soul Warden"]


def test_deduplicate_each_dup_reported_once_regardless_of_copies() -> None:
    """A card appearing 5 times is reported as 1 duplicate, not 4."""
    names = ["Lightning Bolt"] * 5 + ["Counterspell"]
    deduped, dupes = deduplicate_names(names)
    assert deduped == ["Lightning Bolt", "Counterspell"]
    assert dupes == ["Lightning Bolt"]