"""easy-tdx 数据获取：OHLCV、技术指标。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

import pandas as pd
from stockstats import wrap

from .easy_tdx_utils import (
    _classify_market,
    _clean_dataframe,
    _ensure_date_column,
    _rename_kline_columns,
    _download_ohlcv,
    load_ohlcv_easy_tdx,
)
from .errors import NoMarketDataError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OHLCV (core_stock_apis)
# ---------------------------------------------------------------------------

def get_easy_tdx_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """通过 easy-tdx 获取 OHLCV 数据。与 get_akshare_data_online 相同签名和输出格式。"""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    market, code = _classify_market(symbol)

    try:
        data = _download_ohlcv(market, code)
    except NoMarketDataError:
        raise
    except Exception as e:
        raise NoMarketDataError(symbol, code, str(e)) from e

    if data is None or data.empty:
        raise NoMarketDataError(
            symbol, code, f"no OHLCV rows between {start_date} and {end_date}"
        )

    data = _rename_kline_columns(data)
    data = _ensure_date_column(data)
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")

    # 过滤到请求的日期范围
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    data = data[(data["Date"] >= start_dt) & (data["Date"] <= end_dt)]

    if data.empty:
        raise NoMarketDataError(
            symbol, code, f"no OHLCV rows between {start_date} and {end_date}"
        )

    # 去除时区
    if hasattr(data.index, "tz") and data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    # 四舍五入
    for col in ["Open", "High", "Low", "Close", "Adj Close"]:
        if col in data.columns:
            data[col] = data[col].round(2)

    csv_string = data.to_csv(index=False)

    label = code if code == symbol.upper() else f"{code} (from {symbol})"
    header = f"# Stock data for {label} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data source: easy-tdx\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


# ---------------------------------------------------------------------------
# 技术指标
# ---------------------------------------------------------------------------

# 指标参数描述（与 akshare_data.py 保持一致）
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


def get_stock_stats_indicators_easy_tdx(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis of"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """通过 easy-tdx 获取 OHLCV + stockstats 计算技术指标。"""
    data = load_ohlcv_easy_tdx(symbol, curr_date)

    # 过滤到回看窗口
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

        # 添加回看窗口摘要
        window = df[df["Date"].isin(df["Date"].unique()[-look_back_days:])]
        if not window.empty and indicator in window.columns:
            lines.append(f"# {look_back_days}-day lookback summary:")
            data_subset = window[[indicator, "Date"]].dropna()
            if not data_subset.empty:
                csv_str = data_subset.to_csv(index=False)
                lines.append(csv_str)

        header = (
            f"# Technical Indicator: {indicator} for {symbol}\n"
            f"# Data source: easy-tdx\n"
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        return header + "\n".join(lines)

    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error computing indicator {indicator} for {symbol}: {str(e)}"
