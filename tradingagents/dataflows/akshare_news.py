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
            title = row.get("title", row.get("标题", "No title"))
            content = row.get("content", row.get("内容", ""))
            publisher = row.get("source", row.get("来源", "Unknown"))
            link = row.get("url", row.get("链接", ""))
            pub_time = row.get("pub_time", row.get("发布时间", None))

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
    """Retrieve global/macro economic news using akshare.

    Uses akshare news feeds for macro headlines.  Since akshare primarily
    covers Chinese financial news sources, global coverage is limited.
    """
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]

    try:
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - relativedelta(days=look_back_days)
        start_date = start_dt.strftime("%Y-%m-%d")

        # Use akshare's macro/economy news functions
        all_articles = []

        # Try stock_news_em with keyword "宏观" as a fallback for macro news
        try:
            macro_news = ak_retry(lambda: ak.stock_news_main_cx())
            if macro_news is not None and not macro_news.empty:
                for _, row in macro_news.iterrows():
                    title = row.get("title", row.get("标题", "No title"))
                    content = row.get("content", row.get("内容", ""))
                    publisher = row.get("source", row.get("来源", "Unknown"))
                    link = row.get("url", row.get("链接", ""))
                    pub_time = row.get("pub_time", row.get("发布时间", None))

                    pub_date = None
                    if pub_time and not pd.isna(pub_time):
                        with contextlib.suppress(ValueError):
                            if isinstance(pub_time, str):
                                pub_date = datetime.fromisoformat(pub_time.replace("Z", "+00:00"))
                            elif isinstance(pub_time, (int, float)):
                                pub_date = datetime.fromtimestamp(pub_time / 1000 if pub_time > 1e12 else pub_time)

                    if not _in_news_window(pub_date, start_dt, curr_dt):
                        continue

                    all_articles.append({
                        "title": title,
                        "content": content,
                        "publisher": publisher,
                        "link": link,
                    })

                    if len(all_articles) >= limit:
                        break
        except Exception:
            logger.debug("stock_news_main_cx failed, continuing without it")

        if not all_articles:
            return f"No global news found between {start_date} and {curr_date}"

        news_str = ""
        for article in all_articles[:limit]:
            news_str += f"### {article['title']} (source: {article['publisher']})\n"
            if article["content"]:
                news_str += f"{article['content']}\n"
            if article["link"]:
                news_str += f"Link: {article['link']}\n"
            news_str += "\n"

        return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching global news: {str(e)}"
