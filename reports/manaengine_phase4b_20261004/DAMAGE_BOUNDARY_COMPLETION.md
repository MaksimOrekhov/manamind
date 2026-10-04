# Local damage boundary v1 — Completion Record

package_id: local_damage_boundary_v1
baseline: e9572dd3dfee44846c5368365e3f69c7fc308d4b
branch: codex/manaengine-first-deck
RosettaStone: f34da0d3fcb5ad312f7e2acf634d0536b044d29a (unchanged)
verdict: LOCAL_CONTRACT_VERIFIED_SCOPED; SLEET_PARTIAL; STOP_FOR_REVIEW

## Scope and implementation

CURRENT_AT_STEP evaluates ordinary spell Damage steps using their base amount, current board aura and persistent source-instance bonus. One area step evaluates once across its packets. MISSILE_TOTAL evaluates missile count once, preserving unit-damage packets. Typed context carries owner/source/instance bonus/contract; version 1 appears in diagnostics. No global continuation rewrite, new death boundary, per-step stabilize or card-ID behavioral dispatch was added.

CATA_485 is one production declaration-only consumer. A separate test-only one-then-two damage declaration demonstrates parameter reuse without new shared code. No CUSTOM consumer. TIME_855 remains deferred, along with packages B-E. There are no added generated outcomes/dynamic catalog pools.

Shared changes: C++ core/context/selector/bindings (60 physical added lines, 19 removed); Python selector allowlist (1 added, 1 removed). These physical line counts include edits of pre-existing minified lines, not a complexity metric. Native tests add 30 assertions, a new group and independent interactions; adapter adds one real-declaration scenario. No RosettaStone production change or canonical evidence promotion.

## Verified behavior and explicit limitations

- User-reviewed Seer 1/3 + Sleet: first deals 2, Seer remains 1/1, second deals 3. Native and real adapter actions independently assert this outcome.
- Damaged/silenced/no Seer, static/multiple auras, real Kalec grant plus board aura, Divine Shield/Immune, repeated surviving target, empty pool without RNG consumption and clone independence pass.
- Fireball, Frostbolt, First/Second Flame, Arcane Flow/Shatter, Secrets, Spell Damage auras, Kalec and Raincaller existing regression groups pass. Raincaller remains once per turn even with multiple successful packets.
- Arcane Flow's ordinary second damage step intentionally changes from cast-wide snapshot to current aura: an enchanted Seer surviving its first hit activates +2 for the second step. This is the approved ordinary-instruction correction. Single-hit spells, one area instruction and missile-total behavior retain their expected results.
- A mortally wounded unsilenced friendly Spell Damage source before a later ordinary damage instruction invalidates the branch. Pending board death before random enemy-minion selection also invalidates it. No candidate set is narrowed to bypass unresolved removal/deathrattle timing. No further damage or death drain occurs in those blocked followups.

Sleet is IMPLEMENTED_BUT_RULES_BLOCKED outside its verified living-board scope, not a full closed root. Mortality interactions require independent rules review. Arcane Barrage remains unimplemented: selection before/after first hit, mortal candidates/death processing, without-replacement semantics and per-hit Spell Damage timing must be reviewed separately.

## Local observed verification

| Check | Result |
|---|---|
| Debug native executable | 31 scenario groups, 567 assertions passed (baseline 30 / 537) |
| Adapter/pipeline/Policy suite | 41 passed in 22.55s |
| Full Python suite | 88 passed in 9.66s |
| Ruff (no cache) | All checks passed |
| Generic card-identity guard | PASS, 201 pre-existing reviewed exceptions |
| Canonical regeneration | 36 pinned outputs reproduced on first run; no artifact delta |
| Git whitespace | diff --check passed |

Local native core, Python extension and tests were rebuilt together in `%TEMP%/ManaEngineCorrectnessBuild` (Debug), using the configured MSVC toolchain. Adapter explicitly loaded its `python` extension directory with MANAMIND_MANAENGINE_BUILD. Hosted CI independently builds Release.

Reproduction: configure/build `experiments/manaengine` as in its CI, run native executable/CTest; set MANAMIND_MANAENGINE_BUILD to that build's Python directory and PYTHONPATH=src; run `python -m pytest -q -p no:cacheprovider experiments/manaengine/tests/test_adapter.py tests/test_pipeline.py tests/test_policy_action_semantics.py`; then full `python -m pytest -q`, Ruff, generic guard and `python scripts/check_generated_artifacts.py`.

Four build invocations, three correction cycles: one remaining Battlecry call needed the new context signature; two new test expectations were corrected after source review (Raincaller is once per turn; invalid-session legal_actions raises). No existing regression was converted to a baseline or bypassed. Default Ruff cache permission was handled with --no-cache, not a lint exception. Source/hosted checks will be recorded with actual fetched job/log identities in DAMAGE_BOUNDARY_CI_EVIDENCE.json after push.

## Registry / closure / admission

Canonical pinned outputs regenerated and remain byte-equivalent after line-ending normalization. Experimental adapter implementation is outside the canonical RosettaStone rules fingerprint; no registry status or observation schema changed. Scope adds one partial ManaEngine route, zero full verified roots, zero dependency closures, zero DECK_READY decks and zero training eligibility. Experimental admission remains blocked.

Timer started 2026-10-04 11:03:50 UTC. Implementation, review, corrections and local verification through 11:20:38 UTC: 16m48s observed elapsed, with no user-response wait. Hosted acceptance and report/commit work are separate intervals; this is not CPU time or a throughput projection.

Stop after push and green Windows/Ubuntu Source and ManaEngine CI. No later Phase 4B root, training or search is authorized by this completion.

## Hosted acceptance

Implementation commit: 0a7bedcf47b60392be80bb94f6a092f45ba24a26. [Source CI](https://github.com/MaksimOrekhov/manamind/actions/runs/37198474424) is green on Windows and Ubuntu: each reproduced all 36 outputs, had empty generated diff and actually ran 88 Python tests (13.43s / 8.21s). [ManaEngine CI](https://github.com/MaksimOrekhov/manamind/actions/runs/37198474433) is green on both: fresh Release build and native CTest (2.10s Windows / 1.07s Ubuntu), followed by all 41 adapter/policy tests (19.56s / 18.11s).

Fetched completed job steps, actual log excerpts and normalized source SHA-256 identities are in DAMAGE_BOUNDARY_CI_EVIDENCE.json. No PASS/status was inferred from earlier evidence. Local implementation/verification interval ended 11:20:38 UTC; documentation, commit/push and hosted acceptance through 11:25:32 UTC added 4m54s observed elapsed. Total through accepted implementation: 21m42s, including hosted wait. The final evidence-only commit triggers checks again and changes no implementation/test identity.
