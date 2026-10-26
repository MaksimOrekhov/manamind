"""Score an already-computed forecast with existing outcome.verify primitives.

The production score_pair computes its forecast internally. This small offline
adapter preserves its comparison rules, accepts the forecast before truth is
read, and omits only the optional post-hoc explanation heuristics. Tests compare
its ledgers against production score_pair; no alternate alignment/physics.
"""
from manamind.outcome.verify import (
    PairResult, _forecast_mapping, _list_claims, _stale_paths, family_of, observe,
)


def score_precomputed(current, following, forecast):
    out = PairResult(current.decision_id, forecast.label, family_of(current.action), forecast.status, forecast.tier,
                     unsupported_reason=forecast.unsupported_reason)
    if forecast._candidate is None:
        return out
    before, predicted, actual = observe(current.state), observe(forecast._candidate), observe(following.state)
    stale = _stale_paths(current.state, forecast)
    maps = _forecast_mapping(current.state, forecast)
    for path in sorted(before):
        old, new, seen = before[path], predicted[path], actual[path]
        if isinstance(old, list):
            _list_claims(path, old, new, seen, maps[path], out, stale)
        elif path in stale or old is None or (seen is None and old is not None):
            continue
        elif new != old:
            (out.confirmed.__setitem__(path, new) if new == seen
             else out.contradicted.__setitem__(path, (new, seen)))
        elif seen != old:
            out.missed[path] = (old, seen)
    out.unknown_kinds = tuple(sorted({u.kind.value for u in forecast.unknowns}))
    out.unknown_tags = tuple(sorted({u.tag for u in forecast.unknowns}))
    out.own_effect_known = forecast.own_effect_known
    out.alters_listed = any(u.alters_listed for u in forecast.unknowns)
    return out
