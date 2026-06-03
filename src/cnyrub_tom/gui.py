from __future__ import annotations

import queue
import shlex
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_SECID = "CNYRUB_TOM"


@dataclass(frozen=True)
class DefaultPaths:
    orderbook_path: str
    db_path: str
    analysis_csv: str
    accumulation_csv: str
    trades_csv: str
    trades_analysis_csv: str
    orderbook_jsonl: str


def default_paths() -> DefaultPaths:
    base = Path("C:/quik_export")
    return DefaultPaths(
        orderbook_path=str(base / "cnyrub_tom_orderbook.json"),
        db_path=str(base / "cnyrub_tom_orderbook.sqlite"),
        analysis_csv=str(base / "cnyrub_tom_analysis.csv"),
        accumulation_csv=str(base / "cnyrub_tom_accumulation_zones.csv"),
        trades_csv=str(base / "cnyrub_tom_trades.csv"),
        trades_analysis_csv=str(base / "cnyrub_tom_trades_analysis.csv"),
        orderbook_jsonl=str(base / "cnyrub_tom_orderbook.jsonl"),
    )


def _append_option(command: list[str], option: str, value: Any) -> None:
    if value is None or value == "":
        return
    command.extend([option, str(value)])


def build_cli_command(action: str, **options: Any) -> list[str]:
    command = ["cnyrub"]
    secid = options.get("secid")
    if secid and secid != DEFAULT_SECID:
        command.extend(["--secid", str(secid)])
    elif secid == DEFAULT_SECID and action == "orderbook":
        # Keep the primary orderbook command explicit for copy/paste clarity.
        command.extend(["--secid", str(secid)])

    command.append(action)

    if action == "quote":
        return command
    if action == "candles":
        _append_option(command, "--from", options.get("from_date"))
        _append_option(command, "--till", options.get("till"))
        _append_option(command, "--interval", options.get("interval"))
        _append_option(command, "--output", options.get("output"))
    elif action in {"trades", "analyze-trades"}:
        _append_option(command, "--from", options.get("from_date"))
        _append_option(command, "--till", options.get("till"))
        _append_option(command, "--limit", options.get("limit"))
        _append_option(command, "--output", options.get("output"))
    elif action == "orderbook":
        _append_option(command, "--orderbook-path", options.get("orderbook_path"))
        _append_option(command, "--orderbook-url", options.get("orderbook_url"))
        _append_option(command, "--levels", options.get("levels"))
        _append_option(command, "--depth", options.get("depth"))
    elif action == "record-orderbook":
        _append_option(command, "--orderbook-path", options.get("orderbook_path"))
        _append_option(command, "--orderbook-url", options.get("orderbook_url"))
        _append_option(command, "--db", options.get("db_path"))
        _append_option(command, "--interval", options.get("interval"))
        _append_option(command, "--count", options.get("count"))
        _append_option(command, "--seconds", options.get("seconds"))
    elif action in {"analyze-orderbook", "export-orderbook"}:
        _append_option(command, "--db", options.get("db_path"))
        if action == "analyze-orderbook":
            _append_option(command, "--levels", options.get("levels"))
        _append_option(command, "--output", options.get("output"))
    elif action == "detect-accumulation":
        _append_option(command, "--db", options.get("db_path"))
        _append_option(command, "--levels", options.get("levels"))
        _append_option(command, "--window", options.get("window"))
        _append_option(command, "--max-mid-range", options.get("max_mid_range"))
        _append_option(command, "--min-total-depth", options.get("min_total_depth"))
        _append_option(command, "--output", options.get("output"))
    else:
        raise ValueError(f"unknown action: {action}")
    return command


def command_to_text(command: list[str]) -> str:
    parts = []
    for part in command:
        if any(char.isspace() for char in part):
            parts.append(shlex.quote(part))
        else:
            parts.append(part)
    return " ".join(parts)


