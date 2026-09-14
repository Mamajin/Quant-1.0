"""Watchlist add/remove tests (manual FR-002), using a scratch config.toml
copy so the real config/config.toml is never touched."""
import shutil

import pytest

from quantify.config import add_watchlist_symbol, load_config, remove_watchlist_symbol
from quantify.config import DEFAULT_CONFIG_PATH


@pytest.fixture()
def scratch_config(tmp_path):
    dest = tmp_path / "config.toml"
    shutil.copy(DEFAULT_CONFIG_PATH, dest)
    return dest


def test_add_watchlist_symbol_appends_and_persists(scratch_config):
    original = load_config(scratch_config)
    assert "MSFT" not in original.watchlist.symbols

    updated = add_watchlist_symbol("msft", path=scratch_config)
    assert "MSFT" in updated.watchlist.symbols

    reloaded = load_config(scratch_config)
    assert "MSFT" in reloaded.watchlist.symbols


def test_add_watchlist_symbol_is_idempotent(scratch_config):
    add_watchlist_symbol("MSFT", path=scratch_config)
    before = load_config(scratch_config).watchlist.symbols
    add_watchlist_symbol("MSFT", path=scratch_config)
    after = load_config(scratch_config).watchlist.symbols
    assert before == after
    assert after.count("MSFT") == 1


def test_add_watchlist_symbol_enforces_cap(scratch_config):
    config = load_config(scratch_config)
    # Fill up to the cap first
    for i in range(config.watchlist.max_symbols - len(config.watchlist.symbols)):
        add_watchlist_symbol(f"SYM{i}", path=scratch_config)
    with pytest.raises(ValueError):
        add_watchlist_symbol("ONE_TOO_MANY", path=scratch_config)


def test_remove_watchlist_symbol_persists(scratch_config):
    original = load_config(scratch_config)
    target = original.watchlist.symbols[0]

    updated = remove_watchlist_symbol(target, path=scratch_config)
    assert target not in updated.watchlist.symbols

    reloaded = load_config(scratch_config)
    assert target not in reloaded.watchlist.symbols


def test_remove_nonexistent_symbol_is_a_noop(scratch_config):
    before = load_config(scratch_config).watchlist.symbols
    remove_watchlist_symbol("NOPE_NOT_THERE", path=scratch_config)
    after = load_config(scratch_config).watchlist.symbols
    assert before == after


def test_add_then_remove_round_trips_other_config_untouched(scratch_config):
    before = load_config(scratch_config)
    add_watchlist_symbol("MSFT", path=scratch_config)
    remove_watchlist_symbol("MSFT", path=scratch_config)
    after = load_config(scratch_config)
    assert after.scanner == before.scanner
    assert after.greeks == before.greeks
    assert after.watchlist.symbols == before.watchlist.symbols
