"""akshare-based news data fetching functions."""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime

import akshare as ak
import pandas as pd
from dateutil.relativedelta import relativedelta

from .akshare_utils import ak_retry, _classify_market
from .config import get_config

logger = logging.getLogger(__name__)


def _in_news_window(pub_date, start_dt, end_dt) -> bool:
    """Whether an article belongs in the [start_dt, end_dt] window."""
    if pub_date is not None:
        naive = pub_date.replace(tzinfo=None) if hasattr(pub_date, "replace") else pub_date
        return start_dt <= naive <= end_dt + relativedelta(days=1)
    return end_dt >= datetime.now() - relativedelta(days=1)


# ---------------------------------------------------------------------------
# Stock-specific news
# ---------------------------------------------------------------------------

def get_news_akshare(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Retrieve news for a specific stock ticker using akshare.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL", "600519")
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        Formatted string containing news articles
    """
    article_limit = get_config()["news_article_limit"]
    market, code = _classify_market(ticker)

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        if market in ("sh", "sz"):
            news = ak_retry(lambda: ak.stock_news_em(symbol=code))
        elif market == "us":
            # akshare has limited US news; return a clear signal
            return f"Stock-specific news not available for US ticker '{ticker}' via akshare"
        else:
            return f"Stock-specific news not available for '{ticker}' via akshare"

        if news is None or (hasattr(news, "empty") and news.empty):
            return f"No news found for {ticker}"

        news_str = ""
        filtered_count = 0

        for _, row in news.iterrows():
            title = row.get("新闻标题", "No title")
            content = row.get("新闻内容", "")
            publisher = row.get("文章来源", "Unknown")
            link = row.get("新闻链接", "")
            pub_time = row.get("发布时间", None)

            pub_date = None
            if pub_time and not pd.isna(pub_time):
                with contextlib.suppress(ValueError, AttributeError):
                    if isinstance(pub_time, (int, float)):
                        pub_date = datetime.fromtimestamp(pub_time)
                    elif isinstance(pub_time, str):
                        pub_date = datetime.fromisoformat(pub_time.replace("Z", "+00:00"))

            if not _in_news_window(pub_date, start_dt, end_dt):
                continue

            news_str += f"### {title} (source: {publisher})\n"
            if content:
                news_str += f"{content}\n"
            if link:
                news_str += f"Link: {link}\n"
            news_str += "\n"
            filtered_count += 1

            if filtered_count >= article_limit:
                break

        if filtered_count == 0:
            return f"No news found for {ticker} between {start_date} and {end_date}"

        return f"## {ticker} News, from {start_date} to {end_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"


# ---------------------------------------------------------------------------
# Global / macro news
# ---------------------------------------------------------------------------

def get_global_news_akshare(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """Retrieve Chinese macro economic indicators via akshare.

    Calls the following akshare macro interfaces and returns the data as-is:

    - macro_china_gdp_yearly          中国 GDP 年率
    - macro_china_cpi_yearly          物价水平-中国 CPI 年率
    - macro_china_ppi_yearly          中国 PPI 年率
    - macro_china_urban_unemployment  城镇调查失业率
    - macro_china_shrzgm              社会融资规模增量
    - macro_rmb_loan                  新增人民币贷款
    - macro_china_lpr                 LPR 品种数据
    """
    # Map of (section_title, akshare_callable)
    _MACRO_FETCHERS = [
        ("中国 GDP 年率", lambda: ak.macro_china_gdp_yearly()),
        ("物价水平-中国 CPI 年率", lambda: ak.macro_china_cpi_yearly()),
        ("中国 PPI 年率", lambda: ak.macro_china_ppi_yearly()),
        ("城镇调查失业率", lambda: ak.macro_china_urban_unemployment()),
        ("社会融资规模增量", lambda: ak.macro_china_shrzgm()),
        ("新增人民币贷款", lambda: ak.macro_rmb_loan()),
        ("LPR 品种数据", lambda: ak.macro_china_lpr()),
    ]

    sections: list[str] = []

    for title, fetcher in _MACRO_FETCHERS:
        try:
            df = ak_retry(fetcher)
        except Exception as exc:
            logger.warning("macro fetch failed for %s: %s", title, exc)
            sections.append(f"### {title}\n获取失败: {exc}\n")
            continue

        if df is None or (hasattr(df, "empty") and df.empty):
            sections.append(f"### {title}\n无数据\n")
            continue

        sections.append(f"### {title}\n{df.to_string(index=False)}\n")

    if not sections:
        return f"No macro data retrieved for {curr_date}"

    return (
        f"## 中国宏观经济指标 (Macro Indicators as of {curr_date})\n\n"
        + "\n".join(sections)
    )