class CnyrubGui:
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = tk.Tk()
        self.root.title("CNYRUB_TOM Analytics Tool")
        self.root.geometry("1040x760")
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None
        self.fields: dict[str, tk.StringVar] = {}
        self._build_ui()
        self.root.after(100, self._drain_output_queue)

    def _var(self, name: str, value: str = ""):
        var = self.tk.StringVar(value=value)
        self.fields[name] = var
        return var

    def _add_row(self, parent, row: int, label: str, name: str, value: str = "", width: int = 54):
        self.ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
        entry = self.ttk.Entry(parent, textvariable=self._var(name, value), width=width)
        entry.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
        parent.columnconfigure(1, weight=1)
        return entry

    def _build_ui(self) -> None:
        paths = default_paths()
        ttk = self.ttk
        tk = self.tk

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        header = ttk.Frame(main)
        header.pack(fill="x")
        ttk.Label(header, text="CNYRUB_TOM Analytics Tool", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(header, text="Проверить котировку", command=lambda: self.run_action("quote")).pack(side="right", padx=4)

        settings = ttk.LabelFrame(main, text="Основные настройки", padding=8)
        settings.pack(fill="x", pady=8)
        self._add_row(settings, 0, "SECID", "secid", DEFAULT_SECID)
        self._add_row(settings, 1, "QUIK JSON стакана", "orderbook_path", paths.orderbook_path)
        self._add_row(settings, 2, "SQLite база стакана", "db_path", paths.db_path)

        tabs = ttk.Notebook(main)
        tabs.pack(fill="x", pady=8)

        orderbook_tab = ttk.Frame(tabs, padding=8)
        tabs.add(orderbook_tab, text="Стакан / QUIK")
        self._add_row(orderbook_tab, 0, "Уровней для анализа", "levels", "10", width=16)
        self._add_row(orderbook_tab, 1, "Глубина вывода", "depth", "20", width=16)
        self._add_row(orderbook_tab, 2, "Интервал записи, сек", "record_interval", "0.25", width=16)
        self._add_row(orderbook_tab, 3, "Ограничить временем, сек", "record_seconds", "", width=16)
        self._add_row(orderbook_tab, 4, "Ограничить количеством", "record_count", "", width=16)
        self._add_row(orderbook_tab, 5, "Окно накопления, снимков", "accumulation_window", "20", width=16)
        self._add_row(orderbook_tab, 6, "Макс. диапазон mid", "max_mid_range", "0.002", width=16)
        self._add_row(orderbook_tab, 7, "Мин. глубина bid+ask", "min_total_depth", "1000", width=16)
        buttons = ttk.Frame(orderbook_tab)
        buttons.grid(row=8, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Button(buttons, text="Показать стакан", command=lambda: self.run_action("orderbook")).pack(side="left", padx=3)
        ttk.Button(buttons, text="Начать запись", command=lambda: self.run_action("record-orderbook")).pack(side="left", padx=3)
        ttk.Button(buttons, text="Остановить запись", command=self.stop_process).pack(side="left", padx=3)
        ttk.Button(buttons, text="Анализ стакана CSV", command=lambda: self.run_action("analyze-orderbook")).pack(side="left", padx=3)
        ttk.Button(buttons, text="Накопление CSV", command=lambda: self.run_action("detect-accumulation")).pack(side="left", padx=3)
        ttk.Button(buttons, text="Экспорт JSONL", command=lambda: self.run_action("export-orderbook")).pack(side="left", padx=3)

        trades_tab = ttk.Frame(tabs, padding=8)
        tabs.add(trades_tab, text="Сделки MOEX")
        self._add_row(trades_tab, 0, "Дата с", "from_date", "", width=16)
        self._add_row(trades_tab, 1, "Дата по", "till", "", width=16)
        self._add_row(trades_tab, 2, "Лимит сделок", "trades_limit", "1000", width=16)
        self._add_row(trades_tab, 3, "CSV сделок", "trades_csv", paths.trades_csv)
        self._add_row(trades_tab, 4, "CSV анализа сделок", "trades_analysis_csv", paths.trades_analysis_csv)
        trade_buttons = ttk.Frame(trades_tab)
        trade_buttons.grid(row=5, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Button(trade_buttons, text="Показать сделки", command=lambda: self.run_action("trades-preview")).pack(side="left", padx=3)
        ttk.Button(trade_buttons, text="Сохранить сделки CSV", command=lambda: self.run_action("trades")).pack(side="left", padx=3)
        ttk.Button(trade_buttons, text="Показать анализ", command=lambda: self.run_action("analyze-trades-preview")).pack(side="left", padx=3)
        ttk.Button(trade_buttons, text="Сохранить анализ CSV", command=lambda: self.run_action("analyze-trades")).pack(side="left", padx=3)

        candles_tab = ttk.Frame(tabs, padding=8)
        tabs.add(candles_tab, text="Свечи")
        self._add_row(candles_tab, 0, "Дата с", "candles_from", "", width=16)
        self._add_row(candles_tab, 1, "Дата по", "candles_till", "", width=16)
        self._add_row(candles_tab, 2, "Интервал MOEX", "candles_interval", "60", width=16)
        self._add_row(candles_tab, 3, "CSV свечей", "candles_csv", "data/candles.csv")
        ttk.Button(candles_tab, text="Скачать свечи CSV", command=lambda: self.run_action("candles")).grid(row=4, column=0, sticky="w", padx=6, pady=8)

        command_frame = ttk.LabelFrame(main, text="Команда", padding=8)
        command_frame.pack(fill="x", pady=8)
        self.command_var = tk.StringVar()
        ttk.Entry(command_frame, textvariable=self.command_var).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(command_frame, text="Скопировать", command=self.copy_command).pack(side="right", padx=4)

        output_frame = ttk.LabelFrame(main, text="Вывод", padding=8)
        output_frame.pack(fill="both", expand=True)
        self.output = tk.Text(output_frame, wrap="word", height=18)
        self.output.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(output_frame, orient="vertical", command=self.output.yview)
        scrollbar.pack(side="right", fill="y")
        self.output.configure(yscrollcommand=scrollbar.set)

    def _get(self, name: str) -> str:
        return self.fields[name].get().strip()

    def _command_for_action(self, action: str) -> list[str]:
        common = {"secid": self._get("secid")}
        if action == "quote":
            return build_cli_command("quote", **common)
        if action == "orderbook":
            return build_cli_command(
                "orderbook", **common, orderbook_path=self._get("orderbook_path"), levels=self._get("levels"), depth=self._get("depth"),
            )
        if action == "record-orderbook":
            return build_cli_command(
                "record-orderbook", **common, orderbook_path=self._get("orderbook_path"), db_path=self._get("db_path"),
                interval=self._get("record_interval"), seconds=self._get("record_seconds"), count=self._get("record_count"),
            )
        if action == "analyze-orderbook":
            return build_cli_command("analyze-orderbook", **common, db_path=self._get("db_path"), levels=self._get("levels"), output=default_paths().analysis_csv)
        if action == "detect-accumulation":
            return build_cli_command(
                "detect-accumulation", **common, db_path=self._get("db_path"), levels=self._get("levels"),
                window=self._get("accumulation_window"), max_mid_range=self._get("max_mid_range"),
                min_total_depth=self._get("min_total_depth"), output=default_paths().accumulation_csv,
            )
        if action == "export-orderbook":
            return build_cli_command("export-orderbook", **common, db_path=self._get("db_path"), output=default_paths().orderbook_jsonl)
        if action in {"trades", "trades-preview"}:
            return build_cli_command(
                "trades", **common, from_date=self._get("from_date"), till=self._get("till"), limit=self._get("trades_limit"),
                output="" if action.endswith("preview") else self._get("trades_csv"),
            )
        if action in {"analyze-trades", "analyze-trades-preview"}:
            return build_cli_command(
                "analyze-trades", **common, from_date=self._get("from_date"), till=self._get("till"), limit=self._get("trades_limit"),
                output="" if action.endswith("preview") else self._get("trades_analysis_csv"),
            )
        if action == "candles":
            return build_cli_command(
                "candles", **common, from_date=self._get("candles_from"), till=self._get("candles_till"),
                interval=self._get("candles_interval"), output=self._get("candles_csv"),
            )
        raise ValueError(action)

    def run_action(self, action: str) -> None:
        if self.process and self.process.poll() is None:
            self._append_output("\nУже выполняется команда. Остановите её или дождитесь завершения.\n")
            return
        command = self._command_for_action(action)
        self.command_var.set(command_to_text(command))
        self._append_output(f"\n$ {command_to_text(command)}\n")
        thread = threading.Thread(target=self._run_subprocess, args=(command,), daemon=True)
        thread.start()

    def _run_subprocess(self, command: list[str]) -> None:
        try:
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self.output_queue.put(line)
            code = self.process.wait()
            self.output_queue.put(f"\n[exit code: {code}]\n")
        except Exception as exc:  # GUI should show errors instead of crashing.
            self.output_queue.put(f"\n[error] {exc}\n")
        finally:
            self.process = None

    def stop_process(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self._append_output("\n[requested stop]\n")

    def copy_command(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.command_var.get())
        self._append_output("\n[command copied]\n")

    def _append_output(self, text: str) -> None:
        self.output.insert("end", text)
        self.output.see("end")

    def _drain_output_queue(self) -> None:
        while True:
            try:
                self._append_output(self.output_queue.get_nowait())
            except queue.Empty:
                break
        self.root.after(100, self._drain_output_queue)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    app = CnyrubGui()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
