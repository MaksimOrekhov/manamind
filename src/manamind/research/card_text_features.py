"""Conservative, catalog-scoped text features for offline experiments only.

No Hearthstone rules are inferred here. Ambiguous source syntax masks the complete
card text rather than being guessed or partially represented as a certain effect.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

FEATURE_SCHEMA_VERSION = 2
CONFIG = {"version": FEATURE_SCHEMA_VERSION,
          "token_pattern": (r"format_(?:bold|italic)_(?:start|end)|"
                           r"\$\{\d+\}|\$[a-z][a-z0-9]*|\$\d+|#\d+|"
                           r"\([+-]?\d+\)|[+-]?\d+(?:/[+-]?\d+)+|[+-]?\d+|"
                           r"[a-z][a-z0-9']*|[^\w\s]"),
          "ngram_range": [1, 2], "sublinear_tf": True, "smooth_idf": True,
          "format_markers": "neutral-boundaries-v1", "ambiguity_policy": "mask-whole-text-v1"}

_TAG = re.compile(r"<\s*(/?)\s*(b|i)\s*>", re.IGNORECASE)
_ANY_TAG = re.compile(r"<[^>]*>")
_UNRESOLVED_TAG = re.compile(r"<[^>]*>")
_BRACE_PLACEHOLDER = re.compile(r"\{\s*\d+\s*\}")
# One observed collector encoding places a literal variant index after an italic
# segment (e.g. </i>1Draw); flag only that documented ambiguous layout pattern.
_VARIANT_ONE_SEPARATOR = re.compile(r"</i>\s*1(?=[A-Z])", re.IGNORECASE)
_TOKEN = re.compile(CONFIG["token_pattern"], re.IGNORECASE)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize_rules_text(value: object) -> dict:
    """Conservatively normalize only known layout and bold/italic markup.

    The normalized string is diagnostic when warnings exist; `text_usable` is the
    sole permission to emit vector features. Values/placeholders are never filled.
    """
    text_present = isinstance(value, str) and bool(value.strip())
    if not text_present:
        return {"normalized_text": None, "text_present": False, "text_usable": False,
                "normalization_warnings": ["TEXT_MISSING"]}

    text = value
    warnings: list[str] = []
    # Only the documented leading display/layout marker is removed.
    text = re.sub(r"^\s*\[x\]\s*", "", text, count=1, flags=re.IGNORECASE)
    if "[x]" in text:
        warnings.append("UNRESOLVED_LAYOUT_MARKER")
    if "@" in text or "|" in text or _VARIANT_ONE_SEPARATOR.search(text):
        warnings.append("UNRESOLVED_VARIANT_SEPARATOR")
    if _BRACE_PLACEHOLDER.search(text) or re.search(r"\$\{\s*\d+\s*\}", text):
        warnings.append("UNRESOLVED_PLACEHOLDER")

    output: list[str] = []
    stack: list[str] = []
    position = 0
    for match in _TAG.finditer(text):
        before = text[position:match.start()]
        if _UNRESOLVED_TAG.search(before) or "<" in before or ">" in before:
            warnings.append("UNSUPPORTED_MARKUP")
        output.append(before)
        closing, tag = match.group(1), match.group(2).lower()
        if closing:
            if not stack or stack[-1] != tag:
                warnings.append("UNBALANCED_FORMATTING_MARKUP")
            else:
                stack.pop()
            output.append(f" format_{'bold' if tag == 'b' else 'italic'}_end ")
        else:
            stack.append(tag)
            output.append(f" format_{'bold' if tag == 'b' else 'italic'}_start ")
        position = match.end()
    tail = text[position:]
    if _UNRESOLVED_TAG.search(tail) or "<" in tail or ">" in tail:
        warnings.append("UNSUPPORTED_MARKUP")
    output.append(tail)
    if stack:
        warnings.append("UNBALANCED_FORMATTING_MARKUP")

    # Newlines, tabs, and NBSPs are layout only; collapse without punctuation edits.
    text = "".join(output).replace("\u00a0", " ").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return {"normalized_text": text, "text_present": True,
            "text_usable": not warnings, "normalization_warnings": sorted(set(warnings))}


def _terms(text: str) -> list[str]:
    # Keep typed numeric forms distinct: $4, #4, (4), +2/+2 and plain 4.
    return [match.group(0).lower() for match in _TOKEN.finditer(text)]


class CardTextAdapter:
    """Pinned Standard catalog TF-IDF with explicit present/usable masks."""

    def __init__(self, catalog_path: Path):
        self.catalog_path = Path(catalog_path)
        self.catalog_sha256 = sha256_file(self.catalog_path)
        self.config_sha256 = hashlib.sha256(json.dumps(CONFIG, sort_keys=True,
                                                        separators=(",", ":")).encode()).hexdigest()
        payload = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        if payload.get("format") != "STANDARD" or not isinstance(payload.get("cards"), list):
            raise ValueError("Expected pinned STANDARD card catalog")
        self.cards = {card["id"]: card for card in payload["cards"] if isinstance(card.get("id"), str)}
        self.text_status = {card_id: normalize_rules_text(card.get("text"))
                            for card_id, card in self.cards.items()}
        # Compatibility aliases retained for the original MODEL-FIRST-3A report script.
        self.description_present = {card_id: status["text_present"]
                                    for card_id, status in self.text_status.items()}
        self.text_present = self.description_present
        self.text_usable = {card_id: status["text_usable"] for card_id, status in self.text_status.items()}
        self.normalization_warnings = {card_id: status["normalization_warnings"]
                                       for card_id, status in self.text_status.items()}

        document_frequency: Counter[str] = Counter()
        counts_by_card: dict[str, Counter[str]] = {}
        for card_id, status in self.text_status.items():
            terms = _terms(status["normalized_text"] or "") if status["text_usable"] else []
            bigrams = [f"{left}__{right}" for left, right in zip(terms, terms[1:])]
            counts = Counter([*terms, *bigrams])
            counts_by_card[card_id] = counts
            document_frequency.update(counts.keys())
        self.terms = sorted(document_frequency)
        self.term_index = {term: index for index, term in enumerate(self.terms)}
        n_docs = max(1, len(self.cards))
        self.idf = np.asarray([np.log((1 + n_docs) / (1 + document_frequency[t])) + 1
                               for t in self.terms], dtype=np.float32)
        self._counts = counts_by_card

    def cache_key(self) -> str:
        return hashlib.sha256(f"{self.catalog_sha256}:{self.config_sha256}".encode()).hexdigest()

    def features(self, card_id: str | None) -> tuple[np.ndarray, bool]:
        vector = np.zeros(len(self.terms), dtype=np.float32)
        if card_id is None or card_id not in self.cards or not self.text_usable[card_id]:
            return vector, False
        counts = self._counts[card_id]
        for term, count in counts.items():
            tf = 1 + np.log(count) if CONFIG["sublinear_tf"] else count
            vector[self.term_index[term]] = tf * self.idf[self.term_index[term]]
        norm = float(np.linalg.norm(vector))
        if norm:
            vector /= norm
        return vector, True

    def status_for(self, card_id: str | None) -> dict:
        if card_id is None or card_id not in self.cards:
            return {"text_present": False, "text_usable": False,
                    "text_mask": 0, "normalization_warnings": ["UNKNOWN_CARD_ID", "TEXT_MISSING"]}
        status = self.text_status[card_id]
        return {"text_present": status["text_present"], "text_usable": status["text_usable"],
                "text_mask": int(status["text_usable"]),
                "normalization_warnings": list(status["normalization_warnings"])}

    def cache(self, directory: Path) -> Path:
        """Write versioned sparse vectors; old v1 caches have different keys/names."""
        path = Path(directory) / f"card_text_tfidf_v{FEATURE_SCHEMA_VERSION}_{self.cache_key()}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        entries = {}
        for card_id in sorted(self.cards):
            vector, usable = self.features(card_id)
            entries[card_id] = {"features": ([[int(i), float(vector[i])]
                                               for i in np.flatnonzero(vector)] if usable else []),
                                **self.status_for(card_id)}
        payload = {"schema_version": FEATURE_SCHEMA_VERSION, "catalog_sha256": self.catalog_sha256,
                   "config_sha256": self.config_sha256, "terms": self.terms, "cards": entries}
        path.write_text(json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n", encoding="utf-8")
        return path

    def record(self, card_id: str, current_instance: dict | None = None) -> dict:
        card = self.cards.get(card_id, {})
        vector, _ = self.features(card_id)
        return {"card_id": card_id, "type": card.get("type"),
                "base": {key: card.get(key) for key in ("cost", "attack", "health")},
                "mechanics": list(card.get("mechanics", [])),
                **self.status_for(card_id),
                "text_features": vector, "current_instance": current_instance}
