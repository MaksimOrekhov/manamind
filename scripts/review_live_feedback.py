"""Review locally flagged LIVE recommendations after a match, replaying their exact context."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manamind.domain.serialization import game_state_from_dict
from manamind.live.instructions import instruction
from manamind.live.localization import CardNames
from manamind.live.prediction_journal import decision_id
from manamind.live.replay import replay_game, verify_replay
from manamind.live.snapshot import canonical_json
from manamind.cards.catalog import CardCatalog

DATA_ROOT = ROOT / "data/raw/live"
JOURNAL = DATA_ROOT / "prediction_journal.jsonl"
FEEDBACK = DATA_ROOT / "decision_feedback.jsonl"
CARDS = ROOT / "data/cards/standard_current_enUS.json"
NAMES = ROOT / "data/localization/card_names_253932.json"


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Некорректная запись {path.name}:{line_no}") from error
        if not isinstance(row, dict):
            raise ValueError(f"Некорректный формат {path.name}:{line_no}")
        rows.append(row)
    return rows


def load_contexts(feedback_rows: list[dict], prediction_rows: list[dict], recordings_root: Path,
                  catalog: CardCatalog) -> dict[str, tuple[dict, dict]]:
    flags = {row.get("decision_id"): row for row in feedback_rows
             if row.get("event") == "SUSPECTED_RECOMMENDATION"}
    recommendations = {row.get("decision_id"): row for row in prediction_rows
                       if row.get("event") == "RECOMMENDATION"}
    wanted = set(flags)
    if not wanted:
        return {}
    latest_assessment = {row.get("decision_id") for row in feedback_rows if row.get("event") == "ASSESSMENT"}
    wanted -= latest_assessment
    if not wanted:
        return {}
    records: dict[str, Path] = {}
    for meta_path in recordings_root.rglob("meta.json"):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        game_key = meta.get("game_key")
        if isinstance(game_key, str):
            records[game_key] = meta_path.parent
    by_game: dict[str, set[str]] = {}
    for key in wanted:
        flag = flags[key]
        match_id = flag.get("match_id")
        if match_id not in records:
            raise ValueError(f"Не найдена локальная запись матча для решения {key}")
        by_game.setdefault(match_id, set()).add(key)
    result = {}
    for match_id, decision_ids in by_game.items():
        directory = records[match_id]
        identical, _, _ = verify_replay(directory, catalog)
        if not identical:
            raise ValueError("Replay не совпал с записанными снимками; разбор остановлен")
        snapshots = replay_game(directory, catalog)
        matched = {decision_id(snap): snap for snap in snapshots}
        for key in decision_ids:
            flag, rec, snap = flags[key], recommendations.get(key), matched.get(key)
            if rec is None or snap is None:
                raise ValueError(f"Не хватает исходной рекомендации или replay-снимка для {key}")
            if (flag.get("schema") != "manamind.live_feedback/1" or flag.get("assessment") != "UNASSESSED"
                    or flag.get("match_id") != match_id or flag.get("state_hash") != snap.state_hash
                    or rec.get("state_hash") != snap.state_hash or rec.get("checkpoint_sha256") != flag.get("checkpoint_sha256")
                    or rec.get("top3") != flag.get("top3")):
                raise ValueError(f"Проверка связи или digest не пройдена для {key}")
            if (not isinstance(flag.get("legal_menu"), list) or not flag["legal_menu"]
                    or not isinstance(snap.state, dict)):
                raise ValueError(f"Нет легального меню для {key}")
            state = game_state_from_dict(snap.state)
            if state.opponent_known_cards or state.opponent.known_secrets or state.self_player.known_secrets:
                raise ValueError("Snapshot не прошёл границу видимой информации")
            menu = flag["legal_menu"]
            indices = set()
            for item in menu:
                action = item.get("action")
                digest = hashlib.sha256(canonical_json(action).encode("utf-8")).hexdigest()
                if (type(item.get("menu_index")) is not int or item["menu_index"] < 0
                        or item["menu_index"] in indices or item.get("action_sha256") != digest):
                    raise ValueError(f"Некорректный digest legal menu для {key}")
                indices.add(item["menu_index"])
            if any(not any(item["action"] == ranked["action"] and item["policy_rank"] == ranked["rank"]
                           for item in menu) for ranked in flag["top3"]):
                raise ValueError(f"Top-3 не совпадает с полным меню для {key}")
            result[key] = (flag, {"snapshot": snap.to_dict(), "recording": directory.as_posix(),
                                  "recommendation": rec})
    return result


def describe_state(state: dict, names: CardNames) -> list[str]:
    lines = []
    lines.append(f"Ход {state['turn_number']} · доступная мана {state['self_player']['available_mana']}/{state['self_player']['max_mana']}")
    for key, label in (("opponent", "Противник"), ("self_player", "Вы")):
        player = state[key]
        armor = f" + {player['armor']} брони" if player.get("armor") else ""
        hero_attack = f" · атака героя {player['hero_attack']}" if player.get("hero_attack") else ""
        lines.append(f"\n{label}: {player['hero_health']} здоровья{armor}{hero_attack}")
        weapon = player.get("weapon")
        if weapon:
            lines.append(f"  Оружие: {names.get(weapon.get('card_id'))} · атака {weapon.get('current_attack')} · прочность {weapon.get('current_durability')}")
        for minion in player.get("board", []):
            card = minion["card"]
            mechanics = [key for key in ("taunt", "divine_shield", "stealth", "frozen", "poisonous", "lifesteal", "windfury", "reborn", "dormant") if minion.get(key)]
            ability = names.text(card.get("card_id"))
            text = f" · {ability}" if ability else ""
            keywords = f" · {', '.join(mechanics)}" if mechanics else ""
            lines.append(f"  #{minion['board_position']} {names.get(card.get('card_id'))} {minion['current_attack']}/{minion['current_health']}{keywords}{text}")
        for location in player.get("locations", []):
            card = location["card"]
            lines.append(f"  Локация #{location['board_position']}: {names.get(card.get('card_id'))} · прочность {location['current_health']}")
    lines.append("\nВаша рука:")
    for index, card in enumerate(state.get("self_hand", []), 1):
        cost = card.get("current_cost") if card.get("current_cost") is not None else card.get("cost")
        text = names.text(card.get("card_id"))
        lines.append(f"  {index}. {names.get(card.get('card_id'))} · стоимость {cost}" + (f" · {text}" if text else ""))
    known = len(state.get("self_hand", []))
    total = state["self_player"]["hand_size"]
    if known < total:
        lines.append(f"  Ещё не раскрыто карт в руке: {total - known}")
    return lines


def render_case(flag: dict, context: dict, names: CardNames) -> None:
    snapshot = context["snapshot"]
    state = snapshot["state"]
    print("\n" + "=" * 78)
    print(f"СОМНИТЕЛЬНАЯ РЕКОМЕНДАЦИЯ · ход {snapshot['turn']} · решение {flag['decision_id'][-12:]}")
    print(f"Checkpoint SHA-256: {flag['checkpoint_sha256']}")
    print("Снимок восстановлен из replay; исходный state hash проверен.")
    print("\n".join(describe_state(state, names)))
    print("\nTop-3 Policy:")
    for item in flag["top3"]:
        view = instruction(item["action"], state, names)
        print(f"  #{item['rank']}: {view['verb']} {view['source']} {view['target']} {view['placement']}".strip())
    print("\nПолное легальное меню (номер меню · позиция Policy):")
    for item in sorted(flag["legal_menu"], key=lambda x: x["menu_index"]):
        view = instruction(item["action"], state, names)
        label = " · ".join(part for part in (view["verb"], view["source"], view["target"], view["placement"]) if part)
        print(f"  {item['menu_index'] + 1:>2}. [Policy #{item['policy_rank']}] {label}")


def append_assessment(path: Path, flag: dict, assessment: str, *, preferred: dict | None = None,
                      reason: str = "", mechanical_status: str | None = None) -> None:
    row = {"schema": "manamind.live_feedback/1", "event": "ASSESSMENT",
           "match_id": flag["match_id"], "decision_id": flag["decision_id"],
           "state_hash": flag["state_hash"], "checkpoint_sha256": flag["checkpoint_sha256"],
           "assessment": assessment, "assessed_at_utc": datetime.now(timezone.utc).isoformat(),
           "reason": reason}
    if preferred is not None:
        row["preferred_action"] = {"menu_index": preferred["menu_index"],
                                   "action_sha256": preferred["action_sha256"]}
    if mechanical_status:
        row["mechanical_review_status"] = mechanical_status
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()


def review(contexts: dict, feedback_path: Path, names: CardNames, input_fn=input) -> None:
    for decision, (flag, context) in contexts.items():
        render_case(flag, context, names)
        print("\n1 — оставить только сомнение (без обучающей метки)")
        print("2 — экспертно предпочесть ход из меню")
        print("3 — сообщить о механической ошибке и описать правило (потребует независимой проверки)")
        print("4 — только объяснение, без предпочтения")
        print("Enter — пока пропустить")
        choice = input_fn("Оценка: ").strip()
        if not choice:
            continue
        if choice == "1":
            append_assessment(feedback_path, flag, "UNRESOLVED_DOUBT")
            continue
        if choice not in {"2", "3", "4"}:
            print("Неизвестный ответ; запись оставлена для следующего раза.")
            continue
        preferred = None
        if choice in {"2", "3"}:
            raw = input_fn("Номер предпочтительного действия из меню: ").strip()
            try:
                menu_number = int(raw)
                preferred = next(item for item in flag["legal_menu"] if item["menu_index"] == menu_number - 1)
            except (ValueError, StopIteration):
                print("Действие не найдено; запись оставлена для следующего раза.")
                continue
        reason = input_fn("Почему? (кратко): ").strip()
        if choice in {"3", "4"} and not reason:
            print("Нужно указать правило или пояснение; запись оставлена для следующего раза.")
            continue
        assessment = {"2": "EXPERT_PREFERENCE", "3": "MECHANICAL_ERROR_CLAIM", "4": "EXPLANATION_ONLY"}[choice]
        append_assessment(feedback_path, flag, assessment, preferred=preferred, reason=reason,
                          mechanical_status="NEEDS_INDEPENDENT_VERIFICATION" if choice == "3" else None)
        print(f"Оценка сохранена: {decision[-12:]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recordings-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--journal", type=Path, default=JOURNAL)
    parser.add_argument("--feedback", type=Path, default=FEEDBACK)
    parser.add_argument("--cards", type=Path, default=CARDS)
    parser.add_argument("--localization", type=Path, default=NAMES)
    parser.add_argument("--list-only", action="store_true", help="Show pending case count without prompting")
    args = parser.parse_args()
    try:
        feedback_rows = read_rows(args.feedback)
        prediction_rows = read_rows(args.journal)
        catalog = CardCatalog.from_json(args.cards)
        contexts = load_contexts(feedback_rows, prediction_rows, args.recordings_root, catalog)
    except Exception as error:
        print(json.dumps({"result": "FAILED", "reason": type(error).__name__}, ensure_ascii=False))
        return 1
    if not contexts:
        print("Нет неразобранных отметок.")
        return 0
    if args.list_only:
        print(f"Ожидают разбора: {len(contexts)}")
        return 0
    names = CardNames.load(args.localization, args.cards)
    review(contexts, args.feedback, names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
