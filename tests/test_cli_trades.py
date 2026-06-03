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
