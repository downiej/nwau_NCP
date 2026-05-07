"""Process-wide singleton holding the parsed price-weight tables.

Loaded once at cold start so MCP tool calls only hit dictionary lookups.
The data layer (loader.py + this file) stays decoupled from the MCP layer
so that swapping in next year's xlsx is a one-file change.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from .config import Settings, load_settings
from .loader import PriceWeightTables, load_price_weights


log = logging.getLogger(__name__)

_lock = threading.Lock()
_tables: PriceWeightTables | None = None
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def get_tables() -> PriceWeightTables:
    global _tables
    if _tables is None:
        with _lock:
            if _tables is None:
                settings = get_settings()
                log.info(
                    "Loading NEP %s price weights from %s",
                    settings.determination_year,
                    settings.price_weights_path,
                )
                _tables = load_price_weights(settings.price_weights_path)
                log.info(
                    "Loaded acute=%d subacute=%d mh_adm=%d mh_com=%d "
                    "non_adm=%d aecc=%d udg=%d",
                    len(_tables.acute),
                    len(_tables.subacute),
                    len(_tables.mh_admitted),
                    len(_tables.mh_community),
                    len(_tables.non_admitted),
                    len(_tables.aecc),
                    len(_tables.udg),
                )
    return _tables


def reload_tables(xlsx_path: Path | str | None = None) -> PriceWeightTables:
    """Force a reload — useful when swapping in a new annual xlsx without restart."""
    global _tables, _settings
    with _lock:
        if xlsx_path is not None:
            _settings = Settings(
                nep_price=get_settings().nep_price,
                price_weights_path=Path(xlsx_path),
                api_key=get_settings().api_key,
                determination_year=get_settings().determination_year,
            )
        _tables = load_price_weights(get_settings().price_weights_path)
        return _tables
