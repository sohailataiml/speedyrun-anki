#!/usr/bin/env python3
"""Trains the Performance model's logistic regression weights.

*** SYNTHETIC PLACEHOLDER DATA ***
There is no real held-back MCAT-style question bank in this repo yet (see
ARCHITECTURE.md §8, "Held-back sets" — not built). This script generates a
synthetic labeled dataset from a fixed seed instead of reading real exam
questions, purely to prove the train -> evaluate -> serialize -> Rust-apply
pipeline is wired correctly and rerunnable end to end.

The weights this produces must NEVER be presented to a real student as a
genuine Performance score. Once a real held-back question bank exists,
point `generate_synthetic_dataset` -> `load_real_dataset` and retrain; the
rest of the pipeline (split, train, evaluate, serialize) does not change.

Rerunnable: `python train_performance_model.py` with no arguments
regenerates the same dataset (fixed seed), retrains, and overwrites
weights/performance_model.json with the same result every time.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

SEED = 20260731
N_ROWS = 600
# Stated, rerunnable cutoff: the first 80% of generated rows are train, the
# rest are held back for evaluation. Ordering is arbitrary here since the
# data is synthetic and unordered; a real dataset would use a timestamp.
TRAIN_FRACTION = 0.8
LEARNING_RATE = 0.1
EPOCHS = 400

WEIGHTS_PATH = Path(__file__).parent / "weights" / "performance_model.json"


@dataclass
class Row:
    mastery: float  # 0.0-1.0, mean FSRS retrievability across a topic
    difficulty: float  # 0.0-1.0, higher = harder question
    timing_seconds: float  # time taken to answer
    coverage: float  # 0.0-1.0, proportion of requested topics studied
    correct: bool


def generate_synthetic_dataset(n: int, seed: int) -> list[Row]:
    """Synthesizes rows from a known ground-truth relationship plus noise,
    so the training pipeline has real signal to fit and evaluate against.
    Higher mastery/coverage and lower difficulty raise accuracy; timing is
    a weak signal (rushed or very slow answers skew slightly wrong)."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        mastery = rng.random()
        difficulty = rng.random()
        coverage = rng.random()
        timing_seconds = rng.uniform(20, 180)
        # Ground truth: mastery and coverage help, difficulty hurts, being
        # far from a ~70s "comfortable" pace hurts slightly.
        timing_penalty = abs(timing_seconds - 70) / 200
        logit = (
            3.0 * mastery
            + 1.5 * coverage
            - 2.5 * difficulty
            - 1.0 * timing_penalty
            - 0.3
        )
        p_correct = 1 / (1 + math.exp(-logit))
        correct = rng.random() < p_correct
        rows.append(Row(mastery, difficulty, timing_seconds, coverage, correct))
    return rows


def features(row: Row, timing_mean: float, timing_std: float) -> list[float]:
    timing_z = (row.timing_seconds - timing_mean) / timing_std
    return [row.mastery, row.difficulty, timing_z, row.coverage]


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def train_logistic_regression(
    train_rows: list[Row], timing_mean: float, timing_std: float
) -> tuple[float, list[float]]:
    n_features = 4
    bias = 0.0
    weights = [0.0] * n_features
    n = len(train_rows)

    for _ in range(EPOCHS):
        grad_bias = 0.0
        grad_weights = [0.0] * n_features
        for row in train_rows:
            x = features(row, timing_mean, timing_std)
            pred = sigmoid(bias + sum(w * xi for w, xi in zip(weights, x)))
            error = pred - (1.0 if row.correct else 0.0)
            grad_bias += error
            for i, xi in enumerate(x):
                grad_weights[i] += error * xi
        bias -= LEARNING_RATE * grad_bias / n
        weights = [
            w - LEARNING_RATE * g / n for w, g in zip(weights, grad_weights)
        ]

    return bias, weights


def evaluate(
    rows: list[Row], bias: float, weights: list[float], timing_mean: float, timing_std: float
) -> float:
    correct_predictions = 0
    for row in rows:
        x = features(row, timing_mean, timing_std)
        pred = sigmoid(bias + sum(w * xi for w, xi in zip(weights, x))) >= 0.5
        if pred == row.correct:
            correct_predictions += 1
    return correct_predictions / len(rows)


def majority_baseline_accuracy(train_rows: list[Row], eval_rows: list[Row]) -> float:
    majority = sum(1 for r in train_rows if r.correct) / len(train_rows) >= 0.5
    return sum(1 for r in eval_rows if r.correct == majority) / len(eval_rows)


def main() -> None:
    rows = generate_synthetic_dataset(N_ROWS, SEED)
    split_index = int(len(rows) * TRAIN_FRACTION)
    train_rows, eval_rows = rows[:split_index], rows[split_index:]

    timing_mean = sum(r.timing_seconds for r in train_rows) / len(train_rows)
    variance = sum((r.timing_seconds - timing_mean) ** 2 for r in train_rows) / len(train_rows)
    timing_std = math.sqrt(variance)

    bias, weights = train_logistic_regression(train_rows, timing_mean, timing_std)
    eval_accuracy = evaluate(eval_rows, bias, weights, timing_mean, timing_std)
    baseline_accuracy = majority_baseline_accuracy(train_rows, eval_rows)

    print(f"train rows: {len(train_rows)}, eval rows: {len(eval_rows)}")
    print(f"eval accuracy: {eval_accuracy:.3f} (majority baseline: {baseline_accuracy:.3f})")
    if eval_accuracy <= baseline_accuracy:
        raise SystemExit(
            "refusing to write weights: model did not beat the majority baseline"
        )

    WEIGHTS_PATH.parent.mkdir(exist_ok=True)
    WEIGHTS_PATH.write_text(
        json.dumps(
            {
                "synthetic_placeholder": True,
                "bias": bias,
                "weight_mastery": weights[0],
                "weight_difficulty": weights[1],
                "weight_timing_z": weights[2],
                "weight_coverage": weights[3],
                "timing_mean_seconds": timing_mean,
                "timing_std_seconds": timing_std,
                "n_train": len(train_rows),
                "n_eval": len(eval_rows),
                "eval_accuracy": eval_accuracy,
                "baseline_accuracy": baseline_accuracy,
                "seed": SEED,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {WEIGHTS_PATH}")


if __name__ == "__main__":
    main()
