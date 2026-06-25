"""akshare utility functions: symbol normalisation, retry, OHLCV load & cache."""

from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime
from typing import Tuple

import akshare as ak
import pandas as pd

from .config import get_config
from .symbol_utils import NoMarketDataError
from .utils import safe_ticker_component

logger = logging.getLogger(__name__)

MAX_OHLCV_STALE_DAYS = 10

# ---------------------------------------------------------------------------
# Symbol normalisation for akshare
# ---------------------------------------------------------------------------

def _classify_market(raw: str) -> Tuple[str, str]:
    """Return ``(market, clean_code)`` for the given symbol.

    ``market`` is one of ``"sh"``, ``"sz"``, ``"hk"``, ``"us"``, or
    ``"unknown"``.  ``clean_code`` is the bare ticker that akshare APIs expect.
    """
    s = raw.strip().upper()

    for suffix, market in [(".SS", "sh"), (".SH", "sh"), (".SZ", "sz"), (".HK", "hk")]:
        if s.endswith(suffix):
            code = s[: -len(suffix)]
            if market == "hk":
                code = code.zfill(5)
            return market, code

    if s.isdigit():
        if len(s) == 5:
            return "hk", s
        if len(s) == 6:
            return ("sh" if s.startswith(("6", "9")) else "sz"), s

    return "us", s


def _parse_akshare_date(date_str: str) -> str:
    """Convert ``YYYY-MM-DD`` to akshare compact ``YYYYMMDD``."""
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------

def ak_retry(func, max_retries: int = 3, base_delay: float = 2.0):
    """Execute ``func`` with exponential back-off on any exception."""
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "akshare call failed, retrying in %.0fs (attempt %d/%d)",
                    delay,
                    attempt + 1,
                    max_retries,
                )
                time.sleep(delay)
            else:
                raise


# ---------------------------------------------------------------------------
# DataFrame helpers (same contract as stockstats_utils)
# ---------------------------------------------------------------------------

def _ensure_date_column(data: pd.DataFrame) -> pd.DataFrame:
    """Rename the first date-like column to ``Date``."""
    if "Date" in data.columns:
        return data
    for cand in ("index", "Datetime", "date", "\u65e5\u671f"):
        if cand in data.columns:
            return data.rename(columns={cand: "Date"})
    return data


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Parse dates, drop invalid rows, forward-fill price gaps."""
    data = _ensure_date_column(data)
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"])
    price_cols = [
        c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns
    ]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=["Close"])
    data[price_cols] = data[price_cols].ffill().bfill()
    return data


def _coerce_ohlcv_dates(data: pd.DataFrame) -> pd.Series:
    """Return parsed dates from an OHLCV frame."""
    if "Date" in data.columns:
        return pd.to_datetime(data["Date"], errors="coerce").dropna()
    if isinstance(data.index, pd.DatetimeIndex):
        return pd.Series(pd.to_datetime(data.index, errors="coerce")).dropna()
    df = data.reset_index()
    for col in ("Date", "Datetime", "date", "index"):
        if col in df.columns:
            parsed = pd.to_datetime(df[col], errors="coerce").dropna()
            if not parsed.empty:
                return parsed
    return pd.Series(dtype="datetime64[ns]")


def _assert_ohlcv_not_stale(
    data: pd.DataFrame,
    curr_date: str,
    symbol: str,
    canonical: str | None = None,
    *,
    max_stale_days: int = MAX_OHLCV_STALE_DAYS,
) -> None:
    """Reject OHLCV whose latest row is far older than *curr_date*."""
    if data is None or data.empty:
        return
    requested = pd.to_datetime(curr_date, errors="coerce")
    if pd.isna(requested):
        return
    requested = requested.normalize()
    dates = _coerce_ohlcv_dates(data)
    if dates.empty:
        return
    latest = dates.max().normalize()
    stale_days = (requested - latest).days
    if stale_days > max_stale_days:
        raise NoMarketDataError(
            symbol,
            canonical,
            f"latest row is {latest.date()}, {stale_days} days before "
            f"requested {requested.date()} (stale)",
        )


# ---------------------------------------------------------------------------
# OHLCV load & cache
# ---------------------------------------------------------------------------

def load_ohlcv_akshare(symbol: str, curr_date: str) -> pd.DataFrame:
    """Fetch 5 years of OHLCV via akshare, cache per symbol, filter to
    ``curr_date`` to prevent look-ahead bias."""
    market, clean_code = _classify_market(symbol)
    safe = safe_ticker_component(clean_code)

    config = get_config()
    curr_dt = pd.to_datetime(curr_date)
    today = pd.Timestamp.today()
    start_dt = today - pd.DateOffset(years=5)

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    cache_path = os.path.join(
        config["data_cache_dir"],
        f"{safe}-AK-data-{start_dt.strftime('%Y%m%d')}-{today.strftime('%Y%m%d')}.csv",
    )

    data = None
    if os.path.exists(cache_path):
        cached = pd.read_csv(cache_path, on_bad_lines="skip", encoding="utf-8")
        if not cached.empty and "Close" in cached.columns:
            data = cached

    if data is None:
        data = _download_ohlcv(market, clean_code, start_dt, today)
        if data is None or data.empty or "Close" not in data.columns:
            raise NoMarketDataError(
                symbol, clean_code, "akshare returned no OHLCV rows"
            )
        data = _ensure_date_column(data)
        data.to_csv(cache_path, index=False, encoding="utf-8")

    data = _clean_dataframe(data)
    data = data[data["Date"] <= curr_dt]
    _assert_ohlcv_not_stale(data, curr_date, symbol, clean_code)
    return data


def _download_ohlcv(
    market: str,
    code: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame | None:
    """Download raw OHLCV for the given market."""
    start_s = start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")

    if market in ("sh", "sz"):
        return ak_retry(
            lambda: ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=start_s, end_date=end_s, adjust="qfq",
            )
        )
    if market == "hk":
        return ak_retry(
            lambda: ak.stock_hk_hist(
                symbol=code, period="daily",
                start_date=start_s, end_date=end_s, adjust="qfq",
            )
        )
    if market == "us":
        return ak_retry(
            lambda: ak.stock_us_hist(
                symbol=code, period="daily",
                start_date=start_s, end_date=end_s, adjust="qfq",
            )
        )
    raise NoMarketDataError(code, code, f"unsupported market {market!r} for OHLCV")

