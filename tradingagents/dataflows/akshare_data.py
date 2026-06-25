"""akshare-based data fetching: OHLCV, fundamentals, financial statements, indicators."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

import akshare as ak
import pandas as pd
from stockstats import wrap

from .akshare_utils import (
    _classify_market,
    _clean_dataframe,
    _ensure_date_column,
    _parse_akshare_date,
    ak_retry,
    load_ohlcv_akshare,
)
from .symbol_utils import NoMarketDataError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OHLCV (core_stock_apis)
# ---------------------------------------------------------------------------

def get_akshare_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    market, code = _classify_market(symbol)
    start_s = _parse_akshare_date(start_date)
    end_s = _parse_akshare_date(end_date)

    try:
        if market in ("sh", "sz"):
            data = ak_retry(
                lambda: ak.stock_zh_a_hist(
                    symbol=code, period="daily",
                    start_date=start_s, end_date=end_s, adjust="qfq",
                )
            )
        elif market == "hk":
            data = ak_retry(
                lambda: ak.stock_hk_hist(
                    symbol=code, period="daily",
                    start_date=start_s, end_date=end_s, adjust="qfq",
                )
            )
        elif market == "us":
            data = ak_retry(
                lambda: ak.stock_us_hist(
                    symbol=code, period="daily",
                    start_date=start_s, end_date=end_s, adjust="qfq",
                )
            )
        else:
            raise NoMarketDataError(symbol, code, f"unsupported market {market!r}")
    except NoMarketDataError:
        raise
    except Exception as e:
        raise NoMarketDataError(symbol, code, str(e)) from e

    if data is None or data.empty:
        raise NoMarketDataError(
            symbol, code, f"no OHLCV rows between {start_date} and {end_date}"
        )

    data = _ensure_date_column(data)
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")

    # Strip timezone
    if hasattr(data.index, "tz") and data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    # Round numeric columns
    for col in ["Open", "High", "Low", "Close", "Adj Close"]:
        if col in data.columns:
            data[col] = data[col].round(2)

    csv_string = data.to_csv(index=False)

    label = code if code == symbol.upper() else f"{code} (from {symbol})"
    header = f"# Stock data for {label} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------

_BEST_IND_PARAMS = {
    "close_50_sma": (
        "50 SMA: A medium-term trend indicator. "
        "Usage: Identify trend direction and serve as dynamic support/resistance. "
        "Tips: It lags price; combine with faster indicators for timely signals."
    ),
    "close_200_sma": (
        "200 SMA: A long-term trend benchmark. "
        "Usage: Confirm overall market trend and identify golden/death cross setups. "
        "Tips: It reacts slowly; best for strategic trend confirmation."
    ),
    "close_10_ema": (
        "10 EMA: A responsive short-term average. "
        "Usage: Capture quick shifts in momentum and potential entry points. "
        "Tips: Prone to noise in choppy markets."
    ),
    "macd": (
        "MACD: Computes momentum via differences of EMAs. "
        "Usage: Look for crossovers and divergence as signals of trend changes. "
        "Tips: Confirm with other indicators in low-volatility or sideways markets."
    ),
    "macds": (
        "MACD Signal: An EMA smoothing of the MACD line. "
        "Usage: Use crossovers with the MACD line to trigger trades. "
        "Tips: Should be part of a broader strategy to avoid false positives."
    ),
    "macdh": (
        "MACD Histogram: Shows the gap between the MACD line and its signal. "
        "Usage: Visualize momentum strength and spot divergence early. "
        "Tips: Can be volatile."
    ),
    "rsi": (
        "RSI: Measures momentum on a 0-100 scale. "
        "Usage: Values above 70 suggest overbought; below 30 suggest oversold. "
        "Tips: In strong trends RSI can stay overbought/oversold for extended periods."
    ),
    "boll": (
        "Bollinger Bands: Volatility bands around a moving average. "
        "Usage: Price near upper/lower band may indicate overbought/oversold. "
        "Tips: Band squeeze often precedes significant breakouts."
    ),
    "boll_ub": (
        "Bollinger Upper Band. "
        "Usage: Potential resistance; price above it may signal overbought. "
    ),
    "boll_lb": (
        "Bollinger Lower Band. "
        "Usage: Potential support; price below it may signal oversold."
    ),
    "atr": (
        "ATR: Average True Range for volatility measurement. "
        "Usage: Set stop-loss levels and position sizing. "
        "Tips: Higher ATR means wider stops to avoid premature exits."
    ),
    "vwma": (
        "VWMA: Volume Weighted Moving Average. "
        "Usage: Combines price and volume for more accurate trend analysis. "
        "Tips: More responsive than simple MA during volume spikes."
    ),
    "mfi": (
        "MFI: Money Flow Index (volume-weighted RSI). "
        "Usage: Identify overbought (>80) and oversold (<20) with volume confirmation. "
    ),
    "cci": (
        "CCI: Commodity Channel Index. "
        "Usage: Detect cyclical turns; >100 overbought, <-100 oversold. "
    ),
    "dma": (
        "DMA: Difference of short and long Moving Averages. "
        "Usage: DMA > 0 indicates bullish momentum. "
    ),
    "trix": (
        "TRIX: Triple Exponential Moving Average of price. "
        "Usage: Filter out short-term noise; detect medium/long-term reversals. "
    ),
    "volume_delta": (
        "Volume Delta: Difference between up-volume and down-volume. "
        "Usage: Confirm price moves; rising price + rising delta = strong trend. "
    ),
}


def get_stock_stats_indicators_akshare(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis of"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    data = load_ohlcv_akshare(symbol, curr_date)

    # Filter to look-back window
    curr_dt = pd.to_datetime(curr_date)
    start_dt = curr_dt - pd.DateOffset(days=look_back_days * 3)
    data = data[(data["Date"] >= start_dt) & (data["Date"] <= curr_dt)]

    if data.empty or "Close" not in data.columns:
        raise NoMarketDataError(symbol, symbol, "insufficient data for indicator")

    try:
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        curr_date_str = pd.to_datetime(curr_date).strftime("%Y-%m-%d")

        df[indicator]
        matching = df[df["Date"].str.startswith(curr_date_str)]

        if not matching.empty:
            indicator_value = matching[indicator].values[0]
        else:
            indicator_value = "N/A: Not a trading day (weekend or holiday)"

        param_desc = _BEST_IND_PARAMS.get(indicator, "")
        lines = []
        if param_desc:
            lines.append(f"# {indicator}: {param_desc}")
        lines.append(f"# Indicator value on {curr_date}: {indicator_value}")

        # Add a lookback window summary
        window = df[df["Date"].isin(df["Date"].unique()[-look_back_days:])]
        if not window.empty and indicator in window.columns:
            lines.append(f"# {look_back_days}-day lookback summary:")
            data_subset = window[[indicator, "Date"]].dropna()
            if not data_subset.empty:
                csv_str = data_subset.to_csv(index=False)
                lines.append(csv_str)

        header = (
            f"# Technical Indicator: {indicator} for {symbol}\n"
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        return header + "\n".join(lines)

    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error computing indicator {indicator} for {symbol}: {str(e)}"


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------

def get_akshare_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date (not used for akshare)"] = None,
) -> str:
    """Get company fundamentals overview from akshare."""
    market, code = _classify_market(ticker)
    try:
        if market in ("sh", "sz"):
            df = ak_retry(lambda: ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期"))
            if df is None or df.empty:
                raise NoMarketDataError(ticker, code, "no financial abstract data")
            # Use the most recent row
            row = df.iloc[-1] if not df.empty else None
            if row is None:
                raise NoMarketDataError(ticker, code, "empty fundamentals data")
            lines = []
            for col in df.columns:
                val = row[col]
                if pd.notna(val):
                    lines.append(f"{col}: {val}")
            header = (
                f"# Fundamentals for {code}\n"
                f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            )
            return header + "\n".join(lines)
        elif market == "us":
            # akshare has limited US fundamental data; use stock_financial_us_analysis_indicator_em
            try:
                df = ak_retry(lambda: ak.stock_financial_us_analysis_indicator_em(symbol=code))
                if df is not None and not df.empty:
                    csv = df.to_csv(index=False)
                    header = (
                        f"# US Fundamentals for {code}\n"
                        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    )
                    return header + csv
            except Exception:
                pass
            return f"Fundamentals data not available for US stock {code} via akshare (try alpha_vantage vendor)"
        else:
            return f"Fundamentals data not available for {ticker} (market={market}) via akshare"
    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


# ---------------------------------------------------------------------------
# Financial statements
# ---------------------------------------------------------------------------

def get_akshare_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get balance sheet from akshare."""
    market, code = _classify_market(ticker)
    try:
        if market in ("sh", "sz"):
            df = ak_retry(lambda: ak.stock_balance_sheet_by_report_em(symbol=code))
        else:
            return f"Balance sheet not available for {ticker} (market={market}) via akshare"

        if df is None or df.empty:
            raise NoMarketDataError(ticker, code, "no balance sheet data")
        if not isinstance(df, pd.DataFrame):
            raise NoMarketDataError(ticker, code, f"unexpected balance sheet type: {type(df).__name__}")

        csv_string = df.to_csv(index=False)
        header = (
            f"# Balance Sheet for {code}\n"
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        return header + csv_string
    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


def get_akshare_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get cash flow from akshare."""
    market, code = _classify_market(ticker)
    try:
        if market in ("sh", "sz"):
            df = ak_retry(lambda: ak.stock_cash_flow_sheet_by_report_em(symbol=code))
        else:
            return f"Cashflow not available for {ticker} (market={market}) via akshare"

        if df is None or df.empty:
            raise NoMarketDataError(ticker, code, "no cash flow data")
        if not isinstance(df, pd.DataFrame):
            raise NoMarketDataError(ticker, code, f"unexpected cash flow type: {type(df).__name__}")

        csv_string = df.to_csv(index=False)
        header = (
            f"# Cash Flow for {code}\n"
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        return header + csv_string
    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


def get_akshare_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get income statement from akshare."""
    market, code = _classify_market(ticker)
    try:
        if market in ("sh", "sz"):
            df = ak_retry(lambda: ak.stock_profit_sheet_by_report_em(symbol=code))
        else:
            return f"Income statement not available for {ticker} (market={market}) via akshare"

        if df is None or df.empty:
            raise NoMarketDataError(ticker, code, "no income statement data")
        if not isinstance(df, pd.DataFrame):
            raise NoMarketDataError(ticker, code, f"unexpected income statement type: {type(df).__name__}")

        csv_string = df.to_csv(index=False)
        header = (
            f"# Income Statement for {code}\n"
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        return header + csv_string
    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"


# ---------------------------------------------------------------------------
# Insider transactions (limited support in akshare)
# ---------------------------------------------------------------------------

def get_akshare_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Get insider transactions from akshare (CN market only)."""
    market, code = _classify_market(ticker)
    try:
        if market in ("sh", "sz"):
            try:
                df = ak_retry(lambda: ak.stock_hold_management_detail_em(symbol=code))
                if df is not None and not df.empty:
                    csv_string = df.to_csv(index=False)
                    header = (
                        f"# Insider / Management Holdings for {code}\n"
                        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    )
                    return header + csv_string
            except Exception:
                pass
            return f"No insider transactions reported for symbol '{code}'"
        else:
            return f"No insider transactions reported for symbol '{ticker}'"
    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {str(e)}"
