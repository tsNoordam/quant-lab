"""Download raw futures bars from Databento, cost first (ROADMAP step 21).

    uv run python -m quant_lab.data.databento_fetch --config conf/futures/es.yaml
    uv run python -m quant_lab.data.databento_fetch --config conf/futures/es.yaml --download

Without ``--download`` nothing is bought: the script prints, per symbol, the
billable size and the cost Databento quotes for the configured request.
With ``--download`` it writes each symbol's records unmodified, as Databento's
own DBN file (zstd), to the config's ``raw_dir``, and writes the provenance
file ``data/metadata/databento_<name>.json`` (request, cost quote, md5). The
raw directory then enters DVC with ``dvc add``; it is never edited.

The API key is read from the environment variable ``DATABENTO_API_KEY``, or
from a ``.env`` file in the repository root (git-ignored). It is never
printed or written anywhere.

Databento data is licensed: it stays in DVC and is never committed to git or
pasted into notes, issues or chat.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from omegaconf import DictConfig, OmegaConf

KEY_VAR = "DATABENTO_API_KEY"


def load_config(path: Path) -> DictConfig:
    cfg = OmegaConf.load(path)
    for key in ("dataset", "schema", "stype_in", "symbols", "start", "end", "raw_dir"):
        if key not in cfg.source:
            raise ValueError(f"{path}: source.{key} is missing")
    return cfg


def api_key(root: Path) -> str:
    """The key from the environment, else from ``root/.env``; never logged."""
    if not os.environ.get(KEY_VAR):
        from dotenv import load_dotenv

        load_dotenv(root / ".env", override=False)
    key = os.environ.get(KEY_VAR, "").strip()
    if not key or key in {"key", "your-key"}:
        raise SystemExit(f"{KEY_VAR} is not set (environment or {root / '.env'})")
    return key


def raw_filename(symbol: str, src: DictConfig) -> str:
    return f"{symbol}.{src.schema}.{src.start}_{src.end}.dbn.zst"


def request(src: DictConfig, symbol: str) -> dict:
    return {
        "dataset": src.dataset,
        "symbols": [symbol],
        "schema": src.schema,
        "stype_in": src.stype_in,
        "start": src.start,
        "end": src.end,
    }


def quote(client, src: DictConfig) -> list[dict]:
    """Billable size and cost per symbol, as Databento quotes them."""
    rows = []
    for symbol in src.symbols:
        req = request(src, symbol)
        rows.append(
            {
                "symbol": symbol,
                "billable_bytes": int(client.metadata.get_billable_size(**req)),
                "cost_usd": float(client.metadata.get_cost(**req)),
            }
        )
    return rows


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(client, cfg: DictConfig, root: Path, quotes: list[dict]) -> dict:
    src = cfg.source
    raw_dir = root / src.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for q in quotes:
        name = raw_filename(q["symbol"], src)
        path = raw_dir / name
        if path.exists():
            raise SystemExit(f"{path} exists: raw data is immutable; remove it deliberately first")
        client.timeseries.get_range(**request(src, q["symbol"]), path=path)
        files[name] = {
            "md5": md5(path),
            "bytes": path.stat().st_size,
            "billable_bytes": q["billable_bytes"],
            "quoted_cost_usd": q["cost_usd"],
            "downloaded": dt.date.today().isoformat(),
        }
    meta = metadata(cfg, files)
    out = root / "data" / "metadata" / f"databento_{cfg.name}.json"
    out.write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def metadata(cfg: DictConfig, files: dict) -> dict:
    src = cfg.source
    return {
        "dataset": f"databento_{cfg.name}",
        "description": (
            f"{src.dataset} {src.schema} bars for {', '.join(src.symbols)} "
            f"({src.stype_in} symbology), {src.start} to {src.end} (end exclusive)."
        ),
        "source": "Databento historical API (https://databento.com), "
        "quant_lab.data.databento_fetch",
        "license": "Licensed vendor data: stays in DVC, never in git, notes or chat.",
        "request": OmegaConf.to_container(src, resolve=True),
        "layout": f"{src.raw_dir}/<symbol>.{src.schema}.<start>_<end>.dbn.zst, "
        "Databento DBN (zstd), unmodified",
        "files": files,
        "timezone": "UTC (ts_event, nanoseconds, start of the bar)",
        "used_by": ["quant_lab.data.es_futures (dvc stage es_ingest)"],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--download", action="store_true", help="buy and download (else cost only)")
    args = parser.parse_args(argv)

    import databento as db

    cfg = load_config(args.root / args.config)
    client = db.Historical(key=api_key(args.root))
    quotes = quote(client, cfg.source)
    total = sum(q["cost_usd"] for q in quotes)
    for q in quotes:
        print(f"{q['symbol']}: {q['billable_bytes'] / 1e6:,.1f} MB, ${q['cost_usd']:,.2f}")
    print(f"total: ${total:,.2f}")
    if not args.download:
        print("cost only; rerun with --download to buy and download")
        return
    meta = download(client, cfg, args.root, quotes)
    for name, f in meta["files"].items():
        print(f"{name}: {f['bytes'] / 1e6:,.1f} MB on disk, md5 {f['md5']}")
    print(f"next: uv run dvc add {cfg.source.raw_dir}")


if __name__ == "__main__":
    main()
