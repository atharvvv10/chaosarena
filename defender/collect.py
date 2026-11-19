"""Collect feature vectors from Prometheus.

The defender reads only signals a normal operator can see: request rate, error
rate and p95 latency per service. It has no access to the attacker's intent.
"""
from __future__ import annotations

import csv
import json
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .features import FEATURE_NAMES, SERVICES, empty_sample, vector_from

DEFAULT_PROMETHEUS_URL = "http://localhost:9090"
DEFAULT_BASELINE = Path("ml/baseline.csv")


def prometheus_url() -> str:
    return os.environ.get("PROMETHEUS_URL", DEFAULT_PROMETHEUS_URL).rstrip("/")


def query(query_text: str) -> list[dict[str, Any]]:
    url = f"{prometheus_url()}/api/v1/query?{urllib.parse.urlencode({'query': query_text})}"
    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload.get('error', 'unknown error')}")
    return payload["data"]["result"]


def _value(result: list[dict[str, Any]]) -> dict[str, float]:
    values: dict[str, float] = {}
    for item in result:
        service = item.get("metric", {}).get("service")
        if not service:
            continue
        try:
            number = float(item["value"][1])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(number):
            values[service] = number
    return values


def sample_once(window: str = "30s") -> dict[str, dict[str, float]]:
    """Return one sample: {service: {request_rate, error_rate, p95_latency}}."""
    queries = {
        "request_rate": f"sum by (service) (rate(http_requests_total[{window}]))",
        "error_rate": f"sum by (service) (rate(http_errors_total[{window}]))",
        "p95_latency": (
            "histogram_quantile(0.95, "
            f"sum by (le, service) (rate(http_request_duration_seconds_bucket[{window}])))"
        ),
    }
    results = {name: _value(query(text)) for name, text in queries.items()}
    sample = empty_sample()
    for service in SERVICES:
        for metric in results:
            sample[service][metric] = results[metric].get(service, 0.0)
    return sample


def collect_baseline(
    samples: int = 40,
    interval: float = 5.0,
    output: Path | str = DEFAULT_BASELINE,
    window: str = "1m",
) -> Path:
    """Collect `samples` normal-traffic vectors and write them to CSV."""
    if samples < 5:
        raise ValueError("need at least 5 baseline samples to train a model")
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(FEATURE_NAMES)
        for index in range(samples):
            row = vector_from(sample_once(window))
            writer.writerow([f"{value:.6f}" for value in row])
            if index < samples - 1:
                time.sleep(interval)
    return path


def load_baseline(path: Path | str = DEFAULT_BASELINE) -> list[list[float]]:
    """Read baseline vectors back from CSV."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader, None)  # header
        return [[float(value) for value in row] for row in reader if row]
