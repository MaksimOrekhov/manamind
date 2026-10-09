"""Deterministic local TF-IDF card text adapter for bounded experiments.

This module deliberately does not modify CardFeatures, StateEncoder or checkpoints.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

CONFIG = {"version": 1, "token_pattern": r"[a-z][a-z0-9']+", "ngram_range": [1, 2],
          "sublinear_tf": True, "smooth_idf": True, "strip_markup": True}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rules_text(card: dict) -> str:
    # The pinned catalog's `text` is rules text; never fall back to `flavor`.
    value = card.get("text")
    if not isinstance(value, str):
        return ""
    value = re.sub(r"<[^>]*>", " ", value)
    value = html.unescape(value).replace("[x]", " ")
    return " ".join(value.split()).lower()


class CardTextAdapter:
    """Catalog-scoped word TF-IDF, with missing descriptions represented as empty rows."""

    def __init__(self, catalog_path: Path):
        self.catalog_path = Path(catalog_path)
        self.catalog_sha256 = sha256_file(self.catalog_path)
        self.config_sha256 = hashlib.sha256(json.dumps(CONFIG, sort_keys=True,
                                                        separators=(",", ":")).encode()).hexdigest()
        payload = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        if payload.get("format") != "STANDARD" or not isinstance(payload.get("cards"), list):
            raise ValueError("Expected pinned STANDARD card catalog")
        self.cards = {card["id"]: card for card in payload["cards"] if isinstance(card.get("id"), str)}
        docs = {card_id: _rules_text(card) for card_id, card in self.cards.items()}
        self.description_present = {card_id: bool(text) for card_id, text in docs.items()}
        document_frequency: Counter[str] = Counter()
        counts_by_card: dict[str, Counter[str]] = {}
        for card_id, text in docs.items():
            tokens = re.findall(CONFIG["token_pattern"], text)
            terms = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
            counts = Counter(terms)
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
        if card_id is None or card_id not in self.cards or not self.description_present[card_id]:
            return vector, False
        counts = self._counts[card_id]
        for term, count in counts.items():
            tf = 1 + np.log(count) if CONFIG["sublinear_tf"] else count
            vector[self.term_index[term]] = tf * self.idf[self.term_index[term]]
        norm = float(np.linalg.norm(vector))
        if norm:
            vector /= norm
        return vector, True

    def cache(self, directory: Path) -> Path:
        """Write a compact sparse cache whose filename binds catalog and config identities."""
        path = Path(directory) / f"card_text_tfidf_{self.cache_key()}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        entries = {}
        for card_id in sorted(self.cards):
            vector, present = self.features(card_id)
            entries[card_id] = [[int(i), float(vector[i])] for i in np.flatnonzero(vector)] if present else []
        payload = {"schema_version": 1, "catalog_sha256": self.catalog_sha256,
                   "config_sha256": self.config_sha256, "terms": self.terms, "cards": entries}
        path.write_text(json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n", encoding="utf-8")
        return path

    def record(self, card_id: str, current_instance: dict | None = None) -> dict:
        card = self.cards.get(card_id, {})
        vector, present = self.features(card_id)
        return {"card_id": card_id, "type": card.get("type"),
                "base": {key: card.get(key) for key in ("cost", "attack", "health")},
                "mechanics": list(card.get("mechanics", [])), "rules_text_present": present,
                "text_features": vector, "current_instance": current_instance}
