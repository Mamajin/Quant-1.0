"""Position + journal management (manual FR-010). Paper trading only --
there's no broker execution here (Phase 4 per the manual's roadmap); this
just records what you *say* you did, with why, so you can review it later."""
from __future__ import annotations

import datetime as dt

from ..storage import repo

OPTION_MULTIPLIER = 100
SHARE_MULTIPLIER = 1


def open_position(con, symbol: str, qty: float, entry_price: float,
                   contract_id: str | None = None, reason_entry: str | None = None,
                   tags: str | None = None, notes: str | None = None,
                   entry_ts: dt.datetime | None = None) -> int:
    """Log a new paper position. `contract_id` set = option (qty in
    contracts, $100 multiplier); None = shares (multiplier 1)."""
    entry_ts = entry_ts or dt.datetime.now()
    position_id = repo.insert_position(con, symbol, contract_id, qty, entry_price, entry_ts)
    repo.insert_journal_entry(con, position_id, reason_entry, tags, notes)
    return position_id


def close_position(con, position_id: int, exit_price: float,
                    reason_exit: str | None = None, exit_ts: dt.datetime | None = None) -> float:
    """Close a paper position and record realized P&L. Returns the P&L."""
    position = repo.position_by_id(con, position_id)
    if position is None:
        raise ValueError(f"No position with id={position_id}")
    if position["exit_ts"] is not None:
        raise ValueError(f"Position {position_id} is already closed")

    multiplier = OPTION_MULTIPLIER if position["contract_id"] else SHARE_MULTIPLIER
    pnl = (exit_price - position["entry_price"]) * position["qty"] * multiplier

    exit_ts = exit_ts or dt.datetime.now()
    repo.close_position(con, position_id, exit_price, exit_ts, pnl)
    if reason_exit is not None:
        repo.update_journal_exit_reason(con, position_id, reason_exit)
    return pnl


def journal_stats(con) -> dict:
    """Win rate / expectancy / profit factor across all closed paper trades
    (manual sec 3.7 formulas, same definitions used by the backtester)."""
    closed = repo.closed_positions(con, limit=100_000)
    if closed.is_empty():
        return {"n_closed": 0, "total_pnl": 0.0, "win_rate": 0.0,
                "profit_factor": 0.0, "expectancy": 0.0, "avg_win": 0.0, "avg_loss": 0.0}

    pnls = closed["pnl"].to_list()
    wins = [p for p in pnls if p is not None and p > 0]
    losses = [p for p in pnls if p is not None and p <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    n = len(wins) + len(losses)
    win_rate = len(wins) / n if n else 0.0
    avg_win = gross_profit / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss

    return {
        "n_closed": n,
        "total_pnl": sum(wins) + sum(losses),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }
