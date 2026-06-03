import csv
from datetime import datetime, timezone

from cnyrub_tom import cli
from cnyrub_tom.models import Trade


class FakeProvider:
    def get_trades(self, secid, from_=None, till=None, limit=100):
        assert secid == "CNYRUB_TOM"
        assert from_ == "2026-06-03"
        assert till == "2026-06-03"
        assert limit == 2
        return [
            Trade(tradeno=1, secid="CNYRUB_TOM", ts=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc), price=10.0, quantity=2, value=20000, buysell="B", boardid="CETS"),
            Trade(tradeno=2, secid="CNYRUB_TOM", ts=datetime(2026, 6, 3, 10, 1, tzinfo=timezone.utc), price=11.0, quantity=1, value=11000, buysell="S", boardid="CETS"),
        ]


def test_trades_command_prints_anonymous_trades_json(monkeypatch, capsys):
    monkeypatch.setattr(cli, "MoexIssProvider", lambda: FakeProvider())

    result = cli.main(["trades", "--from", "2026-06-03", "--till", "2026-06-03", "--limit", "2"])

    assert result == 0
    output = capsys.readouterr().out
    assert '"tradeno": 1' in output
    assert '"buysell": "B"' in output
    assert '"boardid": "CETS"' in output


def test_analyze_trades_command_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr(cli, "MoexIssProvider", lambda: FakeProvider())

    result = cli.main(["analyze-trades", "--from", "2026-06-03", "--till", "2026-06-03", "--limit", "2"])

    assert result == 0
    output = capsys.readouterr().out
    assert '"trade_count": 2' in output
    assert '"vwap": 10.333333333333334' in output
    assert '"side_imbalance": 0.3333333333333333' in output


class FakeStreamingProvider:
    def __init__(self):
        self.calls = 0

    def get_trades(self, secid, from_=None, till=None, limit=100):
        self.calls += 1
        first = Trade(tradeno=1, secid=secid, ts=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc), price=10.0, quantity=2, value=20000, buysell="B", boardid="CETS")
        second = Trade(tradeno=2, secid=secid, ts=datetime(2026, 6, 3, 10, 1, tzinfo=timezone.utc), price=11.0, quantity=1, value=11000, buysell="S", boardid="CETS")
        third = Trade(tradeno=3, secid=secid, ts=datetime(2026, 6, 3, 10, 2, tzinfo=timezone.utc), price=12.0, quantity=3, value=36000, buysell="B", boardid="CETS")
        return [first, second] if self.calls == 1 else [second, third]


def test_record_trades_command_appends_only_new_trade_numbers(monkeypatch, tmp_path, capsys):
    provider = FakeStreamingProvider()
    monkeypatch.setattr(cli, "MoexIssProvider", lambda: provider)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    output = tmp_path / "trades.csv"

    result = cli.main(["record-trades", "--output", str(output), "--limit", "100", "--interval", "0.01", "--count", "2"])

    assert result == 0
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert [row["tradeno"] for row in rows] == ["1", "2", "3"]
    assert provider.calls == 2
    stdout = capsys.readouterr().out
    assert "saved 2 new anonymous trades" in stdout
    assert "saved 1 new anonymous trades" in stdout


class EmptyStreamingProvider:
    def get_trades(self, secid, from_=None, till=None, limit=100):
        return []


def test_record_trades_command_creates_empty_csv_header(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "MoexIssProvider", lambda: EmptyStreamingProvider())
    output = tmp_path / "trades.csv"

    result = cli.main(["record-trades", "--output", str(output), "--count", "1"])

    assert result == 0
    assert output.read_text(encoding="utf-8").startswith("tradeno,secid,ts,price,quantity,value,buysell,boardid,source")
