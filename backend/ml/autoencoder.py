"""
Optional PyTorch autoencoder for unsupervised anomaly detection.

Trains only on benign traffic; high reconstruction error at inference time
indicates an anomaly.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from backend.core.logging import logger


class Autoencoder(nn.Module):
    def __init__(self, input_dim: int, hidden: int = 32, latent: int = 8):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, latent),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent, hidden),
            nn.ReLU(),
            nn.Linear(hidden, input_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.encoder(x))


def train_autoencoder(
    X_benign: np.ndarray,
    epochs: int = 20,
    batch_size: int = 256,
    lr: float = 1e-3,
    save_path: Optional[str] = None,
) -> Autoencoder:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    X = torch.tensor(X_benign, dtype=torch.float32)
    ds = TensorDataset(X)
    dl = DataLoader(ds, batch_size=batch_size, shuffle=True)

    model = Autoencoder(input_dim=X.shape[1]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    model.train()
    for epoch in range(epochs):
        total = 0.0
        for (batch,) in dl:
            batch = batch.to(device)
            opt.zero_grad()
            out = model(batch)
            loss = loss_fn(out, batch)
            loss.backward()
            opt.step()
            total += loss.item() * batch.size(0)
        logger.info(f"AE epoch {epoch + 1}/{epochs}  loss={total / len(ds):.6f}")

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), save_path)
        logger.info(f"Autoencoder saved → {save_path}")

    return model


def anomaly_score(model: Autoencoder, x: np.ndarray) -> float:
    """Return reconstruction MSE for a single sample (higher = more anomalous)."""
    model.eval()
    with torch.no_grad():
        t = torch.tensor(x, dtype=torch.float32).unsqueeze(0)
        recon = model(t)
        return float(((recon - t) ** 2).mean().item())
