"""Detect new splits/dividends and flag affected contracts (manual FR-018)."""
from __future__ import annotations

import datetime as dt
import logging

from ..ingest.base import Provider
from ..storage import repo

logger = logging.getLogger(__name__)


def detect_and_flag(con, provider: Provider, symbol: str, lookback_days: int = 30) -> list[dict]:
    """Fetch recent splits/dividends for `symbol`, record any not already
    seen in `corporate_actions`, and for a new split, flag existing
    option_contracts rows (expiry on/after the split) as `is_adjusted` so
    Greeks/IV consumers know their cached strikes may be stale (sec 4.2:
    'flag adjusted contracts to avoid mispriced Greeks'). Dividends are
    recorded but don't currently adjust pricing (BSM here is undiscounted
    for dividends -- a documented simplification, not a silent gap)."""
    actions_df = provider.fetch_corporate_actions(symbol)
    if actions_df.empty:
        return []

    cutoff = dt.date.today() - dt.timedelta(days=lookback_days)
    recent = actions_df[actions_df["date"] >= cutoff]

    newly_detected = []
    for row in recent.to_dict("records"):
        if repo.corporate_action_exists(con, symbol, row["date"], row["action_type"]):
            continue

        repo.insert_corporate_action(con, symbol, row["date"], row["action_type"], row["value"])
        newly_detected.append(row)

        if row["action_type"] == "split":
            n_flagged = repo.flag_contracts_adjusted(con, symbol, row["date"])
            logger.warning(
                "%s: new %sx split detected on %s -- flagged %d existing contract(s) as adjusted",
                symbol, row["value"], row["date"], n_flagged,
            )

    return newly_detected
