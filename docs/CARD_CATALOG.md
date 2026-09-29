# Current Standard card catalog

## Snapshot

The current snapshot is generated into data/cards/standard_current_enUS.json from the latest English collectible-card feed at HearthstoneJSON. The source response and resolved URL/build are recorded in the generated file. The full upstream snapshot is kept separately in data/cards/hearthstonejson_latest_enUS.json.

The format manifest is data/cards/standard_sets.json. As of 2026-09-26 it includes Core, the current Event Set, the three Year of the Raptor expansions, and the two released Year of the Scarab expansions. The October 2026 expansion is not included because it has not launched as of this snapshot date. The set IDs are based on Blizzard’s official Card Sets page and expansion launch information.

## Refresh

From the project root, run:

    .\.venv\Scripts\python.exe scripts\update_card_catalog.py

The updater fetches the latest collectible card JSON, validates IDs and configured set IDs, filters the Standard sets, and atomically replaces the generated snapshot. At a yearly rotation or expansion release, review and update standard_sets.json before running it. The updater intentionally fails if a configured set is missing from the source.

To build from an already downloaded HearthstoneJSON file without network access:

    .\.venv\Scripts\python.exe scripts\update_card_catalog.py --source-file .\data\cards\hearthstonejson_latest_enUS.json

## Use with training

When loading a labeled dataset, the training pipeline uses this current Standard catalog by default if the snapshot exists. Pass --cards to select a different catalog explicitly. Synthetic pipeline runs continue using the small sample catalog unless one is explicitly supplied.

The value network can encode these card IDs and the structured metadata represented by CardFeatures (cost, stats, type, class, race, mechanics). The model does not read card rules text. Adding an ID to the catalog gives it a vocabulary entry; its embedding still needs training examples before it has learned anything about that card. Each checkpoint stores its catalog and vocabulary, so a model trained with a changed catalog is a new checkpoint version.

This catalog update does not add card mechanics to RosettaStone and does not create labeled ranked-game examples. Do not train a strategic model on the synthetic sanity-check dataset or on the earlier 2022-pool baseline rollout. The simulator’s legal-card pool and implemented effects must be audited separately before simulator outcomes are treated as labels.

## Sources

- HearthstoneJSON latest collectible cards: https://api.hearthstonejson.com/v1/latest/enUS/cards.collectible.json
- Blizzard Card Sets: https://hearthstone.blizzard.com/en-us/expansions-adventures
- The generated metadata is community-converted from Hearthstone game data; HearthstoneJSON notes that the card data is copyrighted by Blizzard.
