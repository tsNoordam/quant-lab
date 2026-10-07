"""Deterministic synthetic twin-share pair with a known mispricing process.

    uv run python -m quant_lab.data.synthetic --dataset synthetic_twin

Model (all parameters in ``conf/data/<dataset>.yaml`` under ``synthetic:``):

    V_t        fundamental value per B share, geometric Brownian motion
    m_t        log mispricing, Ornstein-Uhlenbeck around ``mispricing.mean``
    P_a        = parity * V_t * exp(+m_t / 2)
    P_b        = V_t * exp(-m_t / 2)        so  log(P_a / (parity * P_b)) = m_t

Prices above are closes. Opens are the previous close times an overnight gap
shared by both legs plus a small leg-specific gap, so the relative price at the
open stays close to the previous close's relative price, as for real twins.

Volume is independent lognormal noise: the data encodes no relation between
relative volume and mispricing. Each leg misses random days independently.

Writes ``<raw_dir>/<SYMBOL>.csv`` per leg plus ``data/metadata/<name>.json`` and
refuses to overwrite existing raw files (raw data is immutable).
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from omegaconf import DictConfig, OmegaConf

TRADING_DAYS = 252


def simulate_truth(cfg: DictConfig) -> pd.DataFrame:
    """Daily fundamental value and mispricing; the ground truth behind the prices."""
    s = cfg.synthetic
    rng = np.random.default_rng(s.seed)
    n, dt = s.n_days, 1.0 / TRADING_DAYS
    dates = pd.bdate_range(s.start, periods=n, name="date")

    shocks = rng.standard_normal(n)
    log_v = np.log(s.initial_value) + np.cumsum(
        (s.drift - 0.5 * s.vol**2) * dt + s.vol * np.sqrt(dt) * shocks
    )

    m = s.mispricing
    phi = np.exp(-np.log(2) / m.half_life_days)
    step_sd = m.vol * np.sqrt(dt)
    mispricing = np.empty(n)
    mispricing[0] = m.mean + step_sd / np.sqrt(1 - phi**2) * rng.standard_normal()
    for t, eps in enumerate(rng.standard_normal(n - 1), start=1):
        mispricing[t] = m.mean + phi * (mispricing[t - 1] - m.mean) + step_sd * eps

    return pd.DataFrame({"fundamental": np.exp(log_v), "mispricing": mispricing}, index=dates)


def _ohlcv(
    close: pd.Series,
    rng: np.random.Generator,
    s: DictConfig,
    volume_mean: float,
    common_gap: np.ndarray,
) -> pd.DataFrame:
    n = len(close)
    noise = s.intraday_vol * rng.standard_normal((2, n))
    prev_close = close.shift(1).fillna(close.iloc[0]).to_numpy()
    # Overnight news moves both twins together; only a small part is leg-specific.
    open_ = prev_close * np.exp(common_gap + s.open_idio_vol * rng.standard_normal(n))
    body_high = np.maximum(open_, close.to_numpy())
    body_low = np.minimum(open_, close.to_numpy())
    volume = volume_mean * np.exp(
        s.volume_dispersion * rng.standard_normal(n) - 0.5 * s.volume_dispersion**2
    )
    df = pd.DataFrame(
        {
            "open": open_,
            "high": body_high * np.exp(np.abs(noise[0])),
            "low": body_low * np.exp(-np.abs(noise[1])),
            "close": close.to_numpy(),
            "adj_close": close.to_numpy(),  # no corporate actions in the synthetic pair
            "volume": np.round(volume).astype("int64"),
        },
        index=close.index,
    ).round({"open": 4, "high": 4, "low": 4, "close": 4, "adj_close": 4})
    keep = rng.random(n) >= s.missing_frac
    keep[0] = True
    return df.loc[keep]


def generate_pair(cfg: DictConfig) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Return ({symbol: ohlcv}, truth). Same config, same output, bit for bit."""
    truth = simulate_truth(cfg)
    s = cfg.synthetic
    rng = np.random.default_rng([s.seed, 1])
    half = np.exp(truth["mispricing"] / 2)
    closes = {
        cfg.legs.a: cfg.parity_ratio * truth["fundamental"] * half,
        cfg.legs.b: truth["fundamental"] / half,
    }
    common_gap = s.intraday_vol * rng.standard_normal(len(truth))
    legs = {
        symbol: _ohlcv(close, rng, s, volume_mean, common_gap)
        for (symbol, close), volume_mean in zip(closes.items(), s.volume_mean, strict=True)
    }
    return legs, truth


def write_raw(cfg: DictConfig, root: Path, *, force: bool = False) -> list[Path]:
    raw_dir = root / cfg.raw_dir
    legs, _ = generate_pair(cfg)
    paths = [raw_dir / f"{symbol}.csv" for symbol in legs]
    existing = [p for p in paths if p.exists()]
    if existing and not force:
        raise FileExistsError(f"raw data is immutable, refusing to overwrite {existing}")
    raw_dir.mkdir(parents=True, exist_ok=True)
    for path, df in zip(paths, legs.values(), strict=True):
        df.to_csv(path, index_label="date", date_format="%Y-%m-%d")

    starts = [df.index.min() for df in legs.values()]
    ends = [df.index.max() for df in legs.values()]
    metadata = {
        "dataset": cfg.name,
        "source": "synthetic",
        "generator": "quant_lab.data.synthetic",
        "config": f"conf/data/{cfg.name}.yaml",
        "seed": cfg.synthetic.seed,
        "symbols": list(legs),
        "start": str(min(starts).date()),
        "end": str(max(ends).date()),
        "calendar": cfg.calendar,
        "timezone": "naive exchange-local dates",
        "currency": cfg.currency,
        "adjusted": "no corporate actions; adj_close == close",
        "parity_ratio": cfg.parity_ratio,
        "columns": ["date", "open", "high", "low", "close", "adj_close", "volume"],
    }
    meta_path = root / "data" / "metadata" / f"{cfg.name}.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
    return [*paths, meta_path]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", required=True, help="name of conf/data/<dataset>.yaml")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root")
    parser.add_argument("--force", action="store_true", help="overwrite existing raw files")
    args = parser.parse_args(argv)
    cfg = OmegaConf.load(args.root / "conf" / "data" / f"{args.dataset}.yaml")
    for path in write_raw(cfg, args.root, force=args.force):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
