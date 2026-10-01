# Core alias pilot — Void Shard — 2026-10-01

`CORE_SW_442` uses linked DBF metadata and exactly matching normalized rules text from `SW_442`; the legacy CardDef and its fixed rule dependencies are available. The allowlisted generator copies that existing CardDef and preserves `COUNT_AS_COPY_DBF` provenance.

## Verification

- Alias generator emitted 56 aliases; 11 still have unresolved dynamic pools.
- Native CardDef parity: 7 cases / 708 assertions passed across all aliases.
- Bridge smoke passed for 35 Core alias IDs, including `CORE_SW_442` Standard deck validation, session creation, opening hand, and legal actions.
- Standard registry tests: 10 passed.

## Limits

The new entry is `IMPLEMENTED_UNVERIFIED`: alias parity compares it with its base definition, so it does not independently prove Void Shard's effect. Registry snapshot: 1,185 roots; 167 direct + 78 generated registrations; 152 known non-root nodes; 310 heuristic pool signals; 937 text-bearing roots without detected registration; zero complete root closures and zero training-eligible roots.
