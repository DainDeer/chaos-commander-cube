"""Build a cube manifest from a Cube Cobra text export.

Usage:
    python scripts/build_manifest.py \
        --cube nicol_bolas \
        --input ../cubes/nicol_bolas/cube_cobra_export.txt \
        --output ../cubes/nicol_bolas/manifest.json

The first run will be slow (~13 minutes for 8000 cards at Scryfall's polite
rate limit). Subsequent runs use a local cache and complete in seconds.
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from ccc.cube_cobra import deduplicate_names, parse_cube_cobra_txt
from ccc.manifest import (
    CardEntry,
    Color,
    CubeManifest,
    make_card_id,
    save_manifest,
)
from ccc.scryfall import ScryfallCard, ScryfallClient

console = Console()


def detect_land_flags(type_line: str) -> tuple[bool, bool]:
    """Return (is_land, is_basic_land) from a Scryfall type_line.

    Basic lands have "Basic Land" in their type. Non-basic lands have "Land"
    but not "Basic".
    """
    is_land = "Land" in type_line
    is_basic_land = "Basic Land" in type_line or "Basic Snow Land" in type_line
    return is_land, is_basic_land


def auto_tags_for_card(card: ScryfallCard) -> list[str]:
    """Generate auto-derived tags from Scryfall data.

    Currently just the set prefix tag. Future expansion: mechanic detection
    from oracle_text (cycling, flashback, etc.), creature type tags, etc.
    """
    tags: list[str] = []

    # Set tag: "set:tempest", "set:mh3", etc.
    tags.append(f"set:{card.set_code.lower()}")

    return tags


def card_entry_from_scryfall(scryfall_card: ScryfallCard) -> CardEntry:
    """Convert a Scryfall response into a CardEntry for the manifest."""
    is_land, is_basic_land = detect_land_flags(scryfall_card.type_line)

    return CardEntry(
        id=make_card_id(scryfall_card.name, scryfall_card.set_code),
        name=scryfall_card.name,
        scryfall_id=scryfall_card.scryfall_id,
        set_code=scryfall_card.set_code,
        image_url=scryfall_card.image_url,
        color_identity=[c for c in scryfall_card.color_identity if c in "WUBRG"],  # type: ignore[misc]
        cmc=scryfall_card.cmc,
        type_line=scryfall_card.type_line,
        is_land=is_land,
        is_basic_land=is_basic_land,
        tags=auto_tags_for_card(scryfall_card),
    )


@click.command()
@click.option(
    "--cube",
    required=True,
    help="Cube ID (matches cubes/<cube_id>/ directory name)",
)
@click.option(
    "--name",
    default=None,
    help="Human-readable cube name (defaults to title-cased cube ID)",
)
@click.option(
    "--colors",
    default="UBR",
    help="Color identity of the cube as a 3-letter string (default: UBR for Bolas)",
)
@click.option(
    "--version",
    default="v1",
    help="Cube version string (default: v1)",
)
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to Cube Cobra text export",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Path to write manifest JSON",
)
@click.option(
    "--cache-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path(".scryfall_cache"),
    help="Local cache directory for Scryfall API responses",
)
def main(
    cube: str,
    name: str | None,
    colors: str,
    version: str,
    input_path: Path,
    output_path: Path,
    cache_dir: Path,
) -> None:
    """Build a cube manifest from a Cube Cobra text export."""
    cube_name = name or cube.replace("_", " ").title()
    color_identity: list[Color] = [c for c in colors.upper() if c in "WUBRG"]  # type: ignore[misc]

    console.print(f"[bold cyan]Building manifest for cube: {cube_name}[/bold cyan]")
    console.print(f"  Input: {input_path}")
    console.print(f"  Output: {output_path}")
    console.print(f"  Cache: {cache_dir}")
    console.print()

    # Step 1: Parse the text export.
    console.print("[yellow]Parsing Cube Cobra export...[/yellow]")
    card_names = parse_cube_cobra_txt(input_path)
    console.print(f"  Found {len(card_names)} cards (including any duplicates)")

    # Step 1b: Deduplicate.
    card_names, duplicates = deduplicate_names(card_names)
    if duplicates:
        console.print(
            f"  [dim]Deduplicated {len(duplicates)} card(s) with multiple entries; "
            f"{len(card_names)} unique cards remain.[/dim]"
        )
        if len(duplicates) <= 10:
            for name in duplicates:
                console.print(f"    [dim]- {name}[/dim]")
        else:
            for name in duplicates[:10]:
                console.print(f"    [dim]- {name}[/dim]")
            console.print(f"    [dim]... and {len(duplicates) - 10} more[/dim]")
    console.print()

    # Step 2: Resolve every card via Scryfall.
    console.print("[yellow]Resolving cards via Scryfall API...[/yellow]")
    console.print(
        "  (First run: ~10 cards/sec due to API rate limit. "
        "Subsequent runs use the cache.)"
    )

    entries: list[CardEntry] = []
    failed: list[str] = []

    with ScryfallClient(cache_dir=cache_dir) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Resolving cards", total=len(card_names))
            for card_name in card_names:
                try:
                    scryfall_card = client.get_card_by_name(card_name)
                except Exception as e:
                    console.print(f"[red]Error resolving '{card_name}': {e}[/red]")
                    failed.append(card_name)
                    progress.advance(task)
                    continue

                if scryfall_card is None:
                    failed.append(card_name)
                    progress.advance(task)
                    continue

                entries.append(card_entry_from_scryfall(scryfall_card))
                progress.advance(task)

    console.print()

    # Step 3: Report failures.
    if failed:
        console.print(
            f"[bold red]Could not resolve {len(failed)} card(s):[/bold red]"
        )
        for name in failed[:20]:
            console.print(f"  - {name}")
        if len(failed) > 20:
            console.print(f"  ... and {len(failed) - 20} more")
        console.print()
        console.print(
            "[yellow]Tip: Check spelling, or these may be DFCs requiring "
            "the front face name (no '//').[/yellow]"
        )
        console.print()

    # Step 4: Check for duplicate IDs (would indicate a name collision).
    id_counts: dict[str, int] = {}
    for entry in entries:
        id_counts[entry.id] = id_counts.get(entry.id, 0) + 1
    duplicates = {k: v for k, v in id_counts.items() if v > 1}
    if duplicates:
        console.print(
            f"[bold red]Warning: {len(duplicates)} duplicate card ID(s) detected.[/bold red]"
        )
        for dup_id, count in list(duplicates.items())[:10]:
            console.print(f"  - {dup_id}: {count} entries")
        console.print()

    # Step 5: Write the manifest.
    manifest = CubeManifest(
        cube_id=cube,
        name=cube_name,
        color_identity=color_identity,
        version=version,
        cards=entries,
    )
    save_manifest(manifest, output_path)

    console.print(
        f"[bold green]✓ Wrote {len(entries)} cards to {output_path}[/bold green]"
    )
    if failed:
        console.print(
            f"[yellow]  ({len(failed)} cards skipped — see warnings above)[/yellow]"
        )


if __name__ == "__main__":
    main()
