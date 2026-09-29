"""Small dependency-free metrics for binary win-probability predictions."""

import numpy as np


def roc_auc(targets: np.ndarray, probabilities: np.ndarray) -> float | None:
    """Compute ROC AUC on decisive outcomes; draws (soft 0.5 labels) are excluded."""
    targets = np.asarray(targets, dtype=np.float64)
    probabilities = np.asarray(probabilities, dtype=np.float64)
    decisive = (targets == 0.0) | (targets == 1.0)
    targets = targets[decisive].astype(np.int64)
    probabilities = probabilities[decisive]
    positive_count = int(targets.sum())
    negative_count = len(targets) - positive_count
    if positive_count == 0 or negative_count == 0:
        return None

    order = np.argsort(probabilities, kind="mergesort")
    sorted_probabilities = probabilities[order]
    ranks = np.empty(len(targets), dtype=np.float64)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and sorted_probabilities[end] == sorted_probabilities[start]:
            end += 1
        average_rank = (start + 1 + end) / 2.0
        ranks[order[start:end]] = average_rank
        start = end

    positive_rank_sum = ranks[targets == 1].sum()
    return float(
        (positive_rank_sum - positive_count * (positive_count + 1) / 2)
        / (positive_count * negative_count)
    )


def binary_metrics(targets: np.ndarray, probabilities: np.ndarray) -> dict[str, float | None]:
    targets = np.asarray(targets, dtype=np.float64)
    probabilities = np.asarray(probabilities, dtype=np.float64)
    decisive = (targets == 0.0) | (targets == 1.0)
    predictions = probabilities[decisive] >= 0.5
    return {
        "accuracy": (
            float(np.mean(predictions == (targets[decisive] == 1.0)))
            if decisive.any() else None
        ),
        "brier": float(np.mean((probabilities - targets) ** 2)),
        "roc_auc": roc_auc(targets, probabilities),
    }
