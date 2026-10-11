"""Show the immediate-outcome forecasts of several actions from one position (no Hearthstone needed).

Examples:
  python scripts/action_outcome_demo.py                          # the Hold Them Off! comparison
  python scripts/action_outcome_demo.py --scenario sequencing    # resolution-order counterexamples
  python scripts/action_outcome_demo.py --real 92bfeca6e:81 --corpus data/processed_data_checkpoint_1_20261010/canonical \\
      --only-card JAIL_913                                       # a logged position, its real menu
Add --assume-defaults for the what-if that fills unobserved healing bonus / hero shield with 0 / False,
and --json for machine-readable output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.outcome import ObservedContext, TextSource, forecast_alternatives, render_comparison  # noqa: E402
from manamind.outcome import demo  # noqa: E402
from manamind.outcome.verify import load_corpus  # noqa: E402


def build_texts(args: argparse.Namespace) -> TextSource:
    paths = [ROOT / "data" / "cards" / "standard_current_enUS.json", ROOT / "data" / "outcome" / "reviewed_texts.json"]
    paths += [Path(item) for item in args.supplement]
    return TextSource.from_files(*paths)


def find_data(path: str) -> Path:
    """Resolve a data path; ignored datasets live only in the main checkout, an ancestor of a worktree."""
    candidate = Path(path)
    if candidate.exists():
        return candidate
    for parent in ROOT.parents:
        if (parent / path).exists():
            return parent / path
    return candidate


def show(title: str, state, actions, texts: TextSource, context: ObservedContext, as_json: bool,
         events: bool = False) -> dict | None:
    forecasts = forecast_alternatives(state, actions, texts, context)
    if as_json:
        return {"title": title, "forecasts": [forecast.to_dict() for forecast in forecasts]}
    print(f"\n=== {title}\n{demo.board_summary(state)}\n")
    print(render_comparison(state, forecasts, events=events))
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", choices=("hold-them-off", "sequencing", "all"), default="hold-them-off")
    parser.add_argument("--real", metavar="DECISION_ID_SUFFIX", help="forecast the whole legal menu of a logged decision")
    parser.add_argument("--corpus", default="data/processed_data_checkpoint_1_20261010/canonical")
    parser.add_argument("--only-card", help="with --real: keep only legal actions of this card ID (and END_TURN)")
    parser.add_argument("--supplement", nargs="*", default=[], help="extra card JSON files for tokens (lowest priority)")
    parser.add_argument("--assume-defaults", action="store_true",
                        help="what-if: unobserved healing bonus = 0, no hero Divine Shield, hand keywords = base card")
    parser.add_argument("--events", action="store_true", help="also print the ordered resolution steps")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    texts = build_texts(args)
    context = ObservedContext.assuming_common_defaults() if args.assume_defaults else ObservedContext()
    output = []

    if args.real:
        corpus = find_data(args.corpus)
        decisions = [d for games in load_corpus(corpus).values() for d in games if d.decision_id.endswith(args.real)]
        if len(decisions) != 1:
            print(f"decision suffix {args.real!r} matched {len(decisions)} decisions", file=sys.stderr)
            return 2
        decision = decisions[0]
        actions = [a for a in decision.legal_actions
                   if not args.only_card or a.get("card_id") == args.only_card or a["type"] == "END_TURN"]
        # identical menu rows (two copies of one card in hand) forecast identically; show each once
        unique, seen = [], set()
        for action in actions:
            key = json.dumps({k: v for k, v in action.items() if k != "hand_index"}, sort_keys=True)
            if key not in seen:
                seen.add(key)
                unique.append(action)
        output.append(show(f"real decision ...{decision.decision_id[-14:]} (turn {decision.state.turn_number})",
                           decision.state, unique, texts, context, args.json, args.events))
    else:
        chosen = [demo.hold_them_off()] if args.scenario == "hold-them-off" else []
        if args.scenario in ("sequencing", "all"):
            chosen = ([demo.hold_them_off()] if args.scenario == "all" else []) + demo.sequencing()
        demo_texts = demo.demo_texts(texts)
        # synthetic positions are fully specified: no Ruby Sanctum, and hand cards are the base cards
        scenario_context = ObservedContext(healing_does_damage=False, hand_keywords_match_card=True,
                                           trust_spell_damage=True, spell_healing_doubled=False)
        for scenario in chosen:
            output.append(show(scenario.title, scenario.state, scenario.actions, demo_texts,
                               context if args.assume_defaults else scenario_context, args.json,
                               args.events or scenario.name != "hold-them-off"))
    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
