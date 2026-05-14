"""
Train the detection model on CICIDS2017 / UNSW-NB15.

Usage (inside the backend container):
    python -m backend.scripts.train_detection --dataset cicids
    python -m backend.scripts.train_detection --dataset unsw
    python -m backend.scripts.train_detection --dataset both

Expected file layout (place CSVs in /app/data/datasets):

  data/datasets/cicids2017/*.csv        (MachineLearningCVE split from CIC)
  data/datasets/unsw-nb15/UNSW_NB15_training-set.csv
  data/datasets/unsw-nb15/UNSW_NB15_testing-set.csv

Download links are listed in the project README (Manual steps section).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path

import pandas as pd

from backend.core.config import settings
from backend.core.logging import logger, setup_logging
from backend.ml import detection


def _load_cicids(root: str) -> pd.DataFrame:
    files = glob.glob(os.path.join(root, "**", "*.csv"), recursive=True)
    if not files:
        raise FileNotFoundError(f"No CSVs under {root}")
    logger.info(f"Loading {len(files)} CICIDS CSVs…")
    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_csv(f, low_memory=False, encoding="latin-1"))
        except Exception as e:
            logger.warning(f"Skip {f}: {e}")
    return pd.concat(dfs, ignore_index=True)


def _load_unsw(root: str) -> pd.DataFrame:
    files = glob.glob(os.path.join(root, "*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSVs under {root}")
    logger.info(f"Loading {len(files)} UNSW-NB15 CSVs…")
    return pd.concat(
        [pd.read_csv(f, low_memory=False) for f in files], ignore_index=True
    )


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset", choices=["cicids", "unsw", "both"], default="both"
    )
    parser.add_argument("--data-dir", default=settings.dataset_dir)
    parser.add_argument("--model-dir", default=settings.model_dir)
    parser.add_argument("--test-size", type=float, default=0.2)
    args = parser.parse_args()

    frames: list[pd.DataFrame] = []
    if args.dataset in ("cicids", "both"):
        p = Path(args.data_dir) / "cicids2017"
        if p.exists():
            frames.append(_load_cicids(str(p)))
        else:
            logger.warning(f"CICIDS dir missing: {p}")
    if args.dataset in ("unsw", "both"):
        p = Path(args.data_dir) / "unsw-nb15"
        if p.exists():
            frames.append(_load_unsw(str(p)))
        else:
            logger.warning(f"UNSW dir missing: {p}")

    if not frames:
        raise SystemExit(
            "No datasets found. See README 'Manual steps' for download links."
        )

    df = pd.concat(frames, ignore_index=True)
    logger.info(f"Combined dataset: {df.shape}")

    Path(args.model_dir).mkdir(parents=True, exist_ok=True)
    metrics = detection.train(df, save_dir=args.model_dir, test_size=args.test_size)

    metrics_path = Path(args.model_dir) / "detection_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2))
    logger.info(f"Metrics written to {metrics_path}")


if __name__ == "__main__":
    main()
