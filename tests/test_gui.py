from cnyrub_tom.gui import (
    action_help_text,
    build_cli_command,
    command_to_text,
    dashboard_state_lines,
    default_paths,
    recorder_state_line,
    setup_steps,
)
from cnyrub_tom.realtime import DashboardState


def test_default_paths_are_windows_friendly():
    paths = default_paths()

    assert paths.orderbook_path.endswith("cnyrub_tom_orderbook.json")
    assert paths.db_path.endswith("cnyrub_tom_orderbook.sqlite")
    assert paths.analysis_csv.endswith("cnyrub_tom_analysis.csv")
    assert paths.cluster_delta_csv.endswith("cnyrub_tom_cluster_delta_3m.csv")
    assert paths.cumulative_delta_csv.endswith("cnyrub_tom_cumulative_delta_3m.csv")
    assert paths.volume_profile_csv.endswith("cnyrub_tom_volume_profile.csv")
    assert paths.trade_alerts_csv.endswith("cnyrub_tom_trade_alerts.csv")


def test_recorder_state_line_is_clear_for_start_stop_buttons():
    assert recorder_state_line(False, None) == "Запись: остановлена"
    assert recorder_state_line(True, "record-orderbook") == "Запись стакана: идет"
    assert recorder_state_line(True, "record-trades") == "Запись сделок: идет"
    assert recorder_state_line(True, "quote") == "Выполняется: quote"


def test_setup_steps_are_operator_friendly_and_quik_first():
    steps = setup_steps()

    assert steps[0].startswith("1. Запусти QUIK")
    assert any("QLua" in step for step in steps)
    assert any("Запустить запись" in step for step in steps)


def test_action_help_text_explains_primary_buttons():
    assert "пишет стакан" in action_help_text("record-orderbook")
    assert "разово" in action_help_text("orderbook")
    assert "CSV" in action_help_text("detect-accumulation")
    assert "3-минут" in action_help_text("cluster-delta")
    assert "накоплен" in action_help_text("cumulative-delta")
    assert "профиль" in action_help_text("volume-profile")
    assert "смотри" in action_help_text("trade-alerts")
    assert "автообнов" in action_help_text("live-cluster-delta")
    assert "сделки" in action_help_text("record-trades")
    assert action_help_text("unknown") == "Выполняет выбранную команду."


def test_dashboard_state_lines_translate_backend_state_for_operator():
    state = DashboardState(
        db_status="connected",
        db_error=None,
        db_path="C:/quik_export/cnyrub_tom_orderbook.sqlite",
        snapshot_count=12500,
        latest_snapshot_id=12500,
        latest_snapshot_ts="2026-06-03T10:00:00+00:00",
        last_snapshot_age_sec=0.4,
        quik_status="active",
        quik_path="C:/quik_export/cnyrub_tom_orderbook.json",
        quik_age_sec=0.2,
        secid="CNYRUB_TOM",
        best_bid=12.34,
        best_ask=12.35,
        spread=0.01,
        mid=12.345,
        bid_qty=9000,
        ask_qty=3000,
        imbalance=0.5,
        advantage="buyer",
        pattern="buyer_accumulation",
        confidence=0.72,
        explanation=["bid depth выше ask depth", "цена стоит в узком диапазоне"],
    )

    lines = dashboard_state_lines(state)

    assert lines["db"].startswith("База: подключена")
    assert "12 500" in lines["db"]
    assert lines["quik"].startswith("QUIK: активен")
    assert lines["advantage"] == "Преимущество: покупатель"
    assert lines["pattern"] == "Момент: набор позиции покупателем · 72%"
    assert "Imbalance: +0.500" in lines["metrics"]


def test_build_cli_command_for_orderbook_includes_quik_file_levels_and_depth():
    command = build_cli_command(
        "orderbook",
        secid="CNYRUB_TOM",
        orderbook_path="C:\\quik_export\\cnyrub_tom_orderbook.json",
        levels=10,
        depth=20,
    )

    assert command == [
        "cnyrub",
        "--secid",
        "CNYRUB_TOM",
        "orderbook",
        "--orderbook-path",
        "C:\\quik_export\\cnyrub_tom_orderbook.json",
        "--levels",
        "10",
        "--depth",
        "20",
    ]


def test_build_cli_command_for_record_orderbook_omits_empty_limits():
    command = build_cli_command(
        "record-orderbook",
        orderbook_path="C:\\quik_export\\cnyrub_tom_orderbook.json",
        db_path="C:\\quik_export\\cnyrub_tom_orderbook.sqlite",
        interval=0.25,
        count=None,
        seconds=None,
    )

    assert "--count" not in command
    assert "--seconds" not in command
    assert command_to_text(command) == 'cnyrub record-orderbook --orderbook-path C:\\quik_export\\cnyrub_tom_orderbook.json --db C:\\quik_export\\cnyrub_tom_orderbook.sqlite --interval 0.25'


