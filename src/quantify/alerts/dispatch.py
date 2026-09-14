"""Wires the scanner's unusual-activity rule to alert channels (manual
FR-008), with dedup so the same contract doesn't re-alert every refresh."""
from __future__ import annotations

import datetime as dt
import logging

from ..config import QuantifyConfig
from ..scanner.rules import unusual_activity
from ..storage import repo
from .channels import build_notifiers

logger = logging.getLogger(__name__)


def format_alert_message(symbol: str, row: dict) -> str:
    return (
        f"{symbol} ${row['strike']:g} {('CALL' if row['right'] == 'C' else 'PUT')} "
        f"exp {row['expiry']}: Vol {row['volume']:,} vs OI {row['open_interest']:,} "
        f"({row['vol_oi_ratio']:.1f}x), mid ${row['mid']:.2f}"
    )


def check_and_alert(con, config: QuantifyConfig, symbol: str) -> list[dict]:
    """Run the unusual-activity rule for `symbol`'s latest chain snapshot and
    alert on any new (undeduped) hits. Returns a list of dispatch records
    (empty if alerting is disabled or nothing new fired)."""
    if not config.alerts.enabled or not config.alerts.channels:
        return []

    chain_df = repo.latest_chain(con, symbol)
    if chain_df.is_empty():
        return []

    flagged = unusual_activity(chain_df, config.scanner.vol_oi_multiple, config.scanner.min_volume)
    if flagged.is_empty():
        return []

    notifiers = build_notifiers(config.alerts.channels)
    if not notifiers:
        return []

    now = dt.datetime.now()
    since = now - dt.timedelta(hours=config.alerts.dedup_hours)
    dispatched = []

    for row in flagged.to_dicts():
        contract_id = row["contract_id"]
        if repo.signal_exists_since(con, symbol, "unusual_activity", contract_id, since):
            continue

        payload = {
            "contract_id": contract_id, "strike": row["strike"], "right": row["right"],
            "expiry": str(row["expiry"]), "volume": row["volume"],
            "open_interest": row["open_interest"], "vol_oi_ratio": row["vol_oi_ratio"],
        }
        signal_id = repo.insert_signal(con, now, symbol, "unusual_activity", row["vol_oi_ratio"], payload)
        message = format_alert_message(symbol, row)

        for notifier in notifiers:
            ok = notifier.send(message)
            repo.insert_alert(con, signal_id, notifier.name, dt.datetime.now(), "sent" if ok else "failed")
            dispatched.append({"signal_id": signal_id, "channel": notifier.name, "ok": ok, "message": message})

    return dispatched
