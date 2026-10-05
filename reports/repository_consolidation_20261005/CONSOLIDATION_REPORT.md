# Repository Consolidation — 2026-10-05

## Scope and result

This consolidation moves the current ManaEngine source line to `main`, accounting for divergent Claude prototype commits individually. The primary checkout at `E:\ManaMind` and all pre-existing local worktrees and branches were left untouched.

## Starting remote branch tips

| Branch | Starting tip |
|---|---|
| `main` | `0b27fec85b288996535c543b2e633c85ce73d68c` |
| `codex/manaengine-first-deck` | `b39e73e9dca6adf34548febb95ea769d6b13e540` |
| `codex/manaengine-hardening` | `eecc9fe9f187da5162037a4c052aca36896870d9` |
| `codex/manaengine-prototype` | `339b51ebf9d9bede781bcf448eba34a23d83a36e` |
| `claude/dark-gift-prototype` | `f73cabdad60d6c02b689afd809c7bae455557def` |
| `claude/reborn-prototype` | `a35ddc6f0b0bd736d6a3b30e2a31884e39204cc1` |

Remote identities were cross-checked through authenticated GitHub branch metadata against local tracking refs. `git fetch` was not used because the shared primary repository metadata could not safely be updated; DNS also prevented `git ls-remote`. No work proceeded from unverified identities.

## Source and graph audit

`SOURCE_HEAD`: `b39e73e9dca6adf34548febb95ea769d6b13e540` (`codex/manaengine-first-deck`). This source line contains the Phase 4J.1 inferred Fire status/manifest, membership contract, completion report, and hosted CI record. Original `main`: `0b27fec85b288996535c543b2e633c85ce73d68c`.

`main`, `codex/manaengine-hardening`, and `codex/manaengine-prototype` are ancestors of `SOURCE_HEAD`. The source line contains 68 commits beyond `main`; `codex/manaengine-prototype` and `codex/manaengine-hardening` contribute no unique commits beyond the source line. Dark Gift diverged from merge base `31a9df16a6ffa1ff571e79e9bcfcfd82d3248d17` with 3 branch-only commits. Reborn diverged from merge base `a31fe5612b72c7e190dcbd3c950cd15aac6405bf` with 4 branch-only commits. No branch was merged wholesale.

### Dark Gift unique commits

| Commit | Classification | Reason |
|---|---|---|
| `b8f535310071c9226cb6268b0fb398797f61f489` | `SEMANTICALLY_SUPERSEDED` | Current source contains the later typed Dark Gift integration and safety behavior (`c436683`, `e1a4d2d`, `a31fe56`) with current tests and pool contract. |
| `2e6388a86ed7a9e5dda578b20cd3560ea9974102` | `SEMANTICALLY_SUPERSEDED` | Current reports, typed pool/metadata and later Phase 4B review replace the prototype report/manifest state. |
| `f73cabdad60d6c02b689afd809c7bae455557def` | `SEMANTICALLY_SUPERSEDED` | The prototype CI state is superseded by the current integration completion and hosted CI record. |

### Reborn unique commits

| Commit | Classification | Reason |
|---|---|---|
| `75d22f7379c48ba9e973c89be41e7e8bf2001f3c` | `SEMANTICALLY_SUPERSEDED` | Reborn implementation is present in the current source line with later integration and evidence-debt handling. |
| `a754ca6db20c9c822e89aab4cb02648d26ac6548` | `SEMANTICALLY_SUPERSEDED` | The older architecture/rules notes are replaced by current integration review and completion records. |
| `6b5555ee5c446196fa7c50fba5580b4799870e27` | `SEMANTICALLY_SUPERSEDED` | Current corrected hosted CI record supersedes the prototype CI record. |
| `a35ddc6f0b0bd736d6a3b30e2a31884e39204cc1` | `REPORT_OR_EVIDENCE_MISSING` | A useful rules evidence report referenced by current review existed only on this branch; only that report was ported. |

## Port and exclusions

Ported `REBORN_RULES_EVIDENCE.md` from the Reborn branch into `reports/manaengine_reborn_integration_20261005/REBORN_RULES_EVIDENCE.md`. Added a provenance note: historical URLs were not independently re-fetched and this port does not promote evidence status. Updated the current integration review to link the local report while retaining that caveat.

Port commit: `2845b792e33c41f8d74450456fdf4e0798204e7a` (`docs: retain reviewed Reborn evidence`). No production code, card declarations, schemas, or RosettaStone content were ported. Older Dark Gift/Reborn code, prototype CI configuration, and stale reports were deliberately not restored.

## Local validation on the consolidation line

| Check | Result |
|---|---|
| ManaEngine Release build | PASS (MSVC 19.44.35213, Ninja, Python 3.12.10, pybind11 3.1.0) |
| Focused inferred Fire suite | PASS — 228 assertions |
| Arcane Barrage suite | PASS — 10 groups / 142 assertions |
| Damage Group suite | PASS — 10 groups / 173 assertions |
| Full ManaEngine native suite | PASS — 78 scenario groups / 2,153 assertions |
| CTest | PASS — 1/1 |
| Full pytest | PASS — 92 passed |
| Ruff | PASS |
| Generated artifact check | PASS — 36 pinned outputs reproduced; unique ownership verified |
| Generic card branch guard | PASS — 201 reviewed AST exceptions |
| Adapter/policy CI-equivalent suite | PASS — 83 passed |
| Fire and Dark Gift strict manifest validation | PASS — Fire 33 members, `REVIEWED_INFERRED`, open and training-ineligible; Dark Gift 12 candidates, 10 launch-reviewed |
| Inferred Fire candidate manifest identity | PASS — unchanged blob `4998436236e924cfbb246c3626edcd4187a3776b` |
| RosettaStone submodule | PASS — unchanged at pinned revision `f34da0d3fcb5ad312f7e2acf634d0536b044d29a` |
| `git diff --check` | PASS before final report addition; rerun before commit |

The regression runs include Dark Gift, Reborn, and adapter cache-isolation coverage.

## Hosted CI and promotion

Temporary branch push: pending. Source and ManaEngine experimental hosted CI (Ubuntu and Windows): pending. Fast-forward promotion to `main`: pending. Final consolidated SHA and final `main` SHA: pending.

## Remote branch cleanup

No remote branches have been deleted yet. Deletion will occur only after the final report is committed, consolidated CI is green, and `main` is confirmed to contain all required work.

| Candidate branch | Former tip | Deletion result |
|---|---|---|
| `codex/manaengine-prototype` | `339b51ebf9d9bede781bcf448eba34a23d83a36e` | pending |
| `codex/manaengine-hardening` | `eecc9fe9f187da5162037a4c052aca36896870d9` | pending |
| `codex/manaengine-first-deck` | `b39e73e9dca6adf34548febb95ea769d6b13e540` | pending |
| `claude/dark-gift-prototype` | `f73cabdad60d6c02b689afd809c7bae455557def` | pending |
| `claude/reborn-prototype` | `a35ddc6f0b0bd736d6a3b30e2a31884e39204cc1` | pending |

## Local branches and remaining cleanup

All local worktrees and branches were intentionally left untouched, including the dirty primary `E:\ManaMind`, older local first-deck checkout, Phase 4J.1 checkout, Claude review worktrees, and the current consolidation worktree. Remote cleanup is independent from local cleanup. Any unrelated branches discovered in the wider repository remain outside this task.