def test_build_cli_command_for_analyze_trades_supports_csv_output():
    command = build_cli_command(
        "analyze-trades",
        from_date="2026-06-03",
        till="2026-06-03",
        limit=1000,
        output="data/trades_analysis.csv",
    )

    assert command == [
        "cnyrub",
        "analyze-trades",
        "--from",
        "2026-06-03",
        "--till",
        "2026-06-03",
        "--limit",
        "1000",
        "--output",
        "data/trades_analysis.csv",
    ]


def test_build_cli_command_for_detect_accumulation():
    command = build_cli_command(
        "detect-accumulation",
        db_path="C:\\quik_export\\cnyrub_tom_orderbook.sqlite",
        output="C:\\quik_export\\accumulation_zones.csv",
        levels=10,
        window=20,
        max_mid_range=0.002,
        min_total_depth=1000,
    )

    assert command == [
        "cnyrub",
        "detect-accumulation",
        "--db",
        "C:\\quik_export\\cnyrub_tom_orderbook.sqlite",
        "--levels",
        "10",
        "--window",
        "20",
        "--max-mid-range",
        "0.002",
        "--min-total-depth",
        "1000",
        "--output",
        "C:\\quik_export\\accumulation_zones.csv",
    ]


def test_build_cli_command_for_record_trades_live_csv():
    command = build_cli_command(
        "record-trades",
        output="C:\\quik_export\\cnyrub_tom_trades.csv",
        limit=1000,
        interval=0.001,
        count=None,
        seconds=None,
    )

    assert command == [
        "cnyrub",
        "record-trades",
        "--limit",
        "1000",
        "--output",
        "C:\\quik_export\\cnyrub_tom_trades.csv",
        "--interval",
        "0.001",
    ]


def test_build_cli_command_for_cumulative_delta_volume_profile_and_alerts():
    common = {"trades_csv": "C:\\quik_export\\cnyrub_tom_trades.csv", "price_step": "0.001"}

    cumulative = build_cli_command("cumulative-delta", **common, bucket_minutes=3, output="C:\\quik_export\\cum.csv")
    profile = build_cli_command("volume-profile", **common, output="C:\\quik_export\\vp.csv")
    alerts = build_cli_command("trade-alerts", **common, bucket_minutes=3, min_abs_delta=100, min_volume=150, output="C:\\quik_export\\alerts.csv")

    assert cumulative == [
        "cnyrub", "cumulative-delta", "--trades-csv", "C:\\quik_export\\cnyrub_tom_trades.csv", "--bucket-minutes", "3", "--price-step", "0.001", "--output", "C:\\quik_export\\cum.csv",
    ]
    assert profile == [
        "cnyrub", "volume-profile", "--trades-csv", "C:\\quik_export\\cnyrub_tom_trades.csv", "--price-step", "0.001", "--output", "C:\\quik_export\\vp.csv",
    ]
    assert alerts == [
        "cnyrub", "trade-alerts", "--trades-csv", "C:\\quik_export\\cnyrub_tom_trades.csv", "--bucket-minutes", "3", "--price-step", "0.001", "--min-abs-delta", "100", "--min-volume", "150", "--output", "C:\\quik_export\\alerts.csv",
    ]


def test_build_cli_command_for_cluster_delta_uses_three_minute_default_chart():
    command = build_cli_command(
        "cluster-delta",
        trades_csv="C:\\quik_export\\cnyrub_tom_trades.csv",
        bucket_minutes=3,
        price_step="0.001",
        output="C:\\quik_export\\cnyrub_tom_cluster_delta_3m.csv",
    )

    assert command == [
        "cnyrub",
        "cluster-delta",
        "--trades-csv",
        "C:\\quik_export\\cnyrub_tom_trades.csv",
        "--bucket-minutes",
        "3",
        "--price-step",
        "0.001",
        "--output",
        "C:\\quik_export\\cnyrub_tom_cluster_delta_3m.csv",
    ]


def test_build_cli_command_for_detect_liquidity_events():
    command = build_cli_command(
        "detect-liquidity-events",
        db_path="C:\\quik_export\\cnyrub_tom_orderbook.sqlite",
        trades_csv="C:\\quik_export\\cnyrub_tom_trades.csv",
        output="C:\\quik_export\\liquidity_events.csv",
        window_seconds=20,
        min_trade_qty=150,
        min_recovery_ratio=0.8,
        iceberg_trade_to_visible_ratio=1.5,
    )

    assert command == [
        "cnyrub",
        "detect-liquidity-events",
        "--db",
        "C:\\quik_export\\cnyrub_tom_orderbook.sqlite",
        "--trades-csv",
        "C:\\quik_export\\cnyrub_tom_trades.csv",
        "--window-seconds",
        "20",
        "--min-trade-qty",
        "150",
        "--min-recovery-ratio",
        "0.8",
        "--iceberg-trade-to-visible-ratio",
        "1.5",
        "--output",
        "C:\\quik_export\\liquidity_events.csv",
    ]
