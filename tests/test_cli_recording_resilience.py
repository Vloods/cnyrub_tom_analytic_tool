from datetime import datetime, timezone

from cnyrub_tom import cli
from cnyrub_tom.models import OrderBook, OrderLevel, Trade
from cnyrub_tom.storage import SnapshotStore


class FlakyTradesProvider:
    def __init__(self) -> None:
        self.calls = 0

    def get_trades(self, secid, from_=None, till=None, limit=100):
        self.calls += 1
        if self.calls == 1:
            raise OSError("temporary MOEX connection error")
        return [Trade(
            tradeno=101,
            secid=secid,
            ts=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
            price=12.34,
            quantity=10,
            value=123.4,
            buysell="B",
            boardid="CETS",
        )]


class FlakyOrderBookProvider:
    def __init__(self) -> None:
        self.calls = 0

    def get_orderbook(self, secid):
        self.calls += 1
        if self.calls == 1:
            raise ValueError("incomplete QUIK JSON while file is being rewritten")
        return OrderBook(
            secid=secid,
            ts=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
            bids=[OrderLevel(price=12.34, quantity=100)],
            asks=[OrderLevel(price=12.35, quantity=120)],
            source="test",
        )


def test_record_trades_retries_after_temporary_provider_error(monkeypatch, tmp_path, capsys):
    provider = FlakyTradesProvider()
    monkeypatch.setattr(cli, "MoexIssProvider", lambda: provider)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    output = tmp_path / "trades.csv"

    result = cli.main(["record-trades", "--output", str(output), "--count", "1"])

    assert result == 0
    assert provider.calls == 2
    assert "101" in output.read_text(encoding="utf-8")
    assert "record-trades error" in capsys.readouterr().err


def test_record_orderbook_retries_after_temporary_quik_read_error(monkeypatch, tmp_path, capsys):
    provider = FlakyOrderBookProvider()
    monkeypatch.setattr(cli, "_provider_from_args", lambda _args: provider)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    db_path = tmp_path / "orderbook.sqlite"

    result = cli.main(["record-orderbook", "--db", str(db_path), "--count", "1"])

    assert result == 0
    assert provider.calls == 2
    assert len(list(SnapshotStore(db_path).iter_orderbooks(secid="CNYRUB_TOM"))) == 1
    assert "record-orderbook error" in capsys.readouterr().err
