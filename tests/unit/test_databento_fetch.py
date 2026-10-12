"""Databento fetch: cost first, immutable raw files, key never written."""

import json
from types import SimpleNamespace

import pytest
from omegaconf import OmegaConf

from quant_lab.data import databento_fetch as f

CFG = OmegaConf.create(
    {
        "name": "es",
        "source": {
            "vendor": "databento",
            "dataset": "GLBX.MDP3",
            "schema": "ohlcv-1m",
            "stype_in": "continuous",
            "symbols": ["ES.v.0", "ES.v.1"],
            "start": "2010-06-06",
            "end": "2026-10-01",
            "raw_dir": "data/raw/databento_es",
        },
    }
)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.metadata = SimpleNamespace(get_cost=self._cost, get_billable_size=self._size)
        self.timeseries = SimpleNamespace(get_range=self._get_range)

    def _cost(self, **req):
        self.calls.append(("cost", req))
        return 1.25

    def _size(self, **req):
        return 1_000_000

    def _get_range(self, path, **req):
        self.calls.append(("get_range", req))
        path.write_bytes(b"DBN" + req["symbols"][0].encode())


def test_quote_buys_nothing():
    client = FakeClient()
    rows = f.quote(client, CFG.source)
    assert [r["symbol"] for r in rows] == ["ES.v.0", "ES.v.1"]
    assert all(kind == "cost" for kind, _ in client.calls)
    req = client.calls[0][1]
    assert req["stype_in"] == "continuous" and req["schema"] == "ohlcv-1m"
    assert req["start"] == "2010-06-06" and req["end"] == "2026-10-01"


def test_download_writes_raw_files_and_metadata(tmp_path):
    (tmp_path / "data" / "metadata").mkdir(parents=True)
    client = FakeClient()
    meta = f.download(client, CFG, tmp_path, f.quote(client, CFG.source))
    names = sorted(meta["files"])
    assert names == [
        "ES.v.0.ohlcv-1m.2010-06-06_2026-10-01.dbn.zst",
        "ES.v.1.ohlcv-1m.2010-06-06_2026-10-01.dbn.zst",
    ]
    written = json.loads((tmp_path / "data/metadata/databento_es.json").read_text())
    assert written["files"][names[0]]["md5"] == f.md5(tmp_path / CFG.source.raw_dir / names[0])
    assert written["request"]["symbols"] == ["ES.v.0", "ES.v.1"]
    assert "key" not in json.dumps(written["request"]).lower()


def test_download_refuses_to_overwrite_raw_data(tmp_path):
    (tmp_path / "data" / "metadata").mkdir(parents=True)
    raw = tmp_path / CFG.source.raw_dir
    raw.mkdir(parents=True)
    (raw / f.raw_filename("ES.v.0", CFG.source)).write_bytes(b"old")
    client = FakeClient()
    with pytest.raises(SystemExit, match="immutable"):
        f.download(client, CFG, tmp_path, f.quote(client, CFG.source))


def test_api_key_from_dotenv_and_placeholder_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv(f.KEY_VAR, raising=False)
    (tmp_path / ".env").write_text(f"{f.KEY_VAR}=key\n")
    with pytest.raises(SystemExit, match="not set"):
        f.api_key(tmp_path)
    monkeypatch.delenv(f.KEY_VAR, raising=False)
    (tmp_path / ".env").write_text(f"{f.KEY_VAR}=db-abc123\n")
    assert f.api_key(tmp_path) == "db-abc123"


def test_cost_only_cli_does_not_download(tmp_path, monkeypatch, capsys):
    import databento

    (tmp_path / "conf").mkdir()
    OmegaConf.save(CFG, tmp_path / "conf" / "es.yaml")
    client = FakeClient()
    monkeypatch.setattr(databento, "Historical", lambda key: client)
    monkeypatch.setenv(f.KEY_VAR, "db-test")
    f.main(["--config", "conf/es.yaml", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert "total: $2.50" in out and "db-test" not in out
    assert not any(kind == "get_range" for kind, _ in client.calls)
    assert not (tmp_path / CFG.source.raw_dir).exists()
