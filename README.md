# Chaos Commander Cube

A custom MTG draft format and the toolkit that powers it: huge curated card pools where each draft sees less than 10% of the cards, ensuring wildly varied games. Seed-based draft generation means every draft is reproducible and shareable.

The format is called **Chaos Commander Draft**. The first cube is **Nicol Bolas' Chaos Commander Cube** — a blue/black/red cube of ~8000 cards. Future cubes will cover other three-color combinations, each curated separately.

This repo contains:
- The toolkit (Python) for building, tagging, and analyzing cubes
- The Tabletop Simulator mod (Lua) for running drafts and gameplay
- The data files for each individual cube (currently just Nicol Bolas')

---

## The format: Chaos Commander Draft

**One-line pitch:** 8-player Commander draft from a massive curated card pool where every draft is a fresh chaos.

**Core rules:**
- 8 players draft 5 packs of 20 cards each → 100-card pools
- Pass direction alternates per pack
- After drafting, each player designates one card from their pool as their commander
- Standard Commander gameplay rules apply for matches afterward
- Basics are free from an infinite station; non-basics are drafted
- Conspiracy cards (from MTG's Conspiracy sets) work during the draft per their normal rules

**Why "chaos":** The pool is so large that each draft sees a different sliver of it. Archetypes form and break on the fly. No two drafts are alike.

Format rules, banned list, and community discussion will live at the Discord (TBA). This repo is the technical implementation.

---

## Project overview

The codebase is **cube-agnostic**. The toolkit and TTS mod load a specific cube as data, so the same code can power the Grixis cube, a Jund cube, or any future three-color cube someone curates.

Three main components:

1. **Per-cube manifest** — a JSON file listing every card in that cube with metadata and tags. Source of truth for that cube.
2. **A Python toolkit** — cube-agnostic tools for building manifests, hand-tagging, simulating drafts, statistical analysis, A/B testing cube changes.
3. **A Tabletop Simulator mod** — the live drafting + gameplay environment. Loads a manifest as data; instantiates only the ~800 cards needed per draft.

The toolkit and the TTS mod share an identical draft algorithm (Mulberry32 PRNG + A-Res weighted reservoir sampling). Given the same cube version, the same filter/weight configuration, and the same seed, both produce the *exact same* 800-card draft. This makes the analysis lab useful: insights from Python simulations apply directly to in-game drafts.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              cubes/<cube_name>/manifest.json                    │
│           (canonical source of truth per cube)                  │
│                                                                 │
│  Each entry: id, name, scryfall_id, set_code, image_url,        │
│   color_identity, cmc, type_line, is_land, is_basic_land,       │
│   tags[]                                                        │
└────────────┬─────────────────────────────────────┬──────────────┘
             │                                     │
             ▼                                     ▼
   ┌───────────────────────┐         ┌─────────────────────────────┐
   │  Python toolkit       │         │  TTS mod (Lua)              │
   │  ─────────────────    │         │  ─────────────────────      │
   │  • manifest builder   │         │  • loads manifest as data   │
   │  • tag CLI            │         │  • cube picker UI           │
   │  • draft simulator    │         │  • seed input UI            │
   │  • analysis / stats   │         │  • filter / weight UI       │
   │  • cube tuning tools  │         │  • seed → 800 cards         │
   │                       │         │  • spawns pack objects      │
   │                       │         │  • draft state machine      │
   │                       │         │  • deck export              │
   └───────────────────────┘         └─────────────────────────────┘

   Both implement identical Mulberry32 + A-Res weighted sampling
   → same (cube_version, config_hash, seed) produces same draft
```

---

## Component breakdown

### Per-cube manifest (`cubes/<cube>/manifest.json`)

Authoritative list of every card in a specific cube. Each entry:

```json
{
  "id": "soul_warden_tmp",
  "name": "Soul Warden",
  "scryfall_id": "ce711943-c1a1-43a0-8b89-8d169cdd3c94",
  "set_code": "TMP",
  "image_url": "https://chaoscommander-images.r2.dev/soul_warden_tmp.jpg",
  "color_identity": ["W"],
  "cmc": 1,
  "type_line": "Creature — Human Cleric",
  "is_land": false,
  "is_basic_land": false,
  "tags": ["lifegain", "creature_etb", "white_weenie", "set:tempest", "added:v3"]
}
```

Notes:
- `id` is stable across reprints (yours, not Scryfall's). If you swap printings, `scryfall_id`/`set_code`/`image_url` change but `id` stays.
- Most metadata fields (CMC, color, type) come from Scryfall auto-population during the build.
- `tags` are the only field requiring hand-curation, and many are also auto-derived (see `tag_vocabulary.json`).

### Tag vocabulary (`cubes/<cube>/tag_vocabulary.json`)

A controlled vocabulary keeps tags from drifting (`lifegain` vs `life-gain` vs `Lifegain`). Per-cube because each cube may have its own archetypes and themes. Categories:

- **archetype** — `lifegain`, `aristocrats`, `spellslinger`, `tribal_elves`, etc. Hand-curated.
- **function** — `wrath`, `ramp`, `removal_single`, `removal_mass`, `tutor`, etc. Hand-curated.
- **mechanic** — `cycling`, `flashback`, `kicker`, etc. Auto-derived from Scryfall oracle text.
- **set** — `set:tempest`, `set:alpha`, etc. Auto-derived.
- **meta** — `added:v3`, `signature_card`, `iconic`, `pet_card`. Hand-curated.

Tags are flat strings (not nested objects); category prefixes like `set:` and `added:` enable UI grouping. A `validate_tags.py` script lints the manifest against the vocabulary.

### Python toolkit (`tools/`)

All scripts take `--cube <cube_name>` to specify which cube directory to operate on.

- **`build_manifest.py`** — reads Cube Cobra CSV export, enriches with Scryfall API data, downloads images, uploads to R2, emits `manifest.json`. One-time setup per cube, then re-run when the cube changes.
- **`tag_cli.py`** — interactive CLI for hand-tagging. Fuzzy card search, bulk operations (e.g., "tag all cards with 'lifelink' in oracle text as `lifegain`"), tag suggestions based on existing tags.
- **`validate_tags.py`** — lints a manifest against its tag vocabulary. Catches typos and drift.
- **`draft_sim.py`** — given a cube + config + seed, produces a draft (40 packs of 20). Reference implementation of the seed→cards algorithm.
- **`analyze.py`** — runs N draft simulations, computes statistics: color balance, curve, archetype representation, tag distribution. Output: charts + summary.
- **`compare_cubes.py`** — A/B testing for cube changes. Takes two manifests (or two versions of one), runs simulations on both, compares outcomes.

### TTS mod (`tts/`)

- **`global.lua`** — main mod script. Loads the active manifest, handles seed input, filter UI, draft generation, pack dealing.
- **`draft_state.lua`** — state machine for the draft itself. Tracks whose pack is whose, handles picking, passing direction (alternates by pack), Conspiracy card handling.
- **`rng.lua`** — Mulberry32 implementation. Must match Python's bit-for-bit.
- **`sampling.lua`** — A-Res weighted reservoir sampling. Must match Python's.
- **`spawn.lua`** — instantiates card objects from manifest entries using `spawnObjectJSON`.
- **`ui.lua`** + **`ui.xml`** — UI definitions: cube picker, seed input panel, filter toggles, weight override panel.

The mod ships with all curated cubes embedded (or fetched on demand from the repo's GitHub Pages — TBD per cube size).

---

## Repo structure

```
chaos-commander-cube/
├── README.md                          # This file
├── DESIGN_DECISIONS.md                # Detailed reasoning for non-obvious choices
├── FORMAT_RULES.md                    # Full rules for Chaos Commander Draft
├── cubes/
│   └── grixis/
│       ├── manifest.json              # Cube data
│       ├── tag_vocabulary.json        # Cube-specific tag vocab
│       ├── cube_cobra_export.csv      # Source export (committed for reproducibility)
│       └── README.md                  # Cube-specific notes (theme, archetypes, etc)
├── tools/
│   ├── pyproject.toml
│   ├── mtgccc/
│   │   ├── __init__.py
│   │   ├── rng.py                     # Mulberry32 — reference implementation
│   │   ├── sampling.py                # A-Res weighted sampling
│   │   ├── manifest.py                # Manifest loading / writing
│   │   ├── scryfall.py                # Scryfall API client (rate-limited)
│   │   ├── images.py                  # Image download + R2 upload
│   │   └── draft.py                   # Seed → 800 cards logic
│   ├── scripts/
│   │   ├── build_manifest.py
│   │   ├── tag_cli.py
│   │   ├── validate_tags.py
│   │   ├── draft_sim.py
│   │   ├── analyze.py
│   │   └── compare_cubes.py
│   └── tests/
│       └── test_determinism.py        # Python ↔ Lua parity tests
├── tts/
│   ├── global.lua
│   ├── draft_state.lua
│   ├── rng.lua
│   ├── sampling.lua
│   ├── spawn.lua
│   ├── ui.lua
│   └── ui.xml
├── docs/
│   ├── seed_format.md                 # How seed codes encode
│   ├── tag_guide.md                   # When/how to use which tags
│   ├── tts_setup.md                   # How to use the mod
│   └── adding_a_cube.md               # Guide for curating a new cube
└── .github/
    └── workflows/
        └── ci.yml                     # Lint, tests, manifest validation
```

---

## Design decisions

### Cube-agnostic codebase

The toolkit and TTS mod don't know about specific cubes — they operate on manifest data. Adding a new cube is a matter of dropping a directory under `cubes/`. This means the work invested in tooling pays off across every future cube.

### Seed-based draft generation

Each draft is identified by `(cube_version, config_hash, seed)`. Given those three values, the exact 40 packs of 20 cards can be reconstructed. Benefits: shareable drafts, reproducible bug reports, deterministic testing, parallel comparison of pick strategies across players.

Seeds are 32-bit integers, displayed as base36 (7 chars). Full identifier example: `bolas-v12-default-15O8MOM`.

### Mulberry32 + A-Res

- **Mulberry32** as the PRNG because it's tiny (~10 lines), fast, and deterministic across platforms. Lua's built-in `math.random` is not portable across Lua versions.
- **A-Res reservoir sampling** for selecting 800 cards from 8k with optional per-card weights. Single pass, no normalization, handles weighted and unweighted cases with the same algorithm. Each card gets `key = rng()^(1/weight)`, take top 800 by key.

### Tag schema

Tags are flat strings with prefix conventions for UI grouping (`set:tempest`, `added:v3`). Controlled vocabulary per cube. Lint script catches drift. Custom (hand-curated) + auto-derived (from Scryfall) tags coexist in the same field.

### Manifest hosting

Manifest is embedded directly in the TTS mod's Lua (~2-3MB of text per cube — well within TTS limits). When a cube updates significantly, the mod is republished. Considered fetching from GitHub at runtime, but embedding is simpler and removes a runtime dependency.

### Image hosting

Cloudflare R2 bucket. Free tier covers 10GB; ~600-800MB per cube. Free egress is critical given 8 simultaneous TTS clients fetching images per draft. Image format: JPG at Scryfall's `normal` quality (488×680). ~50-80KB per card.

### Lands

Basics are free from an infinite-stack land station on the gameplay table. Non-basics are drafted from the pool like any other card. No special pack composition logic needed.

### Commanders

Players designate one of their 100 drafted cards as commander during deckbuilding. Marked via a dedicated "Commander Zone" snap point on the gameplay table. No impact on draft mechanics.

### Draft format

8 players, 5 packs of 20 cards, 100 cards per player → commander deck. Pass direction alternates by pack (1: left, 2: right, 3: left, 4: right, 5: left). Conspiracy cards are revealed and applied per their rules text.

### Tabletop separation

Two TTS workshop items:
- **Draft table** — 8-player draft happens here, then players export decks.
- **Commander gameplay table** — 4-player pods play here on multiple table instances. Decks imported from draft export.

---

## Milestones

Concrete, deliverable-driven. The Grixis cube is the first (and currently only) cube. Building it out also builds the toolkit and mod that will support future cubes.

### M1: Manifest builder produces a valid Bolas manifest

- Set up repo, pyproject.toml, project skeleton with `cubes/grixis/` directory
- Define initial `tag_vocabulary.json` for Bolas
- Write `scryfall.py` (rate-limited API client)
- Write `build_manifest.py`: ingest Cube Cobra CSV, enrich with Scryfall, emit JSON (images skipped at first, just URLs)
- Run on the real 8k Bolas cube, fix issues, commit `manifest.json`
- **Deliverable:** `cubes/grixis/manifest.json` exists and validates against schema.

### M2: Image pipeline

- Set up Cloudflare R2 bucket
- Write `images.py`: download from Scryfall, optimize, upload to R2
- Re-run `build_manifest.py` end-to-end with image upload step
- **Deliverable:** every card in the Bolas manifest has a working `image_url` pointing to R2.

### M3: Python draft simulator

- Write `rng.py` (Mulberry32) and `sampling.py` (A-Res), with unit tests
- Write `draft.py`: seed + manifest + config → 40 packs of 20
- Write `draft_sim.py` CLI: generate and print a draft
- **Deliverable:** `python draft_sim.py --cube grixis --seed 42` outputs reproducible 40 packs.

### M4: Tag CLI

- Write `tag_cli.py`: fuzzy card search, bulk operations, tag suggestions
- Auto-populate mechanic / set / type tags
- Hand-tag the strategic stuff (archetypes, signature cards) — ongoing
- Write `validate_tags.py` for lint
- **Deliverable:** can rapidly tag cards from CLI; CI lints tag drift.

### M5: Analysis lab

- Write `analyze.py`: run N drafts, compute color/curve/tag distributions
- Visualizations (matplotlib): histograms, balance reports
- Write `compare_cubes.py`: A/B test cube changes
- **Deliverable:** can answer "is lifegain underrepresented in Bolas?" with data.

### M6: TTS — basic card spawning

- Create empty TTS mod
- Embed Bolas manifest as Lua table (or test loading via WebRequest)
- Write `spawn.lua`: instantiate card objects from manifest entries
- Manual test: hardcode 20 card IDs, spawn them, verify images load
- **Deliverable:** TTS mod can spawn arbitrary cards from a manifest.

### M7: TTS — seed-based pack generation

- Port `rng.py` → `rng.lua` and `sampling.py` → `sampling.lua`
- Determinism test: given seed 42, Python and Lua produce identical card lists
- UI: cube picker (Bolas-only for now), seed input box, "Generate Draft" button
- On button press: shuffle, pick 800, deal into 40 packs as visible deck objects on table
- **Deliverable:** enter seed, get 8 stacks of 5 packs of 20 cards on the table.

### M8: TTS — draft state machine

- Pack rotation: pass left/right/left/right/left
- Pick mechanic: right-click → "Pick this card" → moves to player's pool, rest of pack passes
- Turn/phase tracking, "ready" indicators
- Deck export at end (saves as TTS deck object per player)
- **Deliverable:** end-to-end draftable from seed to exported decks.

### M9: TTS — Conspiracy card handling

- Inventory which Conspiracy cards are in the Bolas cube
- Categorize: "just reveal" vs "needs draft-time mechanic"
- Implement special handling for the mechanic-bearing ones
- **Deliverable:** Conspiracy cards function correctly.

### M10: TTS — gameplay table

- Decorations (cube-specific aesthetic — for Bolas, Amonkhet/Egyptian dragon vibes)
- Tools: dice, counters, life trackers, token spawners
- Basic land station
- Commander snap point
- **Deliverable:** publishable gameplay table.

### M11: Polish + Workshop publish + Discord launch

- Documentation, screenshots, mod thumbnail
- User guide for hosts and drafters
- Submit to Steam Workshop
- Spin up the Chaos Commander Discord with rules, banned list discussion, cube suggestion channels
- **Deliverable:** anyone can find and play the format.

### Future: additional cubes

Once Bolas is shipped and the toolkit is solid, additional cubes can be added by curating a Cube Cobra list, running `build_manifest.py`, and tagging. The TTS mod's cube picker exposes any new cubes that get added.

---

## Open questions

Things we've punted on but will need decisions later:

- **Which Conspiracy cards are in the Bolas cube?** Need to inventory and categorize before M9.
- **R2 bucket setup details** (region, custom domain, etc) — punted to M2.
- **TTS UI design** — wireframes for cube picker, seed input, filter panel, weight override panel.
- **Bolas-specific aesthetic** — Amonkhet motifs? Pre-mending Bolas lore? Egyptian/dragon iconography?
- **Multiplayer drafting UX details** — how do "ready" indicators work, do we enforce a pick timer, what happens if someone disconnects mid-draft?
- **Deck export format** — TTS native deck save? Markdown/text export for sharing? Cube Cobra import-compatible format?
- **Should the gameplay table also support the draft phase?** (Same instance vs separate tables — current plan is separate, but worth revisiting.)
- **Discord structure** — channels for each cube? Single rules channel? Community curation pipeline for new cubes?
- **Banned list governance** — who decides, how often, where is it documented?

---

## Glossary

- **Chaos Commander Draft** — the format defined by this project.
- **Cube** — a curated card pool from which packs are generated for drafting.
- **Grixis cube** — the first cube of this format; Grixis (UBR) colored, ~8000 cards.
- **Draft** — players take turns picking cards from packs to build their decks.
- **Pack** — a set of cards (here, 20) from which one card is picked, then the rest are passed.
- **Pod** — a group of players drafting together (here, 8 per draft).
- **Commander** — in this format, one of the player's drafted cards designated as their general/commander.
- **Conspiracy card** — special draft-phase cards with effects during the draft itself (from MTG's Conspiracy sets).
- **Seed** — an integer that, combined with cube version and config, deterministically produces a specific draft.
- **Manifest** — the canonical JSON file listing every card in a specific cube.