# REAL-ACTION-PREFERENCES-1 — protocol

No training, checkpoint writes, production edits or real-test access. Base:
8718ee6ad6886ec4a48204cae5eb25070d5f6e6e. Read only the pinned retrain train/validation.
They are development data, never a fresh independent control.

Prepare up to 40 distinct real decision states, one pair per state, at most two
states per match. Use deterministic seed 42 and round-robin candidate categories:
same-target attackers, kill/survive contrast, spell targets, face/trade, attack/end,
conditional-mechanics/Policy disagreement. Include rare SELF classes explicitly.
Reserve up to five scarce verified comparisons before category round-robin, with
the same one-state/two-per-match caps. Local certificates remain unlabelled.
All alternatives must belong to the unchanged complete legal menu. No synthetic
counterfactual states or player-choice labels. Model disagreement is a diagnostic
candidate, not proof of an ID shortcut or suboptimal play.

Use frozen Policy v2 SHA 044b9b50cd6b33912faf8dabe42d919305cb238a8d5cbfb1edf30bb3689d1e4d
for diagnostic scores only. Cache full-menu scores separately from the blind pack.
Use existing Action Outcome and COMBAT-REALITY local facts, retaining conditional
values and their unknowns. Mechanical scope never becomes strategic optimality.

Offline HTML shows visible state, card text, complete menu and both consequences.
Policy scores and actual selection are excluded from the HTML and loaded separately
only after an initial label. Four outcomes: A/B/equivalent/insufficient. Confidence,
basis, aspect and written explanation are required. Human labels start empty.
Optional second independent review is separately exported. Preserve initial blind
annotation and subsequent corrections; validation rejects contradictions, stale
pair hashes, duplicate pair labels and unproved mechanical bases.

Only public code, schema, aggregate inventory and documentation are published.
Detailed states, scored menus, annotations and derived preferences remain ignored.
Report mechanical-review eligibility separately from completed preference labels.
An unannotated 40-case pack is not a training-ready dataset.
