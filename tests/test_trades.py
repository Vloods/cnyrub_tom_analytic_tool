from datetime import datetime, timezone

from cnyrub_tom.analysis import summarize_trades
from cnyrub_tom.models import Trade
from cnyrub_tom.providers import MoexIssProvider, parse_moex_trades


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.urls = []

    def get_json(self, url):
        self.urls.append(url)
        return self.payload


def test_parse_moex_trades_returns_anonymous_trade_fields():
    payload = {
        "trades": {
            "columns": ["TRADENO", "TRADETIME", "BOARDID", "SECID", "PRICE", "QUANTITY", "VALUE", "SYSTIME", "BUYSELL"],
            "data": [[744540006, "09:59:50", "CETS", "CNYRUB_TOM", 10.7875, 2, 21575.0, "2026-06-03 09:59:50", "S"]],
        }
    }

    trades = parse_moex_trades(payload, secid="CNYRUB_TOM")

    assert trades == [
        Trade(
            tradeno=744540006,
            secid="CNYRUB_TOM",
            ts=datetime(2026, 6, 3, 9, 59, 50, tzinfo=timezone.utc),
            price=10.7875,
            quantity=2.0,
            value=21575.0,
            buysell="S",
            boardid="CETS",
            source="moex-iss-trades",
        )
    ]


def test_moex_provider_requests_anonymous_trades_endpoint_with_filters():
    http = FakeHttp({"trades": {"columns": [], "data": []}})
    provider = MoexIssProvider(http=http)

    trades = provider.get_trades("CNYRUB_TOM", from_="2026-06-03", till="2026-06-03", limit=50)

    assert trades == []
    requested = http.urls[0]
    assert "/engines/currency/markets/selt/securities/CNYRUB_TOM/trades.json" in requested
    assert "from=2026-06-03" in requested
    assert "till=2026-06-03" in requested
    assert "limit=50" in requested


def test_summarize_trades_computes_vwap_volume_and_side_imbalance():
    trades = [
        Trade(tradeno=1, secid="CNYRUB_TOM", ts=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc), price=10.0, quantity=2, value=20000, buysell="B"),
        Trade(tradeno=2, secid="CNYRUB_TOM", ts=datetime(2026, 6, 3, 10, 1, tzinfo=timezone.utc), price=11.0, quantity=1, value=11000, buysell="S"),
    ]

    summary = summarize_trades(trades)

    assert summary["secid"] == "CNYRUB_TOM"
    assert summary["trade_count"] == 2
    assert summary["first_ts"] == "2026-06-03T10:00:00+00:00"
    assert summary["last_ts"] == "2026-06-03T10:01:00+00:00"
    assert summary["min_price"] == 10.0
    assert summary["max_price"] == 11.0
    assert summary["last_price"] == 11.0
    assert summary["quantity"] == 3
    assert summary["value"] == 31000
    assert summary["vwap"] == (10.0 * 2 + 11.0 * 1) / 3
    assert summary["buy_quantity"] == 2
    assert summary["sell_quantity"] == 1
    assert summary["side_imbalance"] == 1 / 3
