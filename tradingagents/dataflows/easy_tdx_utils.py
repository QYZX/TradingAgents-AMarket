"""easy-tdx 工具函数：符号分类、客户端管理、DataFrame 处理、OHLCV 缓存。"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Tuple

import pandas as pd
from easy_tdx import UnifiedTdxClient, Market
from easy_tdx.mac.enums import Adjust, ExMarket, Period

from .config import get_config
from .errors import NoMarketDataError, VendorNotConfiguredError
from .utils import safe_ticker_component

logger = logging.getLogger(__name__)

MAX_OHLCV_STALE_DAYS = 10

# ---------------------------------------------------------------------------
# 客户端单例
# ---------------------------------------------------------------------------

_client: UnifiedTdxClient | None = None


def _get_client() -> UnifiedTdxClient:
    """返回懒加载的 UnifiedTdxClient 单例（自动选择延迟最低的服务器）。"""
    global _client
    if _client is not None:
        return _client
    try:
        _client = UnifiedTdxClient()
        _client.connect()
        return _client
    except Exception as e:
        _client = None
        raise VendorNotConfiguredError(
            f"easy_tdx: 无法连接 TDX 服务器: {e}"
        ) from e


def reset_client() -> None:
    """重置客户端单例（用于测试或连接断开后）。"""
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None


# ---------------------------------------------------------------------------
# 符号分类
# ---------------------------------------------------------------------------

def _classify_market(raw: str) -> Tuple[int, str]:
    """将用户输入的符号映射为 easy-tdx 的 (market_int, code)。

    market_int 对应 Market/ExMarket 枚举的 int 值:
      - Market.SZ (0): 深证
      - Market.SH (1): 上证
      - Market.BJ (2): 北证
      - ExMarket.HK_MAIN_BOARD (31): 港股主板
      - ExMarket.US_STOCK (74): 美股
    """
    s = raw.strip().upper()

    # 带后缀的符号
    for suffix, market in [(".SS", Market.SH), (".SH", Market.SH), (".SZ", Market.SZ), (".BJ", Market.BJ)]:
        if s.endswith(suffix):
            code = s[: -len(suffix)]
            return int(market), code

    if s.endswith(".HK"):
        code = s[: -len(".HK")].zfill(5)
        return int(ExMarket.HK_MAIN_BOARD), code

    # 纯数字
    if s.isdigit():
        if len(s) == 5:
            return int(ExMarket.HK_MAIN_BOARD), s
        if len(s) == 6:
            if s.startswith(("6", "9")):
                return int(Market.SH), s
            if s.startswith(("0", "3")):
                return int(Market.SZ), s
            if s.startswith(("8", "4")):
                return int(Market.BJ), s
            return int(Market.SZ), s

    # 非数字 → 美股
    return int(ExMarket.US_STOCK), s


# ---------------------------------------------------------------------------
# DataFrame 辅助
# ---------------------------------------------------------------------------

# easy-tdx 返回的列名 → 标准列名映射
_KLINE_COLUMN_MAP = {
    "datetime": "Date",
    "date": "Date",
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "vol": "Volume",
    "amount": "Amount",
}


def _rename_kline_columns(data: pd.DataFrame) -> pd.DataFrame:
    """将 easy-tdx 返回的小写列名映射为标准大写列名。"""
    rename_map = {k: v for k, v in _KLINE_COLUMN_MAP.items() if k in data.columns}
    if rename_map:
        data = data.rename(columns=rename_map)
    return data


def _ensure_date_column(data: pd.DataFrame) -> pd.DataFrame:
    """确保 DataFrame 有 'Date' 列。"""
    if "Date" in data.columns:
        return data
    for cand in ("index", "Datetime", "date", "日期", "datetime"):
        if cand in data.columns:
            return data.rename(columns={cand: "Date"})
    return data


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """解析日期、删除无效行、前向填充价格缺口。"""
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
    """从 OHLCV DataFrame 中提取解析后的日期序列。"""
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
    """拒绝最新行远早于 curr_date 的 OHLCV 数据。"""
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
# OHLCV 加载 & 缓存
# ---------------------------------------------------------------------------

def load_ohlcv_easy_tdx(symbol: str, curr_date: str) -> pd.DataFrame:
    """通过 easy-tdx 获取 5 年 OHLCV 数据，缓存并过滤到 curr_date。"""
    market, code = _classify_market(symbol)
    safe = safe_ticker_component(code)

    config = get_config()
    curr_dt = pd.to_datetime(curr_date)
    today = pd.Timestamp.today()
    start_dt = today - pd.DateOffset(years=5)

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    cache_path = os.path.join(
        config["data_cache_dir"],
        f"{safe}-TDX-data-{start_dt.strftime('%Y%m%d')}-{today.strftime('%Y%m%d')}.csv",
    )

    data = None
    if os.path.exists(cache_path):
        cached = pd.read_csv(cache_path, on_bad_lines="skip", encoding="utf-8")
        if not cached.empty and "Close" in cached.columns:
            data = cached

    if data is None:
        data = _download_ohlcv(market, code)
        if data is None or data.empty:
            raise NoMarketDataError(
                symbol, code, "easy-tdx returned no OHLCV rows"
            )
        data = _rename_kline_columns(data)
        data = _ensure_date_column(data)
        data.to_csv(cache_path, index=False, encoding="utf-8")

    data = _clean_dataframe(data)
    data = data[data["Date"] <= curr_dt]
    _assert_ohlcv_not_stale(data, curr_date, symbol, code)
    return data


def _download_ohlcv(market: int, code: str) -> pd.DataFrame | None:
    """通过 easy-tdx 下载原始 OHLCV 数据（5 年日线，前复权）。"""
    client = _get_client()

    # 5 年 ≈ 250 交易日/年 × 5 = 1250，加缓冲取 1300
    count = 1300

    # A 股使用 get_stock_kline，扩展市场使用 goods_kline
    if market in (int(Market.SH), int(Market.SZ), int(Market.BJ)):
        return client.get_stock_kline(
            market=market,
            code=code,
            period=Period.DAILY,
            start=0,
            count=count,
            adjust=Adjust.QFQ,
        )
    else:
        return client.goods_kline(
            market=market,
            code=code,
            period=Period.DAILY,
            start=0,
            count=count,
            adjust=Adjust.QFQ,
        )
