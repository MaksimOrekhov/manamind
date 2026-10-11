"""Can forecasts feed the existing ValueNetwork? A read-only compatibility probe (no training).

Checks (1) whether the stored value checkpoints load under the current encoder contract, (2) whether
the partial after-states of real positions go through the current StateEncoder, and (3) which encoded
features a forecast moves, using the frozen Policy v2 checkpoint only as the source of the encoder
(its card catalog and vocabulary). It scores nothing and writes nothing but the report file.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.encoding.state_encoder import GLOBAL_FEATURE_NAMES, STATE_ENCODING_SCHEMA_VERSION  # noqa: E402
from manamind.outcome import NotExactError, ObservedContext, Status, TextSource, forecast_action  # noqa: E402
from manamind.outcome import demo  # noqa: E402
from manamind.outcome.verify import load_corpus  # noqa: E402
from manamind.training.checkpoint import load_checkpoint  # noqa: E402
from manamind.training.policy_checkpoint import load_policy_checkpoint  # noqa: E402


def locate(path: str) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate
    return next((p / path for p in ROOT.parents if (p / path).exists()), candidate)


def value_checkpoints(paths: list[str]) -> list[dict]:
    rows = []
    for item in paths:
        path = locate(item)
        row = {"path": item, "exists": path.exists()}
        if path.exists():
            try:
                _, vocabulary, payload = load_checkpoint(path)
                row.update(loadable=True, encoder_schema=payload["state_encoding_schema_version"],
                           cards=vocabulary.card_count)
            except Exception as error:                      # noqa: BLE001 - the message is the finding
                row.update(loadable=False, reason=str(error)[:200])
                try:
                    import torch
                    header = torch.load(path, map_location="cpu", weights_only=True)
                    row["stored_format_version"] = header.get("format_version")
                    row["stored_encoder_schema"] = header.get("state_encoding_schema_version")
                except Exception:                           # noqa: BLE001
                    pass
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--policy", default="data/processed_policy_ml2a/seed42_v2/policy.pt")
    parser.add_argument("--corpus", default="data/processed_data_checkpoint_1_20261010/canonical")
    parser.add_argument("--value-checkpoint", nargs="*", default=[
        "checkpoints/value_v1.pt", "checkpoints/value_v1_s2.pt",
        "data/processed_archive_data0b_20261007/processed_real/pilot_splits/checkpoints/value_real_pilot.pt",
        "data/processed_archive_data0b_20261007/processed_real/corrected_import/pilot_splits/checkpoints/value_real_corrected_v3.pt",
        "data/processed_archive_data0b_20261007/processed_real/corrected_import/pilot_splits_19/checkpoints/value_real_19games_v3.pt"])
    parser.add_argument("--supplement", nargs="*", default=[])
    parser.add_argument("--out", default=str(ROOT / "reports" / "action_outcome_1b" / "value_probe.json"))
    args = parser.parse_args()

    _, encoder, _ = load_policy_checkpoint(locate(args.policy))
    texts = TextSource.from_files(ROOT / "data" / "cards" / "standard_current_enUS.json",
                                  ROOT / "data" / "outcome" / "reviewed_texts.json", *args.supplement)
    report: dict = {"current_state_encoding_schema_version": STATE_ENCODING_SCHEMA_VERSION,
                    "value_checkpoints": value_checkpoints(args.value_checkpoint)}

    # (2) real positions: only EXACT forecasts yield a position; a PARTIAL one must not reach the encoder
    games = load_corpus(locate(args.corpus))
    status, encoded, failed = Counter(), 0, 0
    partial_blocked, partial_leaked, undetermined = 0, 0, 0
    for items in games.values():
        for decision in items:
            forecast = forecast_action(decision.state, decision.action, texts)
            status[forecast.status.value] += 1
            if forecast.status is Status.EXACT:
                try:
                    encoder.encode(forecast.exact_state())
                    encoded += 1
                except Exception:                            # noqa: BLE001
                    failed += 1
                continue
            partial = forecast.partial_state()
            if partial is None:
                continue
            undetermined += bool(partial.undetermined)
            try:
                encoder.encode(partial)                      # type: ignore[arg-type]
                partial_leaked += 1
            except (AttributeError, TypeError):
                partial_blocked += 1
            try:
                forecast.exact_state()
                partial_leaked += 1
            except NotExactError:
                pass
    report["real_positions"] = {
        "forecasts": dict(status), "exact_states_encoded": encoded, "exact_states_failed": failed,
        "partial_forecasts_rejected_by_encoder": partial_blocked, "partial_forecasts_that_leaked": partial_leaked,
        "partial_forecasts_with_undetermined_fields": undetermined}

    # (3) which encoded features does a controlled forecast move?
    scenario = demo.hold_them_off()
    demo_texts = demo.demo_texts(texts)
    context = ObservedContext(healing_does_damage=False, hand_keywords_match_card=True, trust_spell_damage=True,
                              spell_healing_doubled=False)
    before = encoder.encode(scenario.state)
    moves = []
    for action in scenario.actions:
        forecast = forecast_action(scenario.state, action, demo_texts, context)
        if forecast.status is not Status.EXACT:
            continue
        after = encoder.encode(forecast.exact_state())
        global_delta = {name: round(float(a - b), 4) for name, a, b in zip(
            GLOBAL_FEATURE_NAMES, after.global_features, before.global_features, strict=True) if a != b}
        zones = {}
        for zone in ("self_board", "opponent_board", "self_hand"):
            old, new = getattr(before, zone), getattr(after, zone)
            zones[zone] = {"entities_before": int(len(old.card_ids)), "entities_after": int(len(new.card_ids)),
                           "numeric_changed": bool(old.numeric.shape != new.numeric.shape
                                                   or not np.array_equal(old.numeric, new.numeric))}
        moves.append({"action": forecast.label, "global_feature_changes": global_delta, "zones": zones})
    report["controlled_feature_movement"] = moves

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("value_checkpoints", "real_positions")}, indent=1)[:3000])
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
