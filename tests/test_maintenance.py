"""Maintenance task tests (manual sec 4.3 'Vacuum/compact DuckDB', sec 4.10
'scan dependencies for vulnerabilities (pip-audit)')."""
import subprocess
import sys

import duckdb
import pytest

from quantify.config import StorageConfig
from quantify.maintenance.tasks import database_size_bytes, run_pip_audit, vacuum_database
from quantify.storage.db import SCHEMA_DDL, connect


def test_vacuum_database_runs_without_error_on_populated_db(tmp_path):
    storage = StorageConfig(db_path=str(tmp_path / "t.duckdb"), parquet_dir=str(tmp_path / "parquet"))
    con = connect(storage)
    con.execute("INSERT INTO symbols (symbol, name, type) VALUES ('AAPL', 'Apple', 'stock')")
    vacuum_database(con)  # should not raise
    row = con.execute("SELECT symbol FROM symbols").fetchone()
    assert row[0] == "AAPL"
    con.close()


def test_vacuum_database_runs_on_empty_db(tmp_path):
    storage = StorageConfig(db_path=str(tmp_path / "empty.duckdb"), parquet_dir=str(tmp_path / "parquet"))
    con = connect(storage)
    vacuum_database(con)  # should not raise even with no data
    con.close()


def test_database_size_bytes_zero_when_missing(tmp_path):
    storage = StorageConfig(db_path=str(tmp_path / "does_not_exist.duckdb"), parquet_dir=str(tmp_path / "parquet"))
    assert database_size_bytes(storage) == 0


def test_database_size_bytes_positive_after_creation(tmp_path):
    storage = StorageConfig(db_path=str(tmp_path / "t.duckdb"), parquet_dir=str(tmp_path / "parquet"))
    con = connect(storage)
    con.close()
    assert database_size_bytes(storage) > 0


def test_run_pip_audit_invokes_module_and_returns_completed_process(monkeypatch):
    captured = {}

    def fake_run(cmd, check, capture_output, text):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="No known vulnerabilities found", stderr="")

    monkeypatch.setattr("quantify.maintenance.tasks.subprocess.run", fake_run)
    result = run_pip_audit()

    assert captured["cmd"] == [sys.executable, "-m", "pip_audit"]
    assert result.returncode == 0
    assert "No known vulnerabilities" in result.stdout


def test_run_pip_audit_passes_extra_args(monkeypatch):
    captured = {}

    def fake_run(cmd, check, capture_output, text):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="vuln found")

    monkeypatch.setattr("quantify.maintenance.tasks.subprocess.run", fake_run)
    result = run_pip_audit(extra_args=["--format", "json"])

    assert captured["cmd"] == [sys.executable, "-m", "pip_audit", "--format", "json"]
    assert result.returncode == 1
