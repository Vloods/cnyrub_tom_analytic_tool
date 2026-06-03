from datetime import datetime, timezone

from pathlib import Path

from cnyrub_tom.clusterdelta import build_cluster_delta_rows, build_live_cluster_delta_state, render_cluster_delta_chart
from cnyrub_tom.models import Trade


def _trade(tradeno: int, ts: str, price: float, qty: float, side: str) -> Trade:
    return Trade(
        tradeno=tradeno,
        secid="CNYRUB_TOM",
        ts=datetime.fromisoformat(ts).replace(tzinfo=timezone.utc),
        price=price,
        quantity=qty,
        value=price * qty,
        buysell=side,
    )


def test_build_cluster_delta_rows_groups_by_three_minute_bucket_and_price():
    trades = [
        _trade(1, "2026-06-03T10:00:05", 12.340, 100, "B"),
        _trade(2, "2026-06-03T10:01:10", 12.340, 40, "S"),
        _trade(3, "2026-06-03T10:02:59", 12.350, 30, "B"),
        _trade(4, "2026-06-03T10:03:00", 12.340, 70, "S"),
    ]

    rows = build_cluster_delta_rows(trades, bucket_minutes=3)

    assert rows == [
        {
            "bucket_start": "2026-06-03T10:00:00+00:00",
            "bucket_end": "2026-06-03T10:03:00+00:00",
            "secid": "CNYRUB_TOM",
            "price": 12.34,
            "buy_qty": 100.0,
            "sell_qty": 40.0,
            "delta": 60.0,
            "volume": 140.0,
            "trade_count": 2,
        },
        {
            "bucket_start": "2026-06-03T10:00:00+00:00",
            "bucket_end": "2026-06-03T10:03:00+00:00",
            "secid": "CNYRUB_TOM",
            "price": 12.35,
            "buy_qty": 30.0,
            "sell_qty": 0.0,
            "delta": 30.0,
            "volume": 30.0,
            "trade_count": 1,
        },
        {
            "bucket_start": "2026-06-03T10:03:00+00:00",
            "bucket_end": "2026-06-03T10:06:00+00:00",
            "secid": "CNYRUB_TOM",
            "price": 12.34,
            "buy_qty": 0.0,
            "sell_qty": 70.0,
            "delta": -70.0,
            "volume": 70.0,
            "trade_count": 1,
        },
    ]


def test_build_cluster_delta_rows_can_round_to_price_step():
    trades = [
        _trade(1, "2026-06-03T10:00:05", 12.341, 10, "B"),
        _trade(2, "2026-06-03T10:00:06", 12.344, 20, "S"),
    ]

    rows = build_cluster_delta_rows(trades, bucket_minutes=3, price_step=0.01)

    assert len(rows) == 1
    assert rows[0]["price"] == 12.34
    assert rows[0]["delta"] == -10.0


def test_render_cluster_delta_chart_shows_three_minute_buckets_prices_and_delta():
    rows = build_cluster_delta_rows([
        _trade(1, "2026-06-03T10:00:05", 12.34, 100, "B"),
        _trade(2, "2026-06-03T10:00:06", 12.35, 50, "S"),
    ], bucket_minutes=3)

    chart = render_cluster_delta_chart(rows)

    assert "Cluster Delta 3m" in chart
    assert "10:00-10:03" in chart
    assert "12.350" in chart
    assert "-50" in chart
    assert "+100" in chart


def test_build_live_cluster_delta_state_reads_csv_from_session_start(tmp_path: Path):
    trades_csv = tmp_path / "trades.csv"
    trades_csv.write_text(
        "tradeno,secid,ts,price,quantity,value,buysell\n"
        "1,CNYRUB_TOM,2026-06-02T18:45:05+00:00,12.300,999,12287.7,B\n"
        "2,CNYRUB_TOM,2026-06-03T10:00:05+00:00,12.340,100,1234,B\n"
        "3,CNYRUB_TOM,2026-06-03T10:03:05+00:00,12.350,50,617.5,S\n"
        "4,CNYRUB_TOM,2026-06-03T10:06:05+00:00,12.360,25,309,B\n",
        encoding="utf-8",
    )

    state = build_live_cluster_delta_state(trades_csv, bucket_minutes=3, price_step=0.001, max_buckets=None)

    assert state.status == "active"
    assert state.trade_count == 3
    assert state.row_count == 3
    assert "с начала сессии" in state.summary
    assert "сделок: 3" in state.summary
    assert "10:00-10:03" in state.chart
    assert "10:03-10:06" in state.chart
    assert "10:06-10:09" in state.chart
    assert "18:45-18:48" not in state.chart


def test_build_live_cluster_delta_state_reports_missing_file(tmp_path: Path):
    state = build_live_cluster_delta_state(tmp_path / "missing.csv")

    assert state.status == "missing"
    assert state.trade_count == 0
    assert "CSV сделок не найден" in state.summary
    assert "нет сделок" in state.chart
