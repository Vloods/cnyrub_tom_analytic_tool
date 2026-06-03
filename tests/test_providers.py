import json
from datetime import datetime, timezone

from cnyrub_tom.providers import HttpJsonOrderBookProvider, parse_moex_marketdata


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload

    def get_json(self, url):
        return self.payload


def test_parse_moex_marketdata_returns_quote_fields():
    payload = {
        "marketdata": {
            "columns": ["SECID", "LAST", "BID", "OFFER", "TIME", "UPDATETIME", "SEQNUM"],
            "data": [["CNYRUB_TOM", 12.345, 12.34, 12.35, "10:30:01", "10:30:02", 42]],
        }
    }

    quote = parse_moex_marketdata(payload, secid="CNYRUB_TOM")

    assert quote.secid == "CNYRUB_TOM"
    assert quote.last == 12.345
    assert quote.bid == 12.34
    assert quote.ask == 12.35
    assert quote.seqnum == 42


def test_http_json_orderbook_provider_normalizes_external_payload():
    provider = HttpJsonOrderBookProvider(
        url="https://example.invalid/book",
        http=FakeHttp({
            "ts": "2026-01-02T10:30:00+00:00",
            "bids": [[12.34, 100], [12.33, 50]],
            "asks": [{"price": 12.36, "quantity": 70}],
        }),
    )

    book = provider.get_orderbook("CNYRUB_TOM")

    assert book.secid == "CNYRUB_TOM"
    assert book.ts == datetime(2026, 1, 2, 10, 30, tzinfo=timezone.utc)
    assert [level.price for level in book.bids] == [12.34, 12.33]
    assert [level.quantity for level in book.asks] == [70]
