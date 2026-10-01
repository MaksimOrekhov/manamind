"""Build a rules-coverage matrix for the selected current Standard deck pool."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POOL = ROOT / "data" / "samples" / "standard_meta_deck_pool_20260928.json"
DEFAULT_CATALOG = ROOT / "data" / "cards" / "standard_current_enUS.json"
DEFAULT_BANS = ROOT / "data" / "cards" / "format_bans_20260929.json"
DEFAULT_SOURCES = ROOT / "vendor" / "RosettaStone" / "Sources" / "Rosetta" / "PlayMode" / "CardSets"
DEFAULT_OUTPUT = ROOT / "reports" / "standard_meta_coverage_20260928.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def audit(pool_path: Path, catalog_path: Path, source_dir: Path,
          bans_path: Path = DEFAULT_BANS) -> dict:
    pool = load_json(pool_path)
    catalog_data = load_json(catalog_path)
    catalog = {card["id"]: card for card in catalog_data["cards"]}
    bans = load_json(bans_path)
    standard_banned_ids = set(bans.get("format_bans", {}).get("STANDARD", []))
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(source_dir.glob("*CardsGen.cpp"))
    )
    direct_registered = set(re.findall(r'cards\.emplace\(\s*"([A-Za-z0-9_]+)"', source_text))
    generated_routes: dict[str, str] = {}
    for manifest_name, route in (
        ("core_aliases.generated.json", "generated_core_alias"),
        ("effect_composition.generated.json", "generated_effect_composition"),
    ):
        manifest_path = ROOT / "integrations" / "rosettastone" / "card_rules" / manifest_name
        if manifest_path.exists():
            for item in load_json(manifest_path).get("cards", []):
                generated_routes[item["card_id"]] = route
    registered = direct_registered | generated_routes.keys()

    usage: dict[str, list[str]] = defaultdict(list)
    decks = []
    for deck in pool["decks"]:
        ids = set(deck["cards"])
        invalid = [
            card_id for card_id in ids
            if card_id not in catalog or not catalog[card_id].get("collectible")
        ]
        banned = sorted(set(deck["cards"]) & standard_banned_ids)
        decks.append({
            "name": deck["name"],
            "player_class": deck["player_class"],
            "source_name": deck.get("source_name"),
            "source_url": deck.get("source_url"),
            "published": deck.get("published"),
            "source_stats": deck.get("source_stats"),
            "card_count": len(deck["cards"]),
            "unique_card_count": len(ids),
            "invalid_or_noncollectible_ids": sorted(invalid),
            "standard_banned_ids": banned,
        })
        for card_id in ids:
            usage[card_id].append(deck["name"])

    cards = []
    for card_id, deck_names in sorted(usage.items()):
        card = catalog.get(card_id)
        if card is None:
            cards.append({
                "card_id": card_id, "name": "UNKNOWN", "decks": sorted(deck_names),
                "rules_registered": False, "status": "missing_metadata",
            })
            continue
        has_text = bool(card.get("text", "").strip())
        rules_registered = card_id in registered
        registration_route = (
            generated_routes.get(card_id, "direct_carddef") if rules_registered
            else "textless_metadata" if not has_text
            else "missing"
        )
        cards.append({
            "card_id": card_id,
            "name": card["name"],
            "type": card.get("type"),
            "set": card.get("set"),
            "mechanics": card.get("mechanics", []),
            "text": card.get("text", ""),
            "decks": sorted(deck_names),
            "rules_registered": rules_registered,
            "registration_route": registration_route,
            "status": "registered" if rules_registered or not has_text else "missing_rules",
        })

    by_deck = {}
    for deck in pool["decks"]:
        unique_ids = set(deck["cards"])
        by_deck[deck["name"]] = {
            "class": deck["player_class"],
            "card_slots": len(deck["cards"]),
            "unique_cards": len(unique_ids),
            "rules_covered_unique_cards": sum(
                1 for card_id in unique_ids
                if card_id in catalog and (
                    not catalog[card_id].get("text", "").strip() or card_id in registered
                )
            ),
            "unsupported_card_ids": sorted(
                card_id for card_id in unique_ids
                if card_id in catalog and catalog[card_id].get("text", "").strip()
                and card_id not in registered
            ),
        }

    mechanic_decks: dict[str, set[str]] = defaultdict(set)
    missing_mechanic_counts: Counter[str] = Counter()
    for row in cards:
        for mechanic in row.get("mechanics", []):
            mechanic_decks[mechanic].update(row["decks"])
            if row["status"] == "missing_rules":
                missing_mechanic_counts[mechanic] += 1

    return {
        "as_of": pool.get("catalog_valid_as_of"),
        "format": pool.get("format", "STANDARD"),
        "deck_pool_path": str(pool_path),
        "standard_ban_gate": {
            "status": "PASS" if not any(deck["standard_banned_ids"] for deck in decks) else "FAIL",
            "snapshot_path": str(bans_path),
            "checked_at": bans.get("checked_at"),
            "source_url": bans.get("source_url"),
            "snapshot_sha256": hashlib.sha256(bans_path.read_bytes()).hexdigest(),
            "standard_banned_card_ids": sorted(standard_banned_ids),
            "violations": {
                deck["name"]: deck["standard_banned_ids"]
                for deck in decks if deck["standard_banned_ids"]
            },
        },
        "decks": decks,
        "deck_coverage": by_deck,
        "unique_card_count": len(usage),
        "registered_or_textless_unique_cards": sum(row["status"] == "registered" for row in cards),
        "missing_rules_unique_cards": sum(row["status"] == "missing_rules" for row in cards),
        "cards": cards,
        "mechanics": [
            {
                "mechanic": mechanic,
                "decks": sorted(mechanic_decks[mechanic]),
                "unsupported_card_count": missing_mechanic_counts[mechanic],
            }
            for mechanic in sorted(mechanic_decks)
        ],
        "known_limitations": [
            "RosettaStone does not enforce the current ban list at runtime; the audit checks the dated external snapshot in data/cards/format_bans_20260929.json.",
            "A matching CardDef is an implementation inventory signal, not proof of scenario correctness.",
            "Unsupported card choices and Discover windows cannot be treated as completed games.",
            "The deck matrix does not audit the effects of cards offered by random generation or Discover outside this five-deck pool.",
            "Registration route reads the direct source scan and the two generated manifests; it is not a correctness or training-eligibility result.",
        ],
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Матрица покрытия актуальных колод Standard",
        "",
        f"Срез каталога: **{report['as_of']}**. Колоды взяты из сохранённых конфигураций и списков высокого ранга.",
        f"Всего: **{len(report['decks'])} колод**, **{sum(deck['card_count'] for deck in report['decks'])} слотов**, **{report['unique_card_count']} уникальных карт**.",
        f"Правила зарегистрированы для **{report['registered_or_textless_unique_cards']}** карт; **{report['missing_rules_unique_cards']}** текстовых карт требуют реализации.",
        f"Standard ban gate: **{report['standard_ban_gate']['status']}** (снимок от {report['standard_ban_gate']['checked_at']}; нарушений: {sum(map(len, report['standard_ban_gate']['violations'].values()))}).",
        "",
        "## Колоды",
        "",
        "| Архетип | Класс | Источник | Слоты | Уникальные ID покрыты правилами | Ожидают поддержки |",
        "|---|---|---|---:|---:|---:|",
    ]
    for deck in report["decks"]:
        coverage = report["deck_coverage"][deck["name"]]
        source = f"[{deck['source_name']}]({deck['source_url']})" if deck.get("source_url") else "ранее проверенная конфигурация"
        stats = deck.get("source_stats")
        if stats:
            source += f" (n={stats['reported_games']}, {stats['reported_win_rate_percent']:.2f}%)"
        waiting = len(coverage["unsupported_card_ids"])
        lines.append(
            f"| {deck['name']} | {deck['player_class']} | {source} | {deck['card_count']} | "
            f"{coverage['rules_covered_unique_cards']}/{coverage['unique_cards']} | {waiting} |"
        )
    lines += [
        "",
        "## Покрытие механик",
        "",
        "| Механика из каталога | Колоды | Неподдержанные карты |",
        "|---|---|---:|",
    ]
    for row in report["mechanics"]:
        lines.append(
            f"| {row['mechanic']} | {', '.join(row['decks'])} | {row['unsupported_card_count']} |"
        )
    lines += [
        "",
        "## Очередь групп реализации",
        "",
        "1. **Готовый Warlock-пул:** обе опубликованные колоды прошли прежний аудит правил и smoke-партии; оставить как опорную группу.",
        "2. **Warrior — драконы, оружие и урон:** Battlecry/Discover с условием на дракона, временные и случайные эффекты, массовый урон, оружие, end-of-turn токены.",
        "3. **Druid — атаки героя и развитие стола:** временная мана, эффекты от атак героя, выбор/Discover и перенос карт колоды, усиление по потраченной мане, большие призывы.",
        "4. **Priest — исцеление и контроль:** Quest-награды, Holy/Shadow, Reborn/воскрешение, выбор целей, массовое уничтожение, лечение и добор.",
        "",
        "Группы следует проверять отдельными игровыми сценариями и затем проходить всем пулом. Обучение и итоговая оценка допустимы только после того, как каждая колода создаёт полноценные завершённые партии без неподдержанных окон выбора.",
        "",
        "## Ограничения допуска",
        "",
        "- Список MetaStats является срезом пользовательских высокоранговых списков на 2026-09-27, а не полным официальным tier-листом.",
        "- Две Warlock-колоды включены из ранее декодированных и проверенных конфигураций.",
        "- Список банов хранится отдельно от RosettaStone; перед обновлением пула обновить датированный снимок и повторить этот gate.",
        "- Наличие `CardDef` в исходниках — только инвентарный признак. Оно не заменяет проверку фактического эффекта.",
        "",
        "Подробные строки по каждой карте: `reports/standard_meta_coverage_20260928.json`.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--bans", type=Path, default=DEFAULT_BANS)
    parser.add_argument("--card-sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Machine-readable JSON coverage report")
    parser.add_argument("--markdown-output", type=Path,
                        help="Optional Markdown matrix path")
    args = parser.parse_args()
    report = audit(args.pool, args.catalog, args.card_sources, args.bans)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(
        f"{len(report['decks'])} decks; {report['unique_card_count']} unique cards; "
        f"{report['missing_rules_unique_cards']} missing rule registrations."
    )
    print(f"Wrote {args.output}")
    if args.markdown_output:
        print(f"Wrote {args.markdown_output}")


if __name__ == "__main__":
    main()
