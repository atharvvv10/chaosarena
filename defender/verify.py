"""Verify that an anomaly score returns below threshold after remediation."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Sequence

from .collect import sample_once
from .features import vector_from
from .model import Detector


@dataclass
class Verification:
    score_before: float
    score_after: float
    threshold: float
    recovered: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "score_before": round(self.score_before, 4),
            "score_after": round(self.score_after, 4),
            "threshold": round(self.threshold, 4),
            "recovered": self.recovered,
        }


def verify(
    detector: Detector,
    vector_before: Sequence[float],
    wait: float = 10.0,
    sampler: Callable[[], dict] = sample_once,
) -> Verification:
    score_before = detector.score(vector_before)
    if wait > 0:
        time.sleep(wait)
    vector_after = vector_from(sampler())
    score_after = detector.score(vector_after)
    return Verification(
        score_before=score_before,
        score_after=score_after,
        threshold=detector.threshold,
        recovered=score_after <= detector.threshold,
    )
