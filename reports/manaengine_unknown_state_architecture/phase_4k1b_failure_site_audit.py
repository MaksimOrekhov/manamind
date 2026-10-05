"""Reproducible native failure-site scan for the Phase 4K.1b audit (read-only).

The audit report and the inventory JSON are only as good as their site list, so this
helper enumerates every failure site mechanically instead of trusting a hand count:

  scan                         print per-mechanism counts
  check [--inventory PATH]     fail unless every site matches exactly one inventory row,
                               row site counts agree and the audited source hashes match
  instrument OUT_DIR           write an instrumented SCRATCH copy of the native sources that
                               logs the first hit of every site (never edits the repository)
  hits HITFILE [HITFILE ...]   merge first-hit logs into per-row dynamic coverage

Sites are tokenised (strings, chars, comments skipped), so the minified one-line style of
the native sources cannot hide a throw. Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NATIVE = REPO / "experiments" / "manaengine"
SOURCES = ("engine.cpp", "damage_group.cpp", "pool_manifest.cpp", "python_bindings.cpp")
DEFAULT_INVENTORY = Path(__file__).with_name("PHASE_4K1B_NATIVE_FAILURE_INVENTORY.json")

_FUNC_DEFS = (
    re.compile(r"^(?:\[\[noreturn\]\]\s+)?(?:[\w:<>,&\*]+\s+)*?(?:GameSession|CardCatalog)::(~?\w+)\("),
    re.compile(r"^(?:const char\*|std::string|std::vector<std::string>|std::uint64_t|void|bool|py::dict|Action)\s+(\w+)\("),
)
_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')


@dataclass
class Site:
    file: str
    line: int
    function: str
    kind: str          # reject | catalog_reject_call | write_throw | write_soft | echo | catch | at_call | throw:<type>
    msg: str
    pos: int
    end: int
    edits: list = field(default_factory=list)  # typed edit specs used only by `instrument`

    @property
    def key(self) -> str:
        return f"{self.file}:{self.line}:{self.function}:{self.kind}:{self.msg[:40]}"


def _tokens(text: str):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            yield "lit", i, j + 1
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            i = text.find("*/", i) + 2
        elif c.isalpha() or c == "_":
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            yield "id", i, j
            i = j
        else:
            yield "op", i, i + 1
            i += 1


def _match(text, toks, k):
    depth = 0
    for j in range(k, len(toks)):
        if toks[j][0] == "op":
            ch = text[toks[j][1]]
            depth += ch in "([{"
            if ch in ")]}":
                depth -= 1
                if depth == 0:
                    return j
    raise ValueError("unbalanced brackets")


def _statement_end(text, toks, k):
    depth = 0
    for j in range(k, len(toks)):
        if toks[j][0] == "op":
            ch = text[toks[j][1]]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                if depth == 0:
                    return j
                depth -= 1
            elif ch == ";" and depth == 0:
                return j
    raise ValueError("statement without terminator")


def enumerate_sites(root: Path = NATIVE) -> list[Site]:
    sites: list[Site] = []
    for name in SOURCES:
        rel = f"src/{name}"
        text = (root / rel).read_text(encoding="utf-8")
        lines = text.splitlines()
        starts = [0]
        for line in lines:
            starts.append(starts[-1] + len(line) + 1)
        funcs, cur = [], "<file>"
        for line in lines:
            for rx in _FUNC_DEFS:
                m = rx.match(line)
                if m:
                    cur = m.group(1)
                    break
            funcs.append(cur)

        def line_of(pos: int) -> int:
            lo, hi = 0, len(starts) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                lo, hi = (mid, hi) if starts[mid] <= pos else (lo, mid - 1)
            return lo + 1

        toks = list(_tokens(text))
        found: list[Site] = []
        definition_lines = {i + 1 for i, line in enumerate(lines) if "void GameSession::reject_unsupported(std::string reason)" in line}

        def add(kind, pos, end, edits):
            ln = line_of(pos)
            literal = _LITERAL.search(text[pos:end])
            found.append(Site(rel, ln, funcs[ln - 1], kind, literal.group(1) if literal else "", pos, end, edits))

        for k, (tk, a, b) in enumerate(toks):
            word = text[a:b]
            ln = line_of(a)
            if ln in definition_lines:
                continue  # reject_unsupported's own first-wins store and rethrow are not failure sites
            nxt = toks[k + 1] if k + 1 < len(toks) else None
            call = nxt is not None and text[nxt[1]] == "("
            prev = text[toks[k - 1][1]] if k else ""
            if tk == "id" and word == "reject_unsupported" and call and prev != ":":
                close = _match(text, toks, k + 1)
                add("reject", a, toks[close][2], [("hit", a)])
            elif tk == "id" and word == "reject" and call and prev not in ".:" and rel.endswith("engine.cpp"):
                close = _match(text, toks, k + 1)
                add("catalog_reject_call", a, toks[close][2], [("hit", a)])
            elif tk == "id" and word == "throw" and not (nxt and text[nxt[1]] == ";"):
                end = _statement_end(text, toks, k + 1)
                expr = text[toks[k + 1][1]:toks[end][1]]
                type_name = re.match(r"\s*([\w:]+)", expr).group(1)
                kind = "throw_stored" if "(*state_.unsupported)" in expr else f"throw:{type_name}"
                add(kind, a, toks[end][1], [("wrap", toks[k + 1][1]), ("close", toks[end][1])])
            elif (tk == "id" and word == "state_" and k + 4 < len(toks) and text[toks[k + 1][1]] == "."
                  and text[toks[k + 2][1]:toks[k + 2][2]] == "unsupported" and text[toks[k + 3][1]] == "="
                  and text[toks[k + 4][1]] != "="):
                end = _statement_end(text, toks, k + 4)
                add("write", a, toks[end][1], [("wrap", toks[k + 4][1]), ("close", toks[end][1])])
            elif tk == "id" and word == "catch" and call:
                close = _match(text, toks, k + 1)
                brace = toks[close + 1]
                if text[brace[1]] == "{":
                    header = text[toks[k + 1][1]:toks[close][2]]
                    var = re.search(r"&\s*(\w+)\s*\)$", header)
                    what = var.group(1) if var and ("exception" in header or "Unsupported" in header) else None
                    add("catch", a, toks[close][2], [("catch_body", brace[2], what)])
            elif tk == "op" and text[a] == "." and k + 2 < len(toks) and text[toks[k + 1][1]:toks[k + 1][2]] == "at" and text[toks[k + 2][1]] == "(":
                add("at_call", a, toks[_match(text, toks, k + 2)][2], [])
        # A write immediately followed by `throw UnsupportedSimulationError(*state_.unsupported)` is one statement pair.
        merged, skip = [], set()
        for i, site in enumerate(found):
            if i in skip:
                continue
            if site.kind == "write":
                nxt_site = found[i + 1] if i + 1 < len(found) else None
                adjacent = nxt_site is not None and not text[site.end:nxt_site.pos].strip(" \t\r\n;")
                if adjacent and nxt_site.kind in ("throw_stored", "throw:UnsupportedSimulationError"):
                    site.kind = "write_throw"
                    site.edits += nxt_site.edits
                    site.end = nxt_site.end
                    skip.add(i + 1)
                else:
                    site.kind = "write_soft"
            elif site.kind == "throw_stored":
                site.kind = "echo"
            merged.append(site)
        sites.extend(merged)
    return sites


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counts(sites: list[Site]) -> dict:
    out: dict[str, int] = {}
    for s in sites:
        out[s.kind] = out.get(s.kind, 0) + 1
    return dict(sorted(out.items()))


def _selector_matches(sel: dict, s: Site) -> bool:
    if sel.get("file") and sel["file"] != s.file:
        return False
    if sel.get("function") and sel["function"] != s.function:
        return False
    if sel.get("kind") and sel["kind"] != s.kind:
        return False
    if sel.get("line") is not None and sel["line"] != s.line:
        return False
    if sel.get("msg") and not s.msg.startswith(sel["msg"]):
        return False
    if sel.get("msg_re") and not re.search(sel["msg_re"], s.msg):
        return False
    return True


def assign(sites: list[Site], rows: list[dict]) -> tuple[dict[str, list[Site]], list[Site], list[tuple[Site, list[str]]]]:
    by_row: dict[str, list[Site]] = {r["id"]: [] for r in rows}
    unmatched, ambiguous = [], []
    for s in sites:
        hits = [r["id"] for r in rows for sel in r.get("selectors", ()) if _selector_matches(sel, s)]
        hits = sorted(set(hits))
        if not hits:
            unmatched.append(s)
        elif len(hits) > 1:
            ambiguous.append((s, hits))
        else:
            by_row[hits[0]].append(s)
    return by_row, unmatched, ambiguous


def cmd_scan(_args) -> int:
    sites = enumerate_sites()
    print(json.dumps({"sites": len(sites), "by_kind": counts(sites)}, indent=1))
    per_file: dict[str, dict[str, int]] = {}
    for s in sites:
        per_file.setdefault(s.file, {}).setdefault(s.kind, 0)
        per_file[s.file][s.kind] += 1
    for file, c in sorted(per_file.items()):
        print(file, dict(sorted(c.items())))
    return 0


def cmd_check(args) -> int:
    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    sites = enumerate_sites()
    problems: list[str] = []
    for rel, digest in inventory["source_sha256"].items():
        if sha256(NATIVE / rel) != digest:
            problems.append(f"audited source changed: {rel} (inventory is stale; re-audit the delta)")
    native_rows = [r for r in inventory["rows"] if r.get("selectors")]
    by_row, unmatched, ambiguous = assign(sites, native_rows)
    for s in unmatched:
        problems.append(f"unclassified site: {s.key}")
    for s, rows in ambiguous:
        problems.append(f"site matches several rows {rows}: {s.key}")
    for row in native_rows:
        if len(by_row[row["id"]]) != row["site_count"]:
            problems.append(f"{row['id']}: site_count {row['site_count']} != matched {len(by_row[row['id']])}")
    if len(sites) != inventory["totals"]["native_sites"]:
        problems.append(f"native site total {len(sites)} != inventory {inventory['totals']['native_sites']}")
    if counts(sites) != inventory["totals"]["by_kind"]:
        problems.append("per-kind counts differ from inventory")
    for problem in problems:
        print("FAIL:", problem)
    print(f"{len(sites)} native sites, {len(native_rows)} native rows, {len(problems)} problems")
    return 1 if problems else 0


def cmd_instrument(args) -> int:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("include", "tests"):
        shutil.rmtree(out / name, ignore_errors=True)
        shutil.copytree(NATIVE / name, out / name)
    shutil.copy(NATIVE / "CMakeLists.txt", out / "CMakeLists.txt")
    (out / "src").mkdir(exist_ok=True)
    shutil.copy(NATIVE / "src" / "python_bindings.cpp", out / "src" / "python_bindings.cpp")
    (out / "site_trace.hpp").write_text(_TRACE_HEADER, encoding="utf-8")
    sites = enumerate_sites()
    for name in SOURCES:
        rel = f"src/{name}"
        text = (NATIVE / rel).read_text(encoding="utf-8")
        edits: list[tuple[int, str]] = []
        for sid, site in enumerate(sites):
            if site.file != rel:
                continue
            for spec in site.edits:
                if spec[0] == "hit":      # statement-level prefix: `hit(id), reject_unsupported(...)`
                    edits.append((spec[1], f"::manatrace::hit({sid}),"))
                elif spec[0] == "wrap":   # pass-through wrapper: MSVC rejects a comma expression inside `throw`
                    edits.append((spec[1], f"::manatrace::wrap({sid},"))
                elif spec[0] == "close":
                    edits.append((spec[1], ")"))
                elif spec[0] == "catch_body":
                    edits.append((spec[1], f"::manatrace::hit({sid},{spec[2]}.what());" if spec[2] else f"::manatrace::hit({sid});"))
        for offset, ins in sorted(edits, key=lambda e: e[0], reverse=True):
            text = text[:offset] + ins + text[offset:]
        (out / rel).write_text(text, encoding="utf-8")
    manifest = [{"id": i, "file": s.file, "line": s.line, "function": s.function, "kind": s.kind, "msg": s.msg[:120]}
                for i, s in enumerate(sites)]
    (out / "sites.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"instrumented {len(sites)} sites into {out}; build with CXXFLAGS including /FI{out / 'site_trace.hpp'} (MSVC) "
          "or -include (GCC/Clang), then run with MANA_SITE_HITS=<file>")
    return 0


def cmd_hits(args) -> int:
    manifest = json.loads((Path(args.sites)).read_text(encoding="utf-8"))
    seen: set[int] = set()
    for path in args.hitfiles:
        for row in Path(path).read_text(encoding="utf-8").splitlines():
            seen.add(int(row.split("\t", 1)[0]))
    print(f"{len(seen)} of {len(manifest)} instrumented sites fired")
    return 0


_TRACE_HEADER = r'''#pragma once
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>
#include <utility>
namespace manatrace {
inline int hit(int id, const char* msg = nullptr) {
  static std::set<std::string> seen;
  const char* path = std::getenv("MANA_SITE_HITS");
  if (!path) return 0;
  std::string key = std::to_string(id) + (msg ? std::string("\t") + msg : std::string());
  if (!seen.insert(key).second) return 0;
  if (std::FILE* f = std::fopen(path, "a")) { std::fprintf(f, "%s\n", key.c_str()); std::fclose(f); }
  return 0;
}
template <class T> inline T&& wrap(int id, T&& v) { hit(id); return std::forward<T>(v); }
}
'''


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan").set_defaults(fn=cmd_scan)
    p = sub.add_parser("check")
    p.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("instrument")
    p.add_argument("out_dir")
    p.set_defaults(fn=cmd_instrument)
    p = sub.add_parser("hits")
    p.add_argument("--sites", required=True)
    p.add_argument("hitfiles", nargs="+")
    p.set_defaults(fn=cmd_hits)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
