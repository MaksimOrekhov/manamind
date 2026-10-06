"""Offline evidence extraction from completed Power.log games (EVIDENCE-0B).

This package turns a finished match into sanitized *observations* about cards the ManaEngine
does not support. It is an offline rules-research lane:

* it never feeds a model, the live bridge, the registry or any engine rule;
* it may import ``manamind.live`` / ``manamind.integrations.powerlog`` helpers, but nothing under
  ``encoding``, ``models``, ``training``, ``inference`` or ``live`` may import it
  (enforced by ``tests/test_evidence_boundary.py``);
* it never stores player names, BattleTags, account ids, raw log text or opponent identities that
  SELF could not see.
"""

EXTRACTOR_VERSION = "evidence-0b.1"
OBSERVATION_SCHEMA = "manamind.evidence.observation/1"
GAME_SUMMARY_SCHEMA = "manamind.evidence.game_summary/1"
MANIFEST_SCHEMA = "manamind.evidence.manifest/1"

# Fixed on every observation so a reader cannot mistake it for a proof or a rule.
EVIDENCE_LIMITS = (
    "ABSENCE_OF_AN_EFFECT_IS_NOT_A_NEGATIVE_RULE",
    "NESTED_ONLY_FACTS_ARE_NOT_THE_SUBJECTS_EFFECTS",
    "NOT_RULES_VERIFIED",
    "OBSERVED_OUTCOMES_ARE_SINGLE_DRAWS_NOT_POOLS",
)
