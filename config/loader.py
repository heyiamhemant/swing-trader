import json
import yaml
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent
DATA_DIR = CONFIG_DIR.parent / "data"
CONFIG_JSON = DATA_DIR / "config.json"

_config: dict | None = None
_watchlist: dict | None = None
_etf_tickers: set[str] | None = None

CONFIG_JSON_DEFAULTS = {
    "capital": 1000,
    "max_positions": 10,
    "max_sector_exposure": 3,
    "brokerage_fee_pct": 0.25,
}


def get_config() -> dict:
    global _config
    if _config is None:
        with open(CONFIG_DIR / "strategy_params.yaml") as f:
            _config = yaml.safe_load(f)
        _apply_json_overrides(_config)
    return _config


def _apply_json_overrides(cfg: dict):
    """Overlay values from data/config.json onto the YAML config."""
    overrides = get_user_config()
    cap = cfg.setdefault("capital", {})
    if "capital" in overrides:
        cap["total"] = overrides["capital"]
    if "max_positions" in overrides:
        cap["max_positions"] = overrides["max_positions"]
    if "max_sector_exposure" in overrides:
        cap["max_sector_exposure"] = overrides["max_sector_exposure"]


def get_user_config() -> dict:
    """Read the user-editable config.json, returning defaults if absent."""
    if CONFIG_JSON.exists():
        try:
            return json.loads(CONFIG_JSON.read_text())
        except (json.JSONDecodeError, ValueError):
            pass
    return dict(CONFIG_JSON_DEFAULTS)


def save_user_config(updates: dict):
    """Merge updates into config.json and write to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    current = get_user_config()
    current.update(updates)
    CONFIG_JSON.write_text(json.dumps(current, indent=2), encoding="utf-8")
    reload_config()


def get_watchlist_raw() -> dict:
    global _watchlist
    if _watchlist is None:
        with open(CONFIG_DIR / "watchlist.yaml") as f:
            _watchlist = yaml.safe_load(f)
    return _watchlist


def get_etf_tickers() -> set[str]:
    """Return the set of tickers listed under the 'etfs' key in watchlist.yaml."""
    global _etf_tickers
    if _etf_tickers is None:
        raw = get_watchlist_raw()
        _etf_tickers = set()
        for group_tickers in raw.get("etfs", {}).values():
            _etf_tickers.update(group_tickers)
    return _etf_tickers


def reload_config() -> dict:
    """Force re-read from disk. Useful for tests."""
    global _config, _watchlist, _etf_tickers
    _config = None
    _watchlist = None
    _etf_tickers = None
    return get_config()
