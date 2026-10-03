# Verification proposal — `royal_librarian_trade_silence_verification_v1`

## Semantic contract

Verification-only candidate `CORE_SW_066` (Royal Librarian): a 3/4 neutral minion with Tradeable; when played it silences the chosen minion. Tradeable returns one replacement card while Librarian is in hand, and the Battlecry silences only its selected target.

## Existing implementation and dependencies

- Existing generated `CardDef` plus effect-composition declaration for the silence Battlecry.
- Existing native composition scenario checks a previously buffed enemy Yeti loses its enchantment when targeted. The Rosetta-generated card-specific scenario covers base card data/Tradeable handling.
- Existing bridge scenario checks one Tradeable action, hand-size-preserving replacement, then a legal friendly target and resulting silence.
- No fixed card dependency, generated outcome, dynamic pool, session/class blocker, or new event-order behavior found.

## Scope and verification

One profile root in the Demon Hunter deck. Reuse existing Tradeable, target legality, SilenceTask, and action encoding. No production engine/declaration changes. Record scoped verification only; no dependency closure or training admission claim.

## Completion record

## Candidate result — deferred, no evidence promoted

Observed elapsed audit time: **262.545 seconds** (4 min 22.545 s), measured from `time.perf_counter_ns()` before the review. Two focused native scenarios passed (4 + 4 assertions): base `SW_066` and the existing effect-composition silence case. The bridge/action check did not pass: although a supported friendly minion was on board, the configured bridge did not expose a `PLAY_CARD` action for `CORE_SW_066` on turn five. The pre-existing broad smoke also failed earlier because its free-minion assumption was not met. Since the requirement/action parity is unresolved, this is not a clean verification package. No evidence row was written, no production change was made, and the candidate is deferred for an independent action-legality audit.
