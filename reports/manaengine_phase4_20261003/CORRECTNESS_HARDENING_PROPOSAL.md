# Phase 4 correctness hardening proposal

Package: `prototype_correctness_hardening_v1`; baseline ManaMind `a62ff5fb2f7d48498aea7e913a46ab24ad723286`.
Active work started 2026-10-04 09:04:32 UTC. No new deck roots, training, search or backend migration.

## Contracts before implementation

- One typed damage packet carries source, controller, target, amount, kind and Lifesteal. Prevention returns zero; otherwise damage includes overkill. Armor absorbs hero damage. Result evaluation is deferred until mandatory stabilization completes. Combat snapshots both attacks before damage and sends retaliation to heroes as well as minions.
- Attack Secret eligibility uses the attacked target for friendly-hero/minion windows and the attacker for enemy-minion windows. Activation order remains explicit. Cancelled attacks do not continue gameplay windows whose subject is no longer attacking.
- Collect all dead minions before any deathrattle; order the snapshot by activation sequence, remove the entire batch, then drain mandatory deathrattles and repeat. This remains the approved prototype FIFO model, not a claim of complete Hearthstone event ordering.
- Zero effective cost is a valid playable state. Prepare eligibility must never throw merely because the card reached zero; reviewed rules determine whether a Prepare action is exposed.
- Shatter inherited instance modifiers must not multiply without an external modification. Unconfirmed merge interactions fail closed; existing tests are not an independent rules oracle.
- Catalog support requires reviewed mechanic coverage, not nonempty-text heuristics. Water Elemental is unsupported. Generated IDs must exist in pinned metadata, not fabricated adapter rows.
- Public observations must retain known future-affecting progress and durations, without RNG, deck order, opposing hidden identities or activation sequence. Schema changes invalidate evidence normally.
- Unsupported hero powers fail session admission. Development branch simulation and complete training closure are independent; no survivor-only dataset filtering.

## Verification

Independent adversarial group: combat matrix, shield/immune/armor, Lifesteal overkill, Secret eligibility/order/cancellation, simultaneous deaths and fatigue, zero-cost Prepare lifecycle, modifier conservation/fail-closed, mechanic rejection, privacy and public-state roundtrip. Build native core and adapter together; run native, adapter/pipeline, full repository pytest, regeneration check and both hosted workflows. Unresolved rules remain explicitly NEEDS_RULES_VERIFICATION and do not acquire verification status.

Expected newly supported roots: zero. CUSTOM additions: zero. Completion requires recorded actual test/CI outcomes; stop after this checkpoint.
