"""Parser for Cube Cobra plain text exports.

Format (one card per line, sections delimited by `# section_name`):

    # mainboard
    Card Name 1
    Card Name 2
    ...

Handles Windows line endings, blank lines, and section headers.
"""

from __future__ import annotations

from pathlib import Path


def parse_cube_cobra_txt(path: Path) -> list[str]:
    """Parse a Cube Cobra text export, returning a list of card names.

    Strips section headers (`# mainboard`), blank lines, and whitespace.
    Returns names in their original order, including any duplicates.
    """
    names: list[str] = []
    with path.open(encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()  # strip handles both \n and \r\n
            if not line:
                continue
            if line.startswith("#"):
                continue
            names.append(line)
    return names


def deduplicate_names(names: list[str]) -> tuple[list[str], list[str]]:
    """Remove duplicate card names, preserving first-occurrence order.

    Returns (deduplicated_list, list_of_names_that_had_duplicates).
    The second list is for reporting — useful for showing the user what
    was dedup'd. Each name appears once in the second list regardless of
    how many extra copies it had.
    """
    seen: set[str] = set()
    deduped: list[str] = []
    duplicates_found: list[str] = []
    duplicates_seen: set[str] = set()

    for name in names:
        if name in seen:
            if name not in duplicates_seen:
                duplicates_found.append(name)
                duplicates_seen.add(name)
            continue
        seen.add(name)
        deduped.append(name)

    return deduped, duplicates_found
