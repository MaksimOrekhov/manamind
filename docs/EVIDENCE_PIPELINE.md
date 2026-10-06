# Evidence pipeline (EVIDENCE-0B)

Offline extractor that turns **completed Ranked Standard** Power.log games into sanitized observations about cards
ManaEngine does not support. It collects evidence; it never learns, promotes or changes a rule. Design authority:
[EVIDENCE0A_REAL_CARD_MECHANIC_DISCOVERY.md](../reports/mechanic_discovery/EVIDENCE0A_REAL_CARD_MECHANIC_DISCOVERY.md);
implementation notes and deviations: [EVIDENCE0B_EXTRACTOR_REPORT.md](../reports/mechanic_discovery/EVIDENCE0B_EXTRACTOR_REPORT.md).

## Run

```bash
python scripts/extract_evidence.py --input <Power.log | slice.log | folder> --output data/processed_evidence/<run>
```

* `--output` must not exist (no overwrite). `data/processed*/` is git-ignored; never commit generated evidence.
* `--support-inventory FILE` consumes an exported engine inventory (`{inventory_id, cards: {id: {state, reason}}}`); without it
  the declaration file is a `DECLARATION_PROXY`, recorded in every observation.
* `--include-secondary` also extracts non-Ranked-Standard games, tagged `OTHER_MODE_SECONDARY`; they must never be mixed
  into primary aggregates. `--card-metadata` (full card metadata) only refines `registry_scope` of non-root ids.
* Output: `observations.jsonl`, `games.jsonl` (one status line per game, skip reasons are fixed codes), `manifest.json`.
  Bytes are deterministic for the same input and `extractor_version`.
* The console shows aggregate counts and exception **class** names only.

## Lanes and privacy

* The evidence lane is one-way. `manamind.evidence` may import `manamind.live` / `manamind.integrations.powerlog` helpers;
  `encoding`, `models`, `training`, `inference` and `live` must never import it (`tests/test_evidence_boundary.py`).
  Every record carries `model_input_allowed: false`.
* Identities SELF could not see (opponent hand, deck, secret, setaside, `OVERRIDE_HISTORY` and show-then-hide reveals) are
  **redacted** (`card_id: null`) and their facts labelled `OFFLINE_ONLY_HIDDEN`. Default deny.
* No player name, BattleTag, account id or raw log text is stored. The run scans its own output against identifiers read
  from the input (in memory only) and deletes the output on any hit.
* Entity handles are per-game references, not model inputs.

## What a record means

Each observation is one (root block window, subject card). `facts` are packets read directly; `inferences` are derived and
always list their input facts and assumptions. Attribution precedence: `CREATOR_TAG` > `LAST_AFFECTED_BY` set in the same
unit > unit owner > `UNATTRIBUTED`; anything attributed to another entity is `NESTED_ONLY` and is not the subject's effect.
`evidence_limits` repeats on every record: absence of an effect is not a negative rule, observed outcomes are single draws
and never a pool, nothing is rules-verified.
