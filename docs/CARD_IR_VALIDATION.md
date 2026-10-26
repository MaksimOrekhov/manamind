# Strict validation of Card IR v0.1 and v0.2

This is the contract for the **opt-in validation-2 acceptance layer**. It adds no game operations,
parameters or rules to `card-ir/0.1`. Historical `validate_declaration`, `lint_declaration`, `lint_semantics`
and `render` are frozen and still reproduce Stage A/B1 and the independent review.

`card-ir/0.2` (language delta: [reports/card_ir_v02/CHANGELOG.md](../reports/card_ir_v02/CHANGELOG.md)) has its own
modules (`vocabulary_v02`, `validate_v02`, `lint_v02`, `strict_v02`, `render_v02`) and is accepted only through the
same strict layer; see [Card IR v0.2](#card-ir-v02) below.

## Acceptance

```python
from manamind.card_ir.strict import validate_strict
from manamind.card_ir.audit_render import render_audit

report = validate_strict(declaration, metadata, bindings=receipt_or_none)
report.accepted  # no structural/contract errors or warnings; honest PARTIAL is allowed
report.complete  # accepted AND FULL/FULL_DEP; still not gold or execution readiness
lines = render_audit(declaration, metadata, receipt_or_none, report)
```

Use `scripts/validate_card_ir.py` for strict checking from the command line. Exit 0 means acceptance;
exit 1 means rejection; argument/input errors exit 2. The script loads only pinned card metadata.
It never infers a gap receipt from the candidate. `--audit-output` writes a new plain-text file and
refuses overwrite. `--bindings` accepts one receipt or an explicit card-ID-to-receipt registry.

`StrictReport` retains a representation status; it never promotes PARTIAL based on a clean check.
There is no independent semantic gold check, execution or integration with LIVE/Policy.

## Reminders

The strict default accepts only complete parenthesized progress readouts: `(1/3)`, `(2 left!)`,
`(2 turns remaining)`, and the corresponding uses/charges forms. `why` must be nonempty.
No free prose, keyword, action, trigger or conditional becomes trusted merely because an author
calls it a reminder. All reminders, including rejected ones, appear in the audit rendering.

This is deliberately conservative. A genuine keyword explanation such as
`(Can attack minions immediately.)` is **rejected**, although it can correctly explain Rush.
That rejection is measured as a false alert in the validation-2 report. A future verified
explanation registry could admit exact definitions linked to an existing keyword; arbitrary
parentheses or author assertions must never be enough. Until then use explicit review or an
honest linked PARTIAL gap. Do not reinterpret that review requirement as a wrong game rule.

## Gap receipts (external validation data, not IR)

Each `unexpressed` entry needs a non-placeholder explanation and exactly one persisted
receipt entry with an exact path, span and reason. This shallow reason check rejects placeholders;
it does **not** establish the truth of the explanation. Each gap links to declared dependency IDs,
including at least one CORE dependency. Every CORE dependency needs a gap link, an actual `unknown`
node or a decision that references its ID; `card_level: true` alone is insufficient.

```json
{
  "card_id": "ID_FROM_THE_DECLARATION",
  "snapshot": "hsjson_255130_enUS",
  "text_sha256": "SHA256_OF_THE_PINNED_TEXT",
  "gaps": [{
    "gap": "/unexpressed/0",
    "span": "Exact omitted text.",
    "why": "Exact explanation from the declaration.",
    "dependencies": ["missing_contract"]
  }]
}
```

Store the receipt separately and review it together with the declaration. **Never reconstruct it
while validating an edited candidate.** Removing `missing_contract` must fail even when a different
CORE gap still implies PARTIAL. Editing the text/reason or moving gaps makes the receipt stale.
Duplicate/missing paths, missing IDs, mismatched card/snapshot/hash and unanchored CORE dependencies fail.

The supplied `reports/card_ir_validation_2/historical_gap_bindings.json` is an explicit migration
assertion for 11 historical declarations with omissions. It does not modify those declarations or
claim that their author explanations are semantically optimal. Historical PARTIAL without omissions
can use its existing decision/unknown references without a separate receipt.

## Bounded semantic checks

- Operation guards are checked along the operation's actual `if`/`else`/ability-condition ancestry.
  A sibling's condition does not guard it. Health/death and damaged predicates require the corresponding
  entity and polarity in supported templates. A while/if/unless aura needs a condition.
- Non-class/race and except filters require a compatible excluded ALL set in the same zone, not an
  inclusion or a random subset. Other/source exclusion is explicit; unqualified all-minions areas include both sides.
- Modifier windows distinguish this turn, next turn and next matching card. v0.1 cannot silently encode
  next-turn modifiers: use an explicit gap. Trigger timing/turn phase and hero/source/defender roles are visible.
- Undefined `ATTACK_DECLARED.subject` semantics and PLAY-to-HAND reset semantics require an explicit
  OUTCOME decision referencing an UNKNOWN_RULE/CORE dependency. This permits an honest PARTIAL;
  it does not implement either contract. The narrow singular return-to-own-hand template checks source count/zone.
- SHUFFLE cannot represent top/bottom insertion; unsupported positional effects remain linked gaps.
- Malformed shapes fail closed; damaged must be boolean and numeric fields cannot use booleans as numbers.

These are deterministic consistency checks for bounded English patterns, not a general English compiler.
An arbitrary wrong predicate, entity alias, external pool, token relation, timing boundary or client procedure
can still need independent review. An asserted receipt/decision is traceability, not independent proof.

## Audit rendering

`render_audit` displays text spans, conditions (including nested triggers), event roles/filters,
selection modes/zones/exclusions, current/last-known stat reads, durations, use limits, enchantment IDs,
reminders, omissions, dependencies, decisions and rule provenance. Undefined/default fields are labeled;
undefined event subject roles are not silently translated into an attacker. Player-effect applicability
without uses is shown as unspecified, rather than inventing a cardinality. Malformed data renders as
an explicit failure with its original content instead of disappearing.

## Card IR v0.2

```python
from manamind.card_ir.strict_v02 import validate_strict_any, validate_strict_v02

report = validate_strict_any(declaration, metadata, bindings=receipt_or_none)  # picks v0.1 or v0.2 by "ir"
```

`scripts/validate_card_ir.py` uses the same dispatcher; exit codes are unchanged. An unknown `ir` is rejected.

- **One version per declaration.** v0.1 tools reject `card-ir/0.2`; the v0.2 validator rejects `card-ir/0.1`.
  Upgrading a v0.1 declaration is re-authoring: constructs whose meaning changed must be explicit in v0.2
  (player-effect `uses` and cost `zones`, cost `increase` instead of a negative `reduce`, attack roles
  `attacker`/`defender` instead of `subject`), so a relabelled v0.1 declaration does not pass silently.
- **v0.2 strict = v0.2 validator + every validation-2 check** (structure, gap receipts and their migration file,
  CORE anchors, reminders, both v0.1 lints, the strict lint) **+ `lint_v02`.** Only the strict-lint warnings that
  said "v0.1 cannot express this" are dropped, each replaced by a check that the v0.2 encoding is right:
  `WINDOW_NEXT` → `WINDOW_NEXT_V02`, `DECK_POSITION` → `DECK_POSITION_V02`, `RETURN_CONTRACT` → the PLAY→HAND
  rules, `EVENT_ROLE` → attack roles in the validator.
- **Provisional rules.** A v0.2 declaration that needs a rule listed in `vocabulary_v02.PROVISIONAL_RULES`
  (`R_RETURN_FULL_HAND`, `R_SPLIT_UNQUALIFIED`, `R_FREEZE_THAW`, `R_ATTACK_REDIRECT`, `R_DAMAGE_EVENT_AMOUNT`)
  must acknowledge it with an `UNKNOWN_RULE` dependency carrying `"rule": "<id>"` and scope CONDITIONAL or CORE.
  An acknowledgement of a rule the declaration does not need is an error. The scope sets the status honestly.
- **Rule bases.** `DEFINITION` marks a rule that defines an IR construct (turn windows, delayed start, all-matching
  player effects, attack roles) without claiming anything about a card; the card's mapping is its own decision.
  Decision basis `USER_OBSERVED` records the user's game experience; it is a source, not official documentation.
- **Trigger conditions are validated in v0.2.** The frozen v0.1 validator accepts any `condition` on a trigger
  without checking it; v0.1 strict does not close that loophole either.
- `render_audit` renders v0.2 declarations with the v0.2 renderer: zones, delayed start, window, cardinality,
  deck position, attack roles, survival predicates, rule acknowledgements and provisional rule provenance are shown.
  v0.1 declarations render byte-identically to validation-2.

Conformance cases, examples and known blind spots: [reports/card_ir_v02](../reports/card_ir_v02/README.md).
