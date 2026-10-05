# Phase 4G completion record — Vulcanos vertical slice

Date: 2026-10-05

Branch: `codex/manaengine-first-deck`

Starting HEAD: `4da10488b51ea3fc55bd82c1f721f53e225815e3`

## Verdict

`VULCANOS_PARTIAL_FIRE_BLOCKED`

The bounded Vulcanos body + Colossal appendage entry and end-of-turn damage path are implemented in ManaEngine. The two Plumes are registered against the existing TakesDamage v1 contract, but their random Fire generation remains fail-closed because the exact runtime pool is not established. This is not full Vulcanos support and does not make any root training-eligible.

## Scope and implementation

- `CATA_488` declares its ordered appendages `CATA_488t`, then `CATA_488t2`.
- The shared board-entry helper is used for playing and fixed-effect summoning. It creates independent summoned entities, preserves the declared left/right order around the body, and assigns fresh activation sequences.
- The whole body + appendage family is preflighted before hand removal, entity allocation, or board mutation. Full admission is tested with 0, 1, and 4 existing minions. At 5 or 6, the branch fails closed without mutation. Partial-capacity rules remain unknown.
- Transforming into a Colossal and copying a Colossal source fail closed. Transforming the body out leaves appendages as ordinary independent minions.
- `CATA_488` has the reusable `END_TURN_OTHER_MINIONS_DAMAGE` instruction. It snapshots target entity handles in active board order, excludes its source, skips targets already removed, ignores the source when silenced or dead, and sends 3 `Effect` damage to other minions on both sides. Divine Shield, Immune, Reborn, and existing modifier behavior use shared damage/death processing.
- Both Plumes declare the existing TakesDamage v1 descriptor with Fire candidate pool ID `fire_spell_standard_20261001_candidate_v1` and cost delta `-3`. A candidate pool is not sampled. Missing/unreviewed pool membership and full-hand rejection happen before RNG. Lethal consumer state remains outside TakesDamage v1 and fails closed.
- No card-ID behavior branch was added. Three in-scope card definitions are declarations over shared behavior; runtime Fire membership remains unresolved for both Plumes.

## Fire pool result

The candidate has 33 unique Standard-legal collectible Fire spell IDs in the pinned `standard_full_20261001_v1` snapshot. It remains `CANDIDATE`; its membership and metadata hashes are recorded in [FIRE_POOL_REVIEW.md](FIRE_POOL_REVIEW.md). Available official materials support a Standard boundary and a three-rune exclusion, but do not establish the exhaustive patch-specific `NON_GENERATABLE` exclusions for Plume's wording. Thus 33 pool memberships remain unresolved as a set. No candidate was promoted and no RNG result was fabricated.

## Rules/evidence boundaries

Official and supporting sources, admitted capacity, partial-capacity uncertainty, appendage identity ordering and transform/copy limits are recorded in [COLOSSAL_RULES_REVIEW.md](COLOSSAL_RULES_REVIEW.md). The implementation covers ordinary play and generic fixed-effect summon entry. It does not claim exact partial-capacity, Transform-into-Colossal, copy-of-Colossal, or Plume random-result correctness.

## Verification

- Native build: PASS (MSVC Release build in the configured ManaEngine build directory).
- CTest: PASS, 1/1 native test.
- Direct native suite: PASS, **57 scenario groups / 1607 assertions**.
- Full Python suite: PASS, **92 passed**.
- Focused Vulcanos adapter: PASS, 1 passed.
- Ruff: PASS.
- Generated artifacts: PASS, 36 pinned outputs reproduced with unique ownership.
- Generic card-branch guard: PASS, 201 reviewed AST exceptions; CUSTOM ownership check passed.
- Candidate pool regeneration reproduced Fire=33, Whelp raw=77, and variants=65/63 with unchanged candidate manifest hashes.
- Frontier ledger regenerated and `--check` passed: 105 unique candidate roots across the four pools.
- `git diff --check`: PASS.
- Hosted Source CI: PASS on Windows and Ubuntu. Both jobs completed lint, identity guard, generated-artifact check, clean diff check, and pytest. [Run 65](https://github.com/MaksimOrekhov/manamind/actions/runs/37274537724).
- Hosted ManaEngine CI: PASS on Windows and Ubuntu. Both jobs completed Release build, CTest, and adapter/policy pytest. [Run 42](https://github.com/MaksimOrekhov/manamind/actions/runs/37274537764).

## Measured work

- New native Vulcanos scenario group: 1.
- Shared production changes: typed Colossal appendage metadata + shared entry helper, one end-turn damage capability, and existing TakesDamage v1 declarative consumer fields. The adapter parses and validates the appendage dependencies and generation descriptors.
- Correction cycles: at least 3 observable cycles: (1) board-capacity discovery moved to a pre-mutation guard, (2) Dark Gift modifier test setup was corrected to retain the modifier on the intended surviving entity, and (3) multi-Vulcanos test mana/activation setup was corrected. The Spell Damage +2 isolation assertion was added and passed in the final build.
- Elapsed observation: at least **36m18s** from the last recorded active-work checkpoint (06:13:23 UTC to 06:49:41 UTC), including validation and report work. This excludes earlier Phase 4G work before that checkpoint; total active implementation time cannot be reconstructed reliably from the available session timing, so no full-task duration is claimed.

## Canonical profile impact

- Standard registry, candidate membership and pinned profile: unchanged by the generation check.
- ManaEngine declarations: +3 (`CATA_488`, `CATA_488t`, `CATA_488t2`).
- Runtime verified roots gained: 0; the newly added native scenarios verify the bounded Colossal/EOT contract but do not resolve the Fire pool.
- Dynamic dependency closure gained: 0. Fire pool remains open; training eligibility remains false.
- Observation schema: unchanged. Appendages are ordinary visible board entities; runtime pool/RNG state remains hidden.

## Proposal and design record

See [VULCANOS_ARCHITECTURE.md](VULCANOS_ARCHITECTURE.md). No implementation of Whelp, Barrage, search/MCTS, or training was started in this package.
