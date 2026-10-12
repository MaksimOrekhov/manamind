"""ML-POLICY-SHADOW-1: parallel Retrained-v2 / Policy-v3 comparison next to the displayed Policy, journal only."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import ml_policy_v3_compare as compare  # noqa: E402
import model_shadow_replay as replay  # noqa: E402
import run_manamind  # noqa: E402
from model_shadow_replay import FaultyPolicy  # noqa: E402
import test_live_recommendation  # noqa: E402
from live_fixtures import CANARIES, LiveLog  # noqa: E402
from test_outcome_shadow import record_log, two_decision_log  # noqa: E402
from test_real_policy_dataset import fixture  # noqa: E402
from test_real_policy_training import metadata  # noqa: E402
from manamind.cards.catalog import CardCatalog  # noqa: E402
from manamind.encoding.state_encoder import StateEncoder  # noqa: E402
from manamind.integrations.powerlog.policy_import import extract_match  # noqa: E402
from manamind.models.policy_v2 import PolicyNetworkV2, feature_contract  # noqa: E402
from manamind.models.policy_v3 import PolicyNetworkV3  # noqa: E402
from manamind.policy_shadow import analysis  # noqa: E402
from manamind.policy_shadow.journal import ModelShadowJournal  # noqa: E402
from manamind.policy_shadow.models import ModelUnavailable, load_experimental, load_models  # noqa: E402
from manamind.policy_shadow.shadow import ModelShadow, ShadowFailed, ShadowStats  # noqa: E402
from manamind.policy_shadow.worker import ModelShadowWorker  # noqa: E402
from manamind.training.policy_checkpoint import save_policy_checkpoint  # noqa: E402

CATALOG = CardCatalog.from_json(ROOT / "data/cards/standard_current_enUS.json")
recommender = test_live_recommendation.recommender      # the Policy v1/v2 fixture of the LIVE tests


def make_checkpoint(tmp_path: Path, kind: str, seed: int) -> tuple[Path, str]:
    encoder = StateEncoder(CATALOG)
    contract = feature_contract(encoder)
    shape = dict(card_count=encoder.vocabulary.card_count, state_feature_count=len(contract["state_feature_names"]),
                 entity_feature_count=len(contract["entity_feature_names"]), hidden_size=16)
    torch.manual_seed(seed)
    policy = PolicyNetworkV2(**shape) if kind == "v2" else PolicyNetworkV3(**shape, heads=2)
    path = tmp_path / f"{kind}_{seed}.pt"
    save_policy_checkpoint(path, policy, encoder, metadata())
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def experimental(tmp_path):
    (a, sha_a), (b, sha_b) = make_checkpoint(tmp_path, "v2", 11), make_checkpoint(tmp_path, "v3", 12)
    models, failures = load_models([("retrained_v2", a, sha_a), ("policy_v3", b, sha_b)], CATALOG)
    assert not failures
    return models, {"retrained": (a, sha_a), "v3": (b, sha_b)}


@pytest.fixture
def recording(tmp_path):
    log = two_decision_log()
    split = next(i for i, line in enumerate(log.lines) if "SendOption" in line)
    return record_log(tmp_path, log.lines, pause_at=split)


# ----- loading: pinned digests and strict compatibility ---------------------------------------------------------------


def test_a_checkpoint_loads_only_with_its_pinned_digest_schema_and_runtime_catalog(tmp_path):
    path, sha = make_checkpoint(tmp_path, "v3", 1)
    model = load_experimental("policy_v3", path, sha, CATALOG)
    assert model.sha256 == sha and model.schema == "manamind.real_policy/3" and model.representation == 3
    assert not any(p.requires_grad for p in model.policy.parameters())
    for pin in ("0" * 64, "not a digest", sha.upper()):
        with pytest.raises(ModelUnavailable) as refused:
            load_experimental("policy_v3", path, pin, CATALOG)
        assert refused.value.reason == "CHECKPOINT_IDENTITY_MISMATCH"
    with pytest.raises(ModelUnavailable) as missing:
        load_experimental("policy_v3", tmp_path / "absent.pt", sha, CATALOG)
    assert missing.value.reason == "CHECKPOINT_UNREADABLE"
    with pytest.raises(ModelUnavailable) as foreign:
        load_experimental("policy_v3", path, sha, CardCatalog())
    assert foreign.value.reason == "RUNTIME_CATALOG_MISMATCH"
    payload = torch.load(path, weights_only=True)
    payload["state_encoding_schema_version"] = -1
    broken = tmp_path / "broken.pt"
    torch.save(payload, broken)
    with pytest.raises(ModelUnavailable) as incompatible:
        load_experimental("policy_v3", broken, hashlib.sha256(broken.read_bytes()).hexdigest(), CATALOG)
    assert incompatible.value.reason == "CHECKPOINT_INCOMPATIBLE"
    assert "broken" not in str(incompatible.value) and str(tmp_path) not in str(incompatible.value)


def test_one_bad_checkpoint_never_disables_the_other_and_duplicates_are_refused(tmp_path):
    good, sha = make_checkpoint(tmp_path, "v2", 3)
    other, other_sha = make_checkpoint(tmp_path, "v3", 4)
    models, failures = load_models(
        [("retrained_v2", good, "f" * 64), ("policy_v3", other, other_sha), ("copy", other, other_sha),
         ("primary_again", good, sha)], CATALOG, reserved_sha256={sha})
    assert [m.name for m in models] == ["policy_v3"]
    assert failures == {"retrained_v2": "CHECKPOINT_IDENTITY_MISMATCH", "copy": "DUPLICATE_CHECKPOINT",
                        "primary_again": "DUPLICATE_CHECKPOINT"}


# ----- the three models see the same decision -------------------------------------------------------------------------


def run(tmp_path, recording, recommender, models, *, name="on", **kwargs):
    return replay.run_model_runtime(recording, recommender, tmp_path / name, models=models, **kwargs)


def test_every_model_scores_the_same_state_and_menu_and_the_displayed_top3_is_unchanged(
        tmp_path, recording, recommender, experimental):
    policy, _ = recommender
    models, _ = experimental
    plain = run(tmp_path, recording, policy, models, name="off", threaded=False, shadow=False)
    shadowed = run(tmp_path, recording, policy, models, threaded=False)
    assert all(replay.same_player_view(plain, shadowed).values())
    rows = [r for r in shadowed.model_rows if r["event"] == "MODEL_SHADOW"]
    recommendations = [r for r in shadowed.journal if r["event"] == "RECOMMENDATION"]
    assert len(rows) == shadowed.scored == len(recommendations) >= 1
    for row, shown in zip(rows, recommendations):
        assert (row["decision_id"], row["state_hash"], row["match_id"]) == (
            shown["decision_id"], shown["state_hash"], shown["match_id"])
        primary, retrained, v3 = row["models"]
        assert [m["name"] for m in row["models"]] == ["policy_v2", "retrained_v2", "policy_v3"]
        assert [m["role"] for m in row["models"]] == ["primary", "experimental", "experimental"]
        assert primary["checkpoint_sha256"] == shown["checkpoint_sha256"] == policy.checkpoint_sha256
        assert [t["action"] for t in primary["top3"]] == [t["action"] for t in shown["top3"]]
        assert primary["reproduced"] is True and primary["max_abs_logit_diff"] <= 1e-5
        assert retrained["inputs_sha256"] == v3["inputs_sha256"]          # v2 and v3 are fed identical tensors
        assert retrained["checkpoint_sha256"] != v3["checkpoint_sha256"] != primary["checkpoint_sha256"]
        assert row["menu_size"] == len(row["actions"]) == len(retrained["ranks"]) == len(v3["ranks"])
        for entry in row["models"]:
            assert sorted(entry["ranks"]) == list(range(1, row["menu_size"] + 1))
            assert entry["top3"][0]["rank"] == 1 and entry["top1_type"] == entry["top3"][0]["type"]
            assert entry["inference_ms"] >= 0 and entry["status"] == "OK"
        assert "handle" not in json.dumps(row)
    assert re.fullmatch(r"model shadow: \d+/\d+ decisions recorded.*", shadowed.model_summary)


def test_shadow_rows_hold_no_hidden_information_and_no_raw_text(tmp_path, recommender, experimental):
    policy, _ = recommender
    models, _ = experimental
    log = LiveLog(canaries=True).create_game().mulligan()
    log.canary_reveals()
    log.opponent_hand_identity()
    log.self_decision(1)
    result = run(tmp_path, record_log(tmp_path, log.lines), policy, models, threaded=False)
    assert [r for r in result.model_rows if r["event"] == "MODEL_SHADOW"]
    blob = json.dumps(result.model_rows)
    for canary in CANARIES:
        assert canary not in blob
    assert "handle" not in blob and "Opponent#" not in blob


def test_the_threaded_production_mode_writes_the_same_rows_without_changing_what_the_player_sees(
        tmp_path, recording, recommender, experimental):
    policy, _ = recommender
    models, _ = experimental
    plain = run(tmp_path, recording, policy, models, name="off", threaded=False, shadow=False)
    inline = run(tmp_path, recording, policy, models, name="sync", threaded=False)
    background = run(tmp_path, recording, policy, models, name="thread", threaded=True, pace_ms=60)
    assert all(replay.same_player_view(plain, background).values())
    keep = lambda rows: [{k: v for k, v in r.items() if k not in {"at_utc", "total_ms"} and k != "models"} |   # noqa: E731
                         {"models": [{k: v for k, v in m.items() if not k.endswith("_ms")} for m in r["models"]]}
                         for r in rows if r["event"] == "MODEL_SHADOW"]
    assert keep(background.model_rows) == keep(inline.model_rows) and keep(inline.model_rows)


# ----- independence: a failing, invalid, slow or unwritable model never reaches the Policy path -----------------------


@pytest.mark.parametrize("mode,reason", [("raise", "INFERENCE_FAILED"), ("nan", "INVALID_MODEL_OUTPUT")])
def test_a_failing_model_is_recorded_alone_and_the_other_model_and_the_policy_are_untouched(
        tmp_path, recording, recommender, experimental, mode, reason):
    policy, _ = recommender
    models, _ = experimental
    plain = run(tmp_path, recording, policy, models, name="off", threaded=False, shadow=False)
    broken = [dataclasses.replace(m, policy=FaultyPolicy(m.policy, mode)) if m.name == "policy_v3" else m for m in models]
    faulty = run(tmp_path, recording, policy, broken, threaded=False)
    assert all(replay.same_player_view(plain, faulty).values())
    rows = [r for r in faulty.model_rows if r["event"] == "MODEL_SHADOW"]
    assert rows
    for row in rows:
        by_name = {m["name"]: m for m in row["models"]}
        assert by_name["policy_v3"]["status"] == "ERROR" and by_name["policy_v3"]["reason"] == reason
        assert by_name["retrained_v2"]["status"] == by_name["policy_v2"]["status"] == "OK"
        assert "top3" not in by_name["policy_v3"]
    assert faulty.model_stats.models["policy_v3"].error == len(rows) and faulty.model_stats.models["retrained_v2"].ok == len(rows)


def test_a_model_over_the_budget_causes_the_next_model_to_be_skipped_not_the_policy_to_wait(
        tmp_path, recording, recommender, experimental):
    policy, _ = recommender
    models, _ = experimental
    slow = [dataclasses.replace(models[0], policy=FaultyPolicy(models[0].policy, "slow", 0.08)), models[1]]
    run_ = run(tmp_path, recording, policy, slow, threaded=False, budget_ms=40)
    for row in (r for r in run_.model_rows if r["event"] == "MODEL_SHADOW"):
        first, second = row["models"][1:]
        assert first["status"] == "OK" and first["over_budget"] is True
        assert second["status"] == "SKIPPED" and second["reason"] == "BUDGET_EXCEEDED"


def test_a_slow_model_in_the_background_costs_the_displayed_recommendation_nothing(
        tmp_path, recording, recommender, experimental):
    policy, _ = recommender
    models, _ = experimental
    slow = [dataclasses.replace(m, policy=FaultyPolicy(m.policy, "slow", 0.5)) for m in models]
    plain = run(tmp_path, recording, policy, models, name="off", threaded=False, shadow=False)
    started = time.perf_counter()
    background = run(tmp_path, recording, policy, slow, threaded=True)
    assert all(replay.same_player_view(plain, background).values())
    assert max(background.decision_step_ms) < 250                       # hand-over only, not 2 x 0.5 s of inference
    assert time.perf_counter() - started < 20


def test_an_unwritable_journal_is_counted_and_never_reaches_the_policy(tmp_path, recording, recommender, experimental):
    policy, _ = recommender
    models, _ = experimental
    plain = run(tmp_path, recording, policy, models, name="off", threaded=False, shadow=False)
    broken = run(tmp_path, recording, policy, models, threaded=False, break_journal=True)
    assert all(replay.same_player_view(plain, broken).values())
    assert broken.model_stats.journal_failures >= 1 and broken.model_stats.recorded == 0


def test_a_shadow_that_cannot_read_the_state_fails_closed_with_a_stable_code(recommender, experimental):
    policy, _ = recommender
    models, _ = experimental
    shadow = ModelShadow(policy.policy, policy.encoder, policy.checkpoint_sha256, models)
    snapshot = SimpleNamespace(game_key="m", seq=1, decision={"options_id": 1}, state_hash="h", state={"x": 1}, turn=1)
    item = SimpleNamespace(index=0, score=0.0, action={"type": "END_TURN", "play_position": 0})
    with pytest.raises(ShadowFailed) as refused:
        shadow.score(snapshot, SimpleNamespace(menu=(item,), identity=("m", 1, 1, "h"), latency_ms=1.0))
    assert refused.value.reason == "STATE_UNREADABLE"
    with pytest.raises(ShadowFailed) as empty:
        shadow.score(snapshot, SimpleNamespace(menu=(), identity=("m", 1, 1, "h"), latency_ms=1.0))
    assert empty.value.reason == "NO_MENU"
    with pytest.raises(ShadowFailed) as other:
        shadow.score(snapshot, SimpleNamespace(menu=(item,), identity=("m", 9, 1, "h"), latency_ms=1.0))
    assert other.value.reason == "RECOMMENDATION_SNAPSHOT_MISMATCH"


# ----- decisions are never mixed ---------------------------------------------------------------------------------------


class GatedShadow:
    """Stands in for ModelShadow: a score that blocks until released, or fails on demand."""

    def __init__(self):
        self.stats = ShadowStats()
        self.gate = threading.Event()
        self.started = threading.Event()
        self.fail = False
        self.gate.set()

    def score(self, snapshot, recommendation, cancelled=lambda: None):
        self.started.set()
        self.gate.wait(5)
        if self.fail:
            raise RuntimeError("boom")
        return {"schema": "manamind.model_shadow/1", "models": [], "for": snapshot.state_hash}


def fake_snapshot(name: str):
    return SimpleNamespace(game_key="match", seq=1, decision={"options_id": 1}, state_hash=name)


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def worker_for(tmp_path, *, threaded=True):
    shadow = GatedShadow()
    journal = ModelShadowJournal(tmp_path / "model_shadow.jsonl")
    return shadow, journal, ModelShadowWorker(shadow, journal, threaded=threaded)


def kinds(journal):
    return [(r["event"], r["state_hash"], r.get("reason")) for r in read_rows(journal.path)]


def test_a_decision_that_changes_while_its_models_run_is_discarded_and_never_scored(tmp_path):
    shadow, journal, worker = worker_for(tmp_path)
    shadow.gate.clear()
    old, new = fake_snapshot("old"), fake_snapshot("new")
    worker.submit(old, None)
    assert shadow.started.wait(5)
    started = time.perf_counter()
    worker.invalidate(old, "DECISION_CHANGED")      # constant time while the models are still running
    worker.submit(new, None)
    assert time.perf_counter() - started < 0.1
    shadow.gate.set()
    assert worker.flush()
    assert kinds(journal) == [("MODEL_SHADOW_DISCARDED", "old", "DECISION_CHANGED_DURING_INFERENCE"),
                              ("MODEL_SHADOW", "new", None)]
    worker.close()


def test_a_queued_decision_that_is_replaced_or_invalidated_is_never_computed(tmp_path):
    shadow, journal, worker = worker_for(tmp_path)
    shadow.gate.clear()
    first, second, third = fake_snapshot("first"), fake_snapshot("second"), fake_snapshot("third")
    worker.submit(first, None)
    assert shadow.started.wait(5)
    worker.submit(second, None)                     # waits behind the running one ...
    worker.submit(third, None)                      # ... and is superseded before it ever starts
    worker.invalidate(third, "TRUST_LOST:UNTRUSTED:INVARIANT")
    shadow.gate.set()
    assert worker.flush()
    rows = kinds(journal)
    assert ("MODEL_SHADOW", "first", None) in rows
    assert ("MODEL_SHADOW_ERROR", "second", "SUPERSEDED_BEFORE_START") in rows
    assert ("MODEL_SHADOW_DISCARDED", "third", "DECISION_CHANGED_BEFORE_START") in rows
    assert not [r for r in rows if r[0] == "MODEL_SHADOW" and r[1] in {"second", "third"}]
    worker.close()


def test_a_written_row_is_followed_by_exactly_one_invalidation(tmp_path):
    shadow, journal, worker = worker_for(tmp_path, threaded=False)
    snap = fake_snapshot("done")
    worker.submit(snap, None)
    worker.invalidate(snap, "GAME_OVER")
    worker.invalidate(snap, "APP_STOP")
    assert kinds(journal) == [("MODEL_SHADOW", "done", None), ("MODEL_SHADOW_INVALIDATION", "done", "GAME_OVER")]


def test_a_crashing_shadow_leaves_a_stable_error_row_and_the_worker_keeps_serving(tmp_path):
    shadow, journal, worker = worker_for(tmp_path)
    shadow.fail = True
    worker.submit(fake_snapshot("bad"), None)
    assert worker.flush()
    shadow.fail = False
    worker.submit(fake_snapshot("good"), None)
    assert worker.flush()
    assert kinds(journal) == [("MODEL_SHADOW_ERROR", "bad", "SHADOW_RUNTIME_ERROR"), ("MODEL_SHADOW", "good", None)]
    assert shadow.stats.failed == 1 and shadow.stats.recorded == 1
    worker.close()


def test_closing_with_a_stuck_model_returns_and_counts_what_was_abandoned(tmp_path):
    shadow, journal, worker = worker_for(tmp_path)
    shadow.gate.clear()
    worker.submit(fake_snapshot("stuck"), None)
    assert shadow.started.wait(5)
    worker.submit(fake_snapshot("waiting"), None)
    started = time.perf_counter()
    worker.close(timeout=0.2)
    assert time.perf_counter() - started < 2 and shadow.stats.abandoned == 1
    shadow.gate.set()


# ----- journal, report, cache ----------------------------------------------------------------------------------------


def test_the_journal_rotates_without_losing_rows_and_stays_beside_not_inside_the_policy_journal(tmp_path):
    journal = ModelShadowJournal.beside(tmp_path / "prediction_journal.jsonl", max_bytes=300)
    assert journal.path.name == "prediction_journal.model_shadow.jsonl"
    for i in range(12):
        journal.append({"event": "MODEL_SHADOW", "i": i, "pad": "x" * 100})
    files = sorted(tmp_path.glob("prediction_journal.model_shadow*.jsonl"))
    assert len(files) > 1 and not (tmp_path / "prediction_journal.jsonl").exists()
    assert sorted(r["i"] for f in files for r in read_rows(f)) == list(range(12))


def test_the_report_reads_the_journal_and_proves_the_displayed_top3_is_unchanged(
        tmp_path, recording, recommender, experimental):
    policy, _ = recommender
    models, _ = experimental
    result = run(tmp_path, recording, policy, models, threaded=False)
    report = analysis.analyse(result.model_rows, result.journal)
    integrity = report["integrity"]
    assert integrity["decisions"] == result.scored and integrity["problems"] == {}
    assert integrity["displayed_top3_checked_against_prediction_journal"] == result.scored
    assert integrity["displayed_top3_mismatches"] == 0 and integrity["duplicate_decision_rows"] == 0
    assert set(report["models"]) == {"policy_v2", "retrained_v2", "policy_v3"}
    assert report["latency"]["model_inference_ms_encode_plus_forward"]["policy_v3"]["all"]["n"] == result.scored
    assert set(report["agreement"]) == {"policy_v2|retrained_v2", "policy_v2|policy_v3", "retrained_v2|policy_v3"}
    assert "hero_power" in report["categories"]["per_model"]["policy_v3"]
    assert "decisions" in analysis.render(report)
    tampered = [json.loads(json.dumps(r)) for r in result.journal]
    next(r for r in tampered if r["event"] == "RECOMMENDATION")["top3"].reverse()
    mismatch = analysis.analyse(result.model_rows, tampered)["integrity"]["displayed_top3_mismatches"]
    assert mismatch >= 1 or len(next(r for r in tampered if r["event"] == "RECOMMENDATION")["top3"]) == 1


def synthetic_row(index: int, *, hero_power: tuple[str, str], klass="DEMONHUNTER", mana=2, lethal=False) -> dict:
    actions = [{"index": 0, "type": "END_TURN", "sha": "a"}, {"index": 1, "type": "HERO_POWER", "sha": "b"},
               {"index": 2, "type": "PLAY_CARD", "sha": "c"}]
    detail = {0: {"type": "END_TURN", "play_position": 0}, 1: {"type": "HERO_POWER", "play_position": 0},
              2: {"type": "PLAY_CARD", "card_id": "X", "play_position": 1}}

    def entry(name, role, top, sha):
        order = [top] + [i for i in (0, 1, 2) if i != top]
        return {"name": name, "role": role, "status": "OK", "checkpoint_sha256": sha, "inputs_sha256": "in",
                "inference_ms": 1.0, "live_latency_ms": 1.0, "reproduced": True,
                "ranks": [order.index(i) + 1 for i in (0, 1, 2)], "top1_type": detail[top]["type"],
                "top3": [{"rank": r, "index": i, "type": detail[i]["type"], "action": detail[i]} for r, i in enumerate(order, 1)]}
    kinds_ = {"HERO_POWER": 1, "PLAY_CARD": 2, "END_TURN": 0}
    return {"event": "MODEL_SHADOW", "decision_id": f"m:{index}", "match_id": "m", "state_hash": "s", "turn": index,
            "self_class": klass, "opponent_class": "ROGUE", "mana": mana, "menu_size": 3, "actions": actions,
            "face_attack_lethal_candidate": lethal, "total_ms": 3.0,
            "models": [entry("policy_v2", "primary", kinds_[hero_power[0]], "p"),
                       entry("retrained_v2", "experimental", kinds_[hero_power[1]], "r"),
                       entry("policy_v3", "experimental", 2, "v")]}


def test_the_comparison_surfaces_hero_power_and_end_turn_divergences_of_a_class():
    rows = [synthetic_row(1, hero_power=("HERO_POWER", "PLAY_CARD")), synthetic_row(2, hero_power=("HERO_POWER", "PLAY_CARD")),
            synthetic_row(3, hero_power=("PLAY_CARD", "PLAY_CARD"), mana=3), synthetic_row(4, hero_power=("END_TURN", "PLAY_CARD"))]
    report = analysis.analyse(rows)
    cats = report["categories"]
    assert cats["per_model"]["policy_v2"]["hero_power"]["top1_share_when_legal"] == 0.5
    assert cats["per_model"]["retrained_v2"]["hero_power"]["top1_share_when_legal"] == 0.0
    assert cats["per_model"]["policy_v2"]["hero_power"]["demon_hunter_by_available_mana"]["2"]["top1_hero_power"] == 0.6667   # 2 of 3 two-mana rows
    assert cats["per_model"]["policy_v2"]["hero_power"]["demon_hunter_by_available_mana"]["3-4"]["top1_hero_power"] == 0.0
    assert cats["disagreements"]["policy_v2|retrained_v2"]["hero_power_only_policy_v2"]["count"] == 2
    assert cats["disagreements"]["policy_v2|retrained_v2"]["end_turn_only_policy_v2"]["count"] == 1
    assert cats["per_model"]["policy_v2"]["end_turn"]["top1_end_turn"] == 1
    assert report["agreement"]["retrained_v2|policy_v3"]["top1_agree"] == 1.0


def test_a_journal_that_mixes_checkpoint_versions_is_flagged():
    first, second = synthetic_row(1, hero_power=("PLAY_CARD", "PLAY_CARD")), synthetic_row(2, hero_power=("PLAY_CARD", "PLAY_CARD"))
    second["models"][2]["checkpoint_sha256"] = "other"
    assert analysis.analyse([first, second])["integrity"]["multiple_checkpoint_versions_in_one_journal"] == ["policy_v3"]


def test_the_logits_cache_is_bound_to_the_checkpoint_dataset_and_code_identity(tmp_path):
    rows, _ = extract_match(fixture(45).lines, CATALOG)
    first, sha_first = make_checkpoint(tmp_path, "v2", 21)
    second, sha_second = make_checkpoint(tmp_path, "v2", 22)
    cache = tmp_path / "cache"
    a = compare.cached_logits(cache, first, rows, "d" * 64)
    assert compare.cached_logits(cache, first, rows, "d" * 64) == a        # a verified hit
    assert len(list(cache.glob("*.json"))) == 1 and sha_first[:16] in next(cache.glob("*.json")).name
    first.write_bytes(second.read_bytes())                                 # the same path now holds another model
    b = compare.cached_logits(cache, first, rows, "d" * 64)
    assert b != a and len(list(cache.glob("*.json"))) == 2                 # recomputed under its own digest
    other_dataset = compare.cached_logits(cache, first, rows, "e" * 64)
    assert other_dataset == b and len(list(cache.glob("*.json"))) == 3
    entry = next(cache.glob(f"logits_{sha_second[:16]}_{'d' * 16}_*.json"))
    payload = json.loads(entry.read_text(encoding="utf-8"))
    payload["checkpoint_sha256"] = "0" * 64                                # a forged file under a valid name
    payload["logits"] = {k: [0.0] * len(v) for k, v in payload["logits"].items()}
    entry.write_text(json.dumps(payload), encoding="utf-8")
    assert compare.cached_logits(cache, first, rows, "d" * 64) == b
    assert not (tmp_path / "logits_cache.pkl").exists()


# ----- launcher and boundaries -----------------------------------------------------------------------------------------


def test_the_model_shadow_is_off_by_default_and_unreachable_from_live_and_apps():
    args = run_manamind.build_parser().parse_args([])
    assert args.model_shadow is False
    assert args.model_shadow_retrained_sha256 == run_manamind.RETRAINED_V2_SHA256
    assert args.model_shadow_v3_sha256 == run_manamind.POLICY_V3_SHA256
    assert run_manamind.UnifiedRuntime(SimpleNamespace(session=None), None, None).model_shadow is None
    for path in list((ROOT / "src/manamind/live").rglob("*.py")) + list((ROOT / "apps").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(?:from|import)\s+manamind\.policy_shadow", text, re.MULTILINE), path
        assert "ModelShadow" not in text, path
    for name in ("outcome", "strategy"):                                   # the other shadows stay independent
        for path in (ROOT / "src/manamind" / name).rglob("*.py"):
            assert "policy_shadow" not in path.read_text(encoding="utf-8"), path


def test_the_launcher_wires_the_model_shadow_only_on_request_and_degrades_per_checkpoint(
        tmp_path, monkeypatch, capsys, recommender, experimental):
    policy, checkpoint = recommender
    models, paths = experimental
    constructed = []
    original = run_manamind.UnifiedRuntime

    class Spy(original):
        def __init__(self, *args, **kwargs):
            constructed.append(kwargs.get("model_shadow"))
            super().__init__(*args, **kwargs)

    def stop(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(run_manamind, "UnifiedRuntime", Spy)
    monkeypatch.setattr(run_manamind.time, "sleep", stop)
    base = ["--logs-root", str(tmp_path / "Logs"), "--data-root", str(tmp_path / "data"),
            "--checkpoint", str(checkpoint), "--checkpoint-sha256", policy.checkpoint_sha256]
    pins = ["--model-shadow-retrained", str(paths["retrained"][0]), "--model-shadow-retrained-sha256", paths["retrained"][1],
            "--model-shadow-v3", str(paths["v3"][0]), "--model-shadow-v3-sha256", paths["v3"][1]]
    assert run_manamind.main(base) == 0
    assert run_manamind.main([*base, "--model-shadow", *pins]) == 0
    assert run_manamind.main([*base, "--model-shadow", *pins[:2], "--model-shadow-retrained-sha256", "0" * 64,
                              *pins[4:]]) == 0
    assert run_manamind.main(["--logs-root", str(tmp_path / "Logs"), "--data-root", str(tmp_path / "data"),
                              "--checkpoint", str(tmp_path / "missing.pt"), "--model-shadow", *pins]) == 0
    printed = capsys.readouterr().out
    assert constructed[0] is None
    assert isinstance(constructed[1], ModelShadowWorker) and "model shadow: no decisions" in printed
    assert [m.name for m in constructed[1].shadow.models] == ["retrained_v2", "policy_v3"]
    assert [m.name for m in constructed[2].shadow.models] == ["policy_v3"]       # the other model still runs
    assert "retrained_v2 unavailable (CHECKPOINT_IDENTITY_MISMATCH)" in printed
    assert constructed[3] is None and "no primary Policy; shadow disabled" in printed
    assert str(tmp_path) not in printed
