# Colossal rules review

Date: 2026-10-05. Scope: bounded intrinsic Colossal +2 needed by Vulcanos.

## Rules established

- Blizzard says appendages are part of the Colossal and appear whenever its body is summoned, including when not played from hand ([Sunken City launch notes](https://hearthstone.blizzard.com/en-us/news/23784370/voyage-to-the-sunken-city-is-now-live)).
- Blizzard's positioning guide says minion-generated summons appear to the right of their source and multiple summons fill adjacent spaces ([Board Positioning](https://hearthstone.blizzard.com/en-gb/news/21295165/non-printable)).
- Blizzard's CATACLYSM overview describes appendages as separate cards/spaces that expand the Colossal across the board ([CATACLYSM announcement](https://hearthstone.blizzard.com/en-us/news/24245219)).
- Current community-maintained Hearthstone rules references list each appendage as a separate entity, describe Colossal appendages resolving before the body's other effects, and document Xhilag's outer-to-inner order. These are supporting rules references, not official primary evidence ([Colossal](https://hearthstone.wiki.gg/wiki/Colossal), [Xhilag](https://hearthstone.wiki.gg/wiki/Xhilag_of_the_Abyss)).
- A Blizzard forum replay discussion reports that Xhilag can summon only the appendages for which board slots remain. That is a community replay report, not a normative Blizzard ruling ([forum report](https://us.forums.blizzard.com/en/hearthstone/t/help-me-understand-this-interaction-dh-5-appendages/85810)).

Pinned metadata identifies `CATA_488t` and `CATA_488t2` as the two 1/5 Elemental Plumes. Their left/right identity is supported by current card-reference pages but is not explicitly stated by Blizzard.

## Admission boundary for this implementation

The intrinsic hook can be implemented with a typed finite ordered appendage list and ordinary `CardInstance` entities. Normal play and generic summon invoke the same creation helper. Each appendage receives a new entity and activation sequence, is summoned rather than played, and is inserted around the body in the reviewed order.

The engine will fail closed before mutation when there is not enough space for the body plus both appendages. This conservative boundary avoids guessing partial-capacity resolution. Boards with 0, 1, or 4 existing friendly minions can admit the complete 3-entity family; 5 or 6 existing minions fail closed for this card. The native matrix covers all requested counts 0, 1, 4, 5, and 6. The client likely resolves the partial case, but that behavior is outside admitted evidence.

Transform into a Colossal is not supported by this package: the generic transform path currently replaces an entity without a reviewed appendage insertion continuation. Transforming Vulcanos out leaves already-created Plumes as independent entities. Copying a Colossal source is fail-closed through the existing bounded instance-copy admission. No linkage handle is introduced. These boundaries do not change observation schema.

## Event order and status

Appendages are created as part of the summon operation before the source's end-turn reaction can be scheduled. Root placement is retained; the two appendages are inserted immediately around the root in left then right identity order. The family's normal activation sequence controls subsequent end-turn order. The rules evidence supports this bounded insertion contract enough for a prototype; exact partial-capacity, transform-to, and copy-of-source behavior remain unsupported.
