# ManaMind overlay UI (UI-0)

UI-0 is the first visual prototype of the ManaMind recommendation overlay: a compact, dark, semi-transparent panel (about 360–440 px wide) that lists the top recommended actions and shows how each one was evaluated.

**All data is mocked.** The app runs entirely from deterministic fixtures in `src/overlay/fixtures.ts`. There is no Hearthstone, HDT, `Power.log`, Python bridge, Tauri shell, model inference or ManaEngine integration here, on purpose.

## Run

Requires Node 20+ and pnpm. This is a standalone app, not a workspace member; run everything from this directory.

```bash
pnpm install
pnpm dev          # browser preview; a dev-only "Mock state" switcher sits above the panel
pnpm typecheck
pnpm test
pnpm build
```

The fixture switcher is rendered only when `import.meta.env.DEV` is true, so it is not part of the production build or the overlay itself.

## Evaluation sources

| Badge | Meaning |
| --- | --- |
| `● EXACT` | Exactly simulated under the current runtime contract. |
| `◐ INFERRED` | Simulation completed, but with evidence debt. This is not rules verification. |
| `◆ NEURAL` | Direct action-value estimate, with no exact child state. Never presented as exact. |
| `✕ N/A` | No usable recommendation. No score is shown (`—`). |

Each badge differs by icon, text and border style, not just color. Internal terms such as `REVIEWED_INFERRED` are not shown as player-facing labels. Details appear in the expandable row (the row is a button, so it works with Enter and Space).

## Localization (RU / EN)

Russian is the default; English is available through the compact `RU | EN` switch in the header. The choice is stored in `localStorage` (`manamind.overlay.locale`) and `<html lang>` follows it. No i18n library is used: `src/i18n/messages.ts` holds typed keys for both languages and `src/i18n/index.ts` exposes `locale`, `setLocale()` and `t()`.

Two kinds of text are handled differently:

- **Overlay-owned strings** (statuses, "no active match", "analyzing", source badges and tooltips, counters, "Turn", latency units, accessibility labels) are localized by the UI. The runtime DTO carries no locale fields for them; idle, analyzing and waiting texts are derived from `status` / `activePlayer`.
- **Runtime-provided content** (card and action labels, details, evidence notes, an engine error `message`) is treated as display-ready and already localized by the runtime or client metadata. The UI renders it as-is. There is deliberately no Hearthstone card-name translator here. The localized mock action names in `src/overlay/fixtures.ts` exist only to imitate that.

## DTO boundary

`src/overlay/types.ts` defines presentation DTOs (`OverlayState`, `Recommendation`, `EvaluationSource`). They are deliberately not bound to any Python class. Components only consume these types. The DTO has no locale field. Mapping from runtime output to the DTOs is a separate future layer and does not exist yet. Scores are win probability for SELF in `[0, 1]`; a missing score is rendered as `—` and is never invented.

## Future integration (not implemented)

```
Hearthstone / HDT / Power.log
        ↓
ManaMind runtime
        ↓
recommendation DTO
        ↓
overlay-ui
```

The transport between runtime and UI (local WebSocket, local HTTP, or Tauri command/event) is intentionally undecided. The seam is a single `OverlayState` value: replace the fixture selection in `src/App.vue` with a subscription that yields `OverlayState`. Always-on-top, borderless and click-through window behavior also belong to a later native-shell phase.

## Layout

- `src/overlay/` – DTO types, formatting helpers, mock fixtures
- `src/components/` – `OverlayPanel`, `OverlayHeader`, `RecommendationList`, `RecommendationItem`, `EvaluationBadge`, `OverlayFooter`, `StatusView`
- `tests/` – Vitest unit and component tests
