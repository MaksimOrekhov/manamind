# Compiler instruction recorded before generation

You are the Codex LLM author of Card IR v0.1 declarations, not an independent gold reviewer.
For the first 12 IDs in protocol.json, in that order, use the pinned text and metadata,
Stage A IR_SPEC.md and existing vocabulary.py/validate.py contracts. Produce JSON declarations
with ir, card_id, snapshot, role=sample, original cleaned text and its SHA-256, abilities,
keywords if applicable, dependencies, decisions, unexpressed spans and computed status.
Do not use per-card executable code or invent vocabulary. Encode only known supported pieces;
unexpressible text remains explicitly unexpressed, with general extension proposals outside IR.
Keep ambiguous token/pool/mechanic rules as typed dependencies. Record outcome-changing choices
with alternatives and discriminating cases; unknown means UNRESOLVED, not a guessed rule.
Respect source exclusions, binding, sequential order, zones, ownership and text marks.
Write initial output under raw/ BEFORE running checks. Never revise those files.
Run baseline structural validation, old lexical lint, new general lint, and reverse rendering.
Record every warning and author correction; store final/ separately, including unchanged files.
Do not call self-review semantic accuracy. Stop after these 12; remaining 48 are reserved.

Delivery in this environment uses ordinary file tools to serialize LLM-authored JSON; these
serialization helpers are not an independent compiler and do not perform semantic generation.
No exact model revision or sampling settings are exposed. No API token/latency claims.
