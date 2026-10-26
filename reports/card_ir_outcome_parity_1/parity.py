"""Paired offline IR/text experiment. Forecast phase precedes all truth scoring.

Outputs contain aggregate statistics and numbered events only. Private input
identities/context and predictions remain under ignored data/processed_real.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

from adapter import forecast_ir  # noqa: E402
from data_access import CARDS, PRIVATE, AllowedData, read, selected, write_new  # noqa: E402
from scoring import score_precomputed  # noqa: E402
from manamind.card_metadata import CardMetadata  # noqa: E402
from manamind.domain.serialization import game_state_from_dict  # noqa: E402
from manamind.integrations.powerlog.observed_facts import ObservedFacts  # noqa: E402
from manamind.outcome.forecast import forecast_action  # noqa: E402
from manamind.outcome.model import Forecast, Status  # noqa: E402
from manamind.outcome.observation import context_from_observed  # noqa: E402
from manamind.outcome.texts import TextSource  # noqa: E402
from manamind.outcome.verify import LoggedDecision, role_of  # noqa: E402


def decision(row):
    action = row["legal_actions"][row["chosen_action_index"]]
    return LoggedDecision(row["game_id"], int(row["decision_id"].rsplit(":", 1)[1]), row["decision_id"],
                          game_state_from_dict(row["state"]), action, tuple(row["legal_actions"]))


def signature(forecast):
    """Numerical/state claims independent of explanations or original text labels."""
    return (forecast.status.value, forecast.unsupported_reason,
            tuple((c.ref, c.field, c.before, c.after, c.at_least, c.at_most, c.role) for c in forecast.changes),
            tuple((e.kind, e.subject, e.amount) for e in forecast.events))


def target_paths(current, forecast):
    """Direct target and Lifesteal fields only; deaths/resources/collateral are separate."""
    action = current.action
    side = action.get("target_side")
    if action.get("target_kind") == "HERO":
        paths = {f"{side}.hero.{field}" for field in ("health", "armor", "divine_shield")}
    else:
        player = current.state.self_player if side == "SELF" else current.state.opponent
        index = next((i for i, e in enumerate(player.board) if e.board_position == action.get("target_board_position")
                      and e.card.card_id == action.get("target_card_id")), None)
        prefix = f"{side}.board[{index}:{action.get('target_card_id')}]"
        paths = {prefix + "." + field for field in ("current_health", "current_attack", "max_health", "divine_shield")}
    hand_index = action.get("hand_index")
    hand_card = current.state.self_hand[hand_index] if isinstance(hand_index, int) and 0 <= hand_index < len(current.state.self_hand) else None
    if (hand_card is not None and "LIFESTEAL" in hand_card.mechanics) or any(e.kind == "HEAL" and e.subject is not None and e.subject.zone == "HERO" and e.subject.side == "SELF"
           for e in forecast.events):
        paths.add("SELF.hero.health")
    return paths


def direct_ready(forecast):
    """Conservative direct claim gate, not merely Forecast.EXACT or mana bookkeeping."""
    return (forecast.status is not Status.UNSUPPORTED
            and not any(u.alters_listed for u in forecast.unknowns)
            and not forecast.bounded_changes
            and any(e.kind in ("DAMAGE", "HEAL", "BUFF") for e in forecast.events))


def strata(current, context):
    tags = []
    def known(name, value):
        tags.append(f"{name}:" + ("UNOBSERVED" if value is None else str(value)))
    known("healing_conversion", context.healing_does_damage)
    known("healing_bonus", current.state.self_player.healing_bonus if current.state.self_player.healing_bonus is not None else context.healing_bonus)
    known("healing_doubled", context.spell_healing_doubled)
    known("spell_damage", context.spell_damage if not context.spell_damage_unverified else "PRESENT_UNVERIFIED")
    known("spell_damage_doubled", context.spell_damage_doubled)
    side = current.action.get("target_side")
    player = current.state.self_player if side == "SELF" else current.state.opponent
    if current.action.get("target_kind") == "HERO":
        known("target_shield", player.hero_divine_shield if player.hero_divine_shield is not None else
              context.self_hero_divine_shield if side == "SELF" else context.opponent_hero_divine_shield)
        known("target_armor", player.armor > 0)
        known("target_max_health", player.hero_max_health is not None)
    else:
        entity = next((e for e in player.board if e.board_position == current.action.get("target_board_position")), None)
        known("target_shield", entity.divine_shield if entity else None)
        known("target_immune", entity.immune if entity else None)
    return tags


def score_section(current, following, forecast):
    details = dict(predicted_direct_events=[dict(kind=e.kind, side=e.subject.side if e.subject else None,
                       zone=e.subject.zone if e.subject else None, amount=e.amount,
                       amount_confidence="OWN_EFFECT_KNOWN" if forecast.own_effect_known and e.amount is not None else "UNKNOWN_OR_BOUND")
                       for e in forecast.events if e.kind in ("DAMAGE", "HEAL", "BUFF")],
                   own_effect_known=forecast.own_effect_known)
    if following is None:
        return dict(pair_available=False, status=forecast.status.value, tier=forecast.tier.value,
                    direct_ready=direct_ready(forecast), direct_confirmed=0, direct_contradicted=0, direct_missed=0,
                    verify_effect_confirmed=0, verify_effect_contradicted=0, verify_effect_missed=0,
                    resource_confirmed=0, resource_contradicted=0, resource_missed=0,
                    unknown_tags=sorted({u.tag or u.kind.value for u in forecast.unknowns}),
                    unsupported_reason=forecast.unsupported_reason, uncovered_observed_direct_changes=None,
                    declared_uncovered_direct_changes=None, silent_uncovered_direct_changes=None, direct_change_ledger=[], **details)
    out = score_precomputed(current, following, forecast)
    paths = target_paths(current, forecast)
    # An identity prediction is only an evaluator probe for observed deltas. It
    # uses verify's existing entity alignment even when the real forecast is
    # UNSUPPORTED (production score_pair then returns before counting misses).
    identity_map = {(side, zone, e.board_position): index
                    for side, player in (("SELF", current.state.self_player), ("OPPONENT", current.state.opponent))
                    for zone, entities in (("BOARD", player.board), ("LOCATION", player.locations))
                    for index, e in enumerate(entities)}
    actual = score_precomputed(current, following, Forecast(dict(current.action), "evaluator identity", Status.PARTIAL,
                                                            _candidate=current.state, _after_index=identity_map))
    changed_direct = {p for p in actual.missed if p in paths}
    claimed = set(out.confirmed) | set(out.contradicted)
    uncovered = changed_direct - claimed
    counts = {name: sum(p in paths for p in ledger) for name, ledger in (
        ("direct_confirmed", out.confirmed), ("direct_contradicted", out.contradicted), ("direct_missed", out.missed))}
    for label, ledger in (("confirmed", out.confirmed), ("contradicted", out.contradicted), ("missed", out.missed)):
        counts["verify_effect_" + label] = sum(role_of(p) == "EFFECT" for p in ledger)
        counts["resource_" + label] = sum(role_of(p) == "BOOKKEEPING" for p in ledger)
    ledger = []
    for verdict, items in (("confirmed", out.confirmed), ("contradicted", out.contradicted), ("missed", actual.missed)):
        for path, value in items.items():
            if path not in paths or (verdict == "missed" and path in claimed):
                continue
            # Numeric/boolean direct fields only; no match keys or foreign card IDs.
            label = path.split(".board[")[0] + ".target." + path.rsplit(".", 1)[1] if ".board[" in path else path
            ledger.append(dict(path=label, verdict=verdict, values=list(value) if isinstance(value, tuple) else value))
    return dict(pair_available=True, status=forecast.status.value, tier=forecast.tier.value,
                direct_ready=direct_ready(forecast), **counts,
                uncovered_observed_direct_changes=len(uncovered),
                declared_uncovered_direct_changes=len(uncovered) if not direct_ready(forecast) else 0,
                silent_uncovered_direct_changes=len(uncovered) if direct_ready(forecast) else 0,
                direct_change_ledger=ledger, **details,
                unknown_tags=sorted({u.tag or u.kind.value for u in forecast.unknowns}),
                unsupported_reason=forecast.unsupported_reason)


def aggregate(events, approach):
    rows = [r[approach] for r in events]
    claims = [r for r in rows if r["direct_ready"] and r["pair_available"]]
    eligible = [r for r in claims if r["direct_confirmed"] + r["direct_contradicted"] > 0]
    good = sum(r["direct_confirmed"] for r in claims)
    bad = sum(r["direct_contradicted"] for r in claims)
    return dict(actions=len(rows), next_state_pairs=sum(r["pair_available"] for r in rows),
                own_direct_effect_known=sum(r["own_effect_known"] for r in rows),
                status=dict(Counter(r["status"] for r in rows)), tiers=dict(Counter(r["tier"] for r in rows)),
                checkable_exact_direct_events=len(eligible), coverage_all_actions=len(eligible) / len(rows) if rows else None,
                coverage_pairs=len(eligible) / sum(r["pair_available"] for r in rows) if any(r["pair_available"] for r in rows) else None,
                exact_direct_claims_confirmed=good, exact_direct_claims_contradicted=bad,
                exact_direct_claim_accuracy=good / (good + bad) if good + bad else None,
                exact_direct_missed=sum(r["direct_missed"] for r in claims),
                uncovered_observed_direct_changes=sum(r["uncovered_observed_direct_changes"] or 0 for r in rows),
                declared_uncovered_direct_changes=sum(r["declared_uncovered_direct_changes"] or 0 for r in rows),
                silent_uncovered_direct_changes=sum(r["silent_uncovered_direct_changes"] or 0 for r in rows),
                exact_direct_events_with_contradiction=sum(r["direct_contradicted"] > 0 for r in eligible),
                exact_direct_ready_no_changed_claim=sum(r["direct_ready"] and r["pair_available"] and not r["direct_confirmed"] and not r["direct_contradicted"] for r in rows),
                all_pair_conditional_target_diagnostics={k: sum(r[k] for r in rows) for k in ("direct_confirmed", "direct_contradicted", "direct_missed")},
                all_pair_verify_effect_diagnostics={k: sum(r[k] for r in rows) for k in ("verify_effect_confirmed", "verify_effect_contradicted", "verify_effect_missed")},
                all_pair_resource_diagnostics={k: sum(r[k] for r in rows) for k in ("resource_confirmed", "resource_contradicted", "resource_missed")},
                blockers=dict(Counter(t for r in rows for t in r["unknown_tags"])),
                unsupported_reasons=dict(Counter(r["unsupported_reason"] for r in rows if r["unsupported_reason"])))


def evidence_inventory(source, predictions):
    """Outcome-only phase, after all forecasts; never returns context to a predictor."""
    counts, sides, index = Counter(), Counter(), defaultdict(list)
    for path in source.files("data/processed_evidence/collected", "*/observations.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            obs = json.loads(line)
            s = obs.get("subject", {})
            if s.get("card_id") not in CARDS or s.get("role") not in ("PLAYED_CARD", "CONTROL_SAMPLE"):
                continue
            counts[s["card_id"]] += 1
            sides[s.get("side")] += 1
            if s.get("side") == "SELF" and obs.get("window", {}).get("root_block_type") == "PLAY":
                index[(path.parent.name[:16], obs["public_states"]["before_hash"], s["card_id"])].append(obs)
    matched, packet_rows = 0, []
    for number, r in enumerate(predictions, start=1):
        matches = index.get((r["game"][:16], r["row"]["provenance"]["state_hash"], r["current"].action["card_id"]), [])
        if len(matches) != 1:
            continue
        matched += 1
        obs = matches[0]
        units = {u["unit_id"] for u in obs["window"]["units"] if u["relation_to_subject"] in ("ROOT", "SUBJECT_OWN")}
        facts = [f for f in obs["facts"] if f["unit_id"] in units and f["visibility"] != "OFFLINE_ONLY_HIDDEN"
                 and f["attribution"]["basis"] in ("UNIT_OWNER", "CREATOR_TAG")]
        target_facts = [f["data"]["target"] for f in facts if f["kind"] == "PLAY_TARGET"]
        action = r["current"].action
        # No handle goes to a predictor. For evaluation the PLAY_TARGET witness
        # must match the chosen public side/type (and unique minion identity).
        target_ok = len(target_facts) == 1 and target_facts[0].get("side") == action.get("target_side") and \
            target_facts[0].get("card_type") == action.get("target_kind")
        if target_ok and action.get("target_kind") == "MINION":
            target_ok = target_facts[0].get("card_id") == action.get("target_card_id")
            player = r["current"].state.self_player if action["target_side"] == "SELF" else r["current"].state.opponent
            target_ok = target_ok and sum(e.card.card_id == action["target_card_id"] for e in player.board) == 1
        result = dict(event=number, card_id=action["card_id"], target_witness=target_ok)
        for name in ("baseline", "candidate"):
            forecast = r[name]
            checked, confirmed, contradicted, skipped = 0, 0, 0, Counter()
            if not target_ok:
                skipped["PLAY_TARGET_NOT_UNAMBIGUOUS"] += 1
            elif not forecast.own_effect_known:
                skipped["OWN_EFFECT_OR_MODIFIER_NOT_KNOWN"] += 1
            else:
                for event in forecast.events:
                    if event.kind not in ("DAMAGE", "HEAL") or event.subject is None or event.amount is None:
                        continue
                    kind = "DAMAGE_PACKET" if event.kind == "DAMAGE" else "HEALING_PACKET"
                    actual = [f for f in facts if f["kind"] == kind and
                              f["data"].get("target", {}).get("side") == event.subject.side and
                              f["data"].get("target", {}).get("card_type") == ("HERO" if event.subject.zone == "HERO" else "MINION")]
                    if event.subject.zone != "HERO":
                        actual = [f for f in actual if f["data"]["target"].get("card_id") == event.subject.card_id]
                    if len(actual) != 1:
                        skipped["NO_SINGLE_STRONGLY_ATTRIBUTED_PACKET"] += 1
                        continue
                    data = actual[0]["data"]
                    if kind == "HEALING_PACKET":
                        before, after = data.get("damage_tag_before"), data.get("damage_tag_after")
                        amount = before - after if before is not None and after is not None else None
                    else:
                        amount = data.get("amount")
                    if amount is None:
                        skipped["PACKET_AMOUNT_UNOBSERVED"] += 1
                        continue
                    checked += 1
                    confirmed += amount == event.amount
                    contradicted += amount != event.amount
            result[name] = dict(checked=checked, confirmed=confirmed, contradicted=contradicted, exclusions=dict(skipped),
                                forecast_status=forecast.status.value, own_effect_known=forecast.own_effect_known)
        packet_rows.append(result)
    return dict(allowed_observations_by_card=dict(counts), subject_sides=dict(sides),
                exact_policy_before_hash_joins=matched,
                strongly_attributed_packet_checks=packet_rows,
                packet_summary={name: dict(events_checked=sum(r[name]["checked"] > 0 for r in packet_rows),
                    confirmed=sum(r[name]["confirmed"] for r in packet_rows), contradicted=sum(r[name]["contradicted"] for r in packet_rows),
                    coverage_all_actions=sum(r[name]["checked"] > 0 for r in packet_rows) / len(predictions) if predictions else None,
                    accuracy=(sum(r[name]["confirmed"] for r in packet_rows) / sum(r[name]["checked"] for r in packet_rows))
                    if sum(r[name]["checked"] for r in packet_rows) else None) for name in ("baseline", "candidate")},
                note="No fuzzy association or target-handle guessing. This packet comparator checks already-predicted event kind/target/amount; it does no effect resolution. Separate from outcome.verify net-state path metrics.")


def build():
    source = AllowedData()
    manifest = read(HERE / "data_manifest.json")
    if hashlib.sha256(source.plan_path.read_bytes()).hexdigest() != manifest["split_plan_sha256"]:
        raise ValueError("Split plan changed; do not open cached contexts or match data")
    inputs = read(PRIVATE / "inputs.json")
    # Revalidate membership before rehashing each frozen file; no protected bytes read on rerun.
    for relative, digest in inputs.items():
        path = Path(relative)
        if relative.startswith("data/raw/collected/") and path.stem[:16] not in source.prefixes:
            raise ValueError("Frozen raw input no longer allowed")
        if relative.startswith("data/processed_evidence/") and path.parent.name[:16] not in source.prefixes:
            raise ValueError("Frozen evidence input no longer allowed")
        if relative.startswith("data/processed_policy_prepare_1/dataset/") and path.stem not in source.allowed:
            raise ValueError("Frozen policy input no longer allowed")
        if hashlib.sha256((REPO / path).read_bytes()).hexdigest() != digest:
            raise ValueError("Frozen permitted input changed")
    cache = read(PRIVATE / "contexts.json")
    games, _ = source.policy()
    texts = TextSource.from_files(REPO / "data/cards/standard_current_enUS.json", REPO / "data/outcome/reviewed_texts.json")
    docs = {c: read(REPO / "reports/card_ir_execution_pilot_1/declarations" / (c + ".json")) for c in CARDS}
    meta = CardMetadata.load()
    predictions = []
    for game, rows in sorted(games.items()):
        for i, row in enumerate(rows):
            if not selected(row):
                continue
            current = decision(row)
            observed = cache["contexts"].get(row["decision_id"])
            ctx = context_from_observed(ObservedFacts.from_dict(observed) if observed else None, current.state)
            baseline = forecast_action(current.state, current.action, texts, ctx)
            candidate = forecast_ir(current.state, current.action, texts, ctx, docs[current.action["card_id"]], meta)
            predictions.append(dict(game=game, row=row, row_index=i, current=current, context=ctx,
                                    baseline=baseline, candidate=candidate))
    # Persist predictions before dereferencing ANY next observation or parsing evidence outcomes.
    frozen_predictions = [dict(decision_id=r["current"].decision_id, baseline=r["baseline"].to_dict(), candidate=r["candidate"].to_dict()) for r in predictions]
    prediction_path = PRIVATE / "predictions.json"
    if prediction_path.exists():
        if read(prediction_path) != frozen_predictions:
            raise ValueError("Predictions differ from the write-once pre-truth snapshot")
    else:
        write_new(prediction_path, frozen_predictions)
    events = []
    exclusions = Counter()
    for r in predictions:
        current, rows, i = r["current"], games[r["game"]], r["row_index"]
        following, reason = None, "NO_NEXT_LABELED_DECISION"
        if i + 1 < len(rows):
            candidate = decision(rows[i + 1])
            if candidate.number != current.number + 1:
                reason = "NONCONSECUTIVE_DECISION"
            elif candidate.state.turn_number != current.state.turn_number or candidate.state.active_player != "SELF":
                reason = "NEXT_DECISION_NOT_SAME_SELF_TURN"
            else:
                following, reason = candidate, None
        if reason:
            exclusions[reason] += 1
        events.append(dict(event=len(events) + 1, card_id=current.action["card_id"], target_side=current.action.get("target_side"),
                           target_kind=current.action.get("target_kind"), context_association=cache["reasons"].get(current.decision_id),
                           modifiers=strata(current, r["context"]), after_exclusion=reason,
                           numeric_forecast_equal=signature(r["baseline"]) == signature(r["candidate"]),
                           baseline=score_section(current, following, r["baseline"]),
                           candidate=score_section(current, following, r["candidate"])))
    evidence = evidence_inventory(source, predictions)
    summary = {name: aggregate(events, name) for name in ("baseline", "candidate")}
    by_card = {c: {name: aggregate([e for e in events if e["card_id"] == c], name) for name in summary} for c in CARDS}
    modifier_groups = sorted({m for e in events for m in e["modifiers"]})
    by_modifier = {m: {name: aggregate([e for e in events if m in e["modifiers"]], name) for name in summary} for m in modifier_groups}
    source_paths = [REPO / "src/manamind/outcome" / name for name in
                    ("forecast.py", "world.py", "verify.py", "model.py", "grammar.py", "observation.py")]
    source_paths += list(HERE.glob("*.py")) + [REPO / "src/manamind/card_ir" / name for name in
                                             ("engine_translate.py", "strict_v02.py", "numeric_lint_v02.py")]
    source_paths += list((REPO / "reports/card_ir_execution_pilot_1/declarations").glob("*.json"))
    return dict(id="CARD-IR-OUTCOME-PARITY-1", base_sha="fc501cee81feaa028bca2fd0d9a33b890936a005",
                protocol_commit="2108dc5", validator_fix_commit="c0be622", data_freeze_commit="b73d82f",
                recommendation="INCONCLUSIVE",
                conclusion="IR controls its instructions and matches the baseline numerically on this sample; no measured benefit. One independently attributed packet and missing real coverage of two cards are insufficient for a superiority claim.",
                training_admission=False,
                artifacts=dict(numeric_before="validation_before.json", numeric_after="validation_after.json",
                               numeric_report="VALIDATION_FIX.md", parity_report="PARITY.md", limitations="LIMITATIONS.md",
                               verification="verification.json", technical_mutations="mutations.json",
                               historical_reproduction="history_reproduction.json", historical_verdict_deltas="historical_v02_verdict_deltas.json"),
                source_sha256={p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source_paths)},
                input_manifest=manifest, predictions_before_truth_sha256=hashlib.sha256(prediction_path.read_bytes()).hexdigest(),
                baseline_source="Unchanged manamind.outcome; same texts/context for both; private _Run/World reused",
                input_observation_completeness=dict(pre_action_states=len(events),
                    exact_fact_associations=sum(e["context_association"] == "EXACT_DECISION_AND_STATE_HASH" for e in events),
                    core_modifier_values_known=sum(not any((m.endswith(":UNOBSERVED") or "UNVERIFIED" in m)
                        for m in e["modifiers"] if m.startswith(("healing_bonus:", "healing_doubled:", "healing_conversion:", "spell_damage:", "spell_damage_doubled:"))) for e in events),
                    note="Core arithmetic flags/values only, not proof that every external interaction is observed; unsupported known conversion is counted as observed, not as a forecast"),
                text_fingerprints=texts.fingerprints, analyzed_actions=len(events),
                identical_numerical_forecasts=sum(e["numeric_forecast_equal"] for e in events),
                after_exclusions=dict(exclusions), summary=summary, by_card=by_card, by_modifier=by_modifier,
                evidence=evidence, events=events,
                limits=["Seen allowed data, not protected holdout; only SELF chosen pilot plays in canonical policy files are forecastable.",
                        "No default modifiers. Missing exact pre-action context stays unknown. Active healing-to-damage is unsupported by both resolvers.",
                        "Primary exact direct gate excludes modifiers, bounds and listed-altering reaction uncertainty; lower-bound/local path diagnostics are separate.",
                        "Next-state net paths cannot prove damage/heal packet magnitude on overkill/death or absence of hidden cancelling reactions. Death/resource claims are separate.",
                        "Evidence packet inventory is outcome-only; exact association required, no fuzzy guesses. Exclusions are not successes.",
                        "No random-state engine hydration, new simulator, model training, training labels, native engine changes or LIVE integration.",
                        "Same resolver implies shared strengths and shared errors. Paired equality is not independent rule truth or playing strength."])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = build()
    write_new(args.output, result)
    print(json.dumps(dict(actions=result["analyzed_actions"], equal=result["identical_numerical_forecasts"],
                          summary=result["summary"], evidence=result["evidence"], exclusions=result["after_exclusions"]), indent=2))
