# Verification follow-up — 2026-10-02

## Python suite

Full suite: **44 passed in 8.27 seconds**, no failed tests. Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp E:/ManaMind/.pytest-tmp-review-20261002-a
```

The initial default run encountered fixture setup PermissionError in the shared Windows pytest temporary directory. The separate workspace temporary directory resolved that environmental issue. The successful run retained one cache-write ACL warning; this did not skip or fail tests. These include synthetic plumbing checks, not production self-play or a training admission decision.

## Why eleven scoped rows became STALE

For each of the four schema-2 evidence documents, the sole differing execution-identity field was `rules_source_sha256`. That identity deliberately includes **all** generator/rules Python sources, not only a package's direct imports. The changed source was `scripts/card_rules/composition_ops.py`: the renderer now distinguishes ARMOR_DAMAGE custom routing from an unknown operation and removes an unreachable raise.

The four package generators do not use that composition renderer. Their declarations, generated C++, native engine/bridge/observation sources, catalog, native scenarios and verifier scripts were unchanged. The 27-output regeneration check in the previous maintenance stage also reproduced all generated rules. This supports **no semantic impact on these four scoped contracts**, not an automatic transfer of PASS to a new identity.

The composition renderer's invalid-input error behavior did change. A future composition verification must use the current renderer; historical composition results are not upgraded here. Successful supported compositions produced identical C++. No new family expectations were inferred from that fact.

| Verification package | Scoped cards | Semantic impact of this edit | Actual repeat |
|---|---|---|---|
| after_attack_draw | CAP_003, EDR_253, CORE_NX2_028, TLC_478, TLC_840 | None on package effects/actor timing; global fingerprint only | 5 native cases / 42 assertions; bridge smokes passed |
| repeated_trigger_draw | CORE_DMF_067, RLK_708, CORE_RLK_657 | None on trigger/draw contract; global fingerprint only | 4 / 34; original bridge scope repeated |
| filtered_school_draw | FIR_929, RLK_511 | None on school/Deathrattle draw contract; global fingerprint only | 3 / 27; original bridge scope repeated |
| core_aliases scoped ULD133 verification | CORE_ULD_133 | None on alias parity/Crystal Merchant scenario; global fingerprint only | 1 / 780; existing alias batch bridge smokes repeated |

## Actual refresh procedure

Previous evidence and build identity were copied to `before_*.json` in this report directory **before** any producer overwrote its output. Ran:

```powershell
.\.venv\Scripts\python.exe scripts/build_native_identity.py
.\.venv\Scripts\python.exe scripts/verify_after_attack_draw.py
.\.venv\Scripts\python.exe scripts/verify_repeated_trigger_draw.py
.\.venv\Scripts\python.exe scripts/verify_filtered_school_draw.py
.\.venv\Scripts\python.exe scripts/verify_core_alias_uld133.py
.\.venv\Scripts\python.exe scripts/build_standard_registry.py
```

The configured build succeeded; the evidence producers checked current source/profile identity, artifact hashes and the actually loaded bridge. All **13 native cases / 883 assertions** passed. Before/after native artifact hashes and per-card evidence payloads are identical. The new execution identity was recorded only after actual checks. See `result.json` for the before/after comparison and evidence hashes.

Result: eleven rows have matching CURRENT **scoped** evidence again; the five older historical rows (CAP_801, CORE_BAR_801, CORE_CS2_004, CORE_SW_066, END_007) remain STALE because their earlier scenarios lack the current complete execution/source fingerprint. Full-Standard closure and training admission remain blocked, with zero eligible roots. Core alias parity checks/batch imports do not confer rules verification on every alias.

**Preserved limitation:** RLK_708 and RLK_511 have native effect evidence and deck-legality checks; Death Knight session setup remains blocked. Their producers explicitly retain that limit in each card's bridge-smoke text. An aggregate smoke PASS must not be presented as a successful Death Knight session or match. No session/match evidence was created.

Final source checks: Ruff (`src tests scripts`), generator AST guard and `git diff --check` passed; 27 pinned outputs reproduced with unique ownership. No tracked native engine/card source changed, no package implementation started and no new roots registered during this verification/analysis task.
