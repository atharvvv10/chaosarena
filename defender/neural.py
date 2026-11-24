"""LSTM autoencoder anomaly detector — the deep defender.

It learns the shape of normal traffic from the same baseline CSV as the
Isolation Forest, then scores reconstruction error over a sliding window. The
public ``score`` / ``is_anomaly`` / ``save`` / ``load`` surface mirrors the
classical detector so the two can be compared fairly.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch
from torch import nn

from .features import FEATURE_NAMES

DEFAULT_MODEL = Path("ml/deep/defender_lstm.pt")


class _Autoencoder(nn.Module):
    def __init__(self, n_features: int, hidden: int) -> None:
        super().__init__()
        self.encoder = nn.LSTM(n_features, hidden, batch_first=True)
        self.decoder = nn.LSTM(hidden, hidden, batch_first=True)
        self.head = nn.Linear(hidden, n_features)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (hidden_state, _) = self.encoder(x)
        context = hidden_state.transpose(0, 1).squeeze(1)
        repeated = context.unsqueeze(1).expand(-1, x.size(1), -1)
        decoded, _ = self.decoder(repeated)
        return self.head(decoded)


class NeuralDetector:
    """Windowed reconstruction-error detector with a calibrated threshold."""

    def __init__(
        self,
        window: int = 8,
        hidden: int = 32,
        seed: int = 42,
        quantile: float = 0.99,
        margin: float = 0.05,
    ) -> None:
        if window < 2:
            raise ValueError("window must be at least 2")
        self.window = window
        self.hidden = hidden
        self.seed = seed
        self.quantile = quantile
        self.margin = margin
        self.n_features = len(FEATURE_NAMES)
        self.mean: np.ndarray | None = None
        self.std: np.ndarray | None = None
        self.threshold = 0.0
        self.buffer: deque[list[float]] = deque(maxlen=window)
        torch.manual_seed(seed)
        self.model = _Autoencoder(self.n_features, hidden)
        self.losses: list[float] = []

    def reset(self) -> None:
        """Clear the streaming window between battles."""
        self.buffer.clear()

    def _windows(self, scaled: np.ndarray) -> np.ndarray:
        return np.asarray(
            [scaled[i : i + self.window] for i in range(len(scaled) - self.window + 1)],
            dtype=np.float32,
        )

    def _loss(self, batch: torch.Tensor) -> torch.Tensor:
        reconstructed = self.model(batch)
        return nn.functional.mse_loss(reconstructed, batch)

    def train(
        self,
        rows: Sequence[Sequence[float]],
        epochs: int = 200,
        lr: float = 1e-3,
        batch_size: int = 16,
        augment: float = 0.05,
    ) -> dict[str, Any]:
        matrix = np.asarray(rows, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[0] < 5 or matrix.shape[1] != self.n_features:
            raise ValueError(
                f"need at least 5 rows of {self.n_features} features to train the neural detector"
            )
        self.mean = matrix.mean(axis=0)
        self.std = np.where(matrix.std(axis=0) < 1e-9, 1.0, matrix.std(axis=0))
        scaled = (matrix - self.mean) / self.std
        windows = self._windows(scaled)
        if len(windows) < 4:
            raise ValueError("baseline is too short for the configured window")
        if augment > 0:
            # Teach the autoencoder that small jitter around normal traffic is
            # still normal. Without this, a tiny feature std makes harmless
            # noise look like a fault.
            generator = np.random.default_rng(self.seed)
            windows = np.concatenate(
                [windows, windows + generator.normal(0.0, augment, size=windows.shape)],
                axis=0,
            ).astype(np.float32)

        tensor = torch.as_tensor(windows, dtype=torch.float32)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        generator = torch.Generator().manual_seed(self.seed)
        for _ in range(epochs):
            order = torch.randperm(len(tensor), generator=generator)
            for start in range(0, len(order), batch_size):
                batch = tensor[order[start : start + batch_size]]
                optimizer.zero_grad()
                loss = self._loss(batch)
                loss.backward()
                optimizer.step()

        self.model.eval()
        with torch.no_grad():
            values = np.asarray(
                [float(self._loss(tensor[i : i + 1])) for i in range(len(tensor))]
            )
        self.losses = [round(float(v), 6) for v in values.tolist()]
        spread = float(np.std(values))
        self.threshold = round(
            float(np.quantile(values, self.quantile)) + self.margin * spread, 6
        )
        self.reset()
        return {
            "samples": int(matrix.shape[0]),
            "windows": int(len(windows)),
            "epochs": epochs,
            "window": self.window,
            "hidden": self.hidden,
            "threshold": self.threshold,
            "final_loss": self.losses[-1] if self.losses else None,
            "seed": self.seed,
        }

    def calibrate(
        self,
        rows: Sequence[Sequence[float]],
        quantile: float = 0.99,
        margin: float = 0.1,
    ) -> float:
        """Set the threshold from clean samples held out of training."""
        self.reset()
        scores: list[float] = []
        for row in rows:
            value = self.score(row)
            if value > 0.0:
                scores.append(value)
        if len(scores) < 2:
            raise ValueError("need at least two calibration windows")
        values = np.asarray(scores)
        self.threshold = round(
            float(np.quantile(values, quantile)) + margin * float(np.std(values)), 6
        )
        self.reset()
        return self.threshold

    def score(self, vector: Sequence[float]) -> float:
        if self.mean is None or self.std is None:
            raise RuntimeError("neural detector is not trained")
        row = np.asarray(vector, dtype=np.float32)
        if row.shape != (self.n_features,):
            raise ValueError(f"expected a {self.n_features}-value feature vector")
        self.buffer.append(((row - self.mean) / self.std).tolist())
        if len(self.buffer) < self.window:
            return 0.0
        batch = torch.as_tensor([list(self.buffer)], dtype=torch.float32)
        self.model.eval()
        with torch.no_grad():
            return round(float(self._loss(batch)), 6)

    def is_anomaly(self, vector: Sequence[float]) -> bool:
        return self.score(vector) > self.threshold

    def save(self, path: Path | str = DEFAULT_MODEL) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "state_dict": self.model.state_dict(),
                "mean": self.mean,
                "std": self.std,
                "threshold": self.threshold,
                "window": self.window,
                "hidden": self.hidden,
                "seed": self.seed,
                "quantile": self.quantile,
                "margin": self.margin,
                "losses": self.losses[-500:],
                "features": list(FEATURE_NAMES),
            },
            target,
        )
        return target

    @classmethod
    def load(cls, path: Path | str = DEFAULT_MODEL) -> "NeuralDetector":
        payload = torch.load(Path(path), map_location="cpu", weights_only=False)
        if tuple(payload.get("features", ())) != FEATURE_NAMES:
            raise ValueError("model feature layout does not match this project")
        detector = cls(
            window=int(payload["window"]),
            hidden=int(payload["hidden"]),
            seed=int(payload["seed"]),
            quantile=float(payload["quantile"]),
            margin=float(payload["margin"]),
        )
        detector.model.load_state_dict(payload["state_dict"])
        detector.mean = np.asarray(payload["mean"], dtype=np.float32)
        detector.std = np.asarray(payload["std"], dtype=np.float32)
        detector.threshold = float(payload["threshold"])
        detector.losses = list(payload.get("losses", []))
        return detector
