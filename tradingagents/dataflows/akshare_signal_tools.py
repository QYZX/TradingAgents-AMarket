'''A-stock signal data tools backed by akshare.

Provides: profit_forecast, hot_stocks, northbound_flow, concept_blocks,
fund_flow, dragon_tiger_board, lockup_expiry, industry_comparison.
'''
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Annotated

import akshare as ak
import pandas as pd
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_code(ticker: str) -> str:
    '''Normalise ticker to akshare-friendly format.'''
    t = str(ticker).strip().upper()
    # Strip suffixes / prefixes
    for s in (".SH", ".SZ", ".BJ", ".HK"):
        if t.endswith(s):
            t = t[: -len(s)]
    for p in ("SH", "SZ", "BJ"):
        if t.startswith(p) and len(t) == 8:
            t = t[2:]
    if not t.isdigit() or len(t) < 6:
        # Fill to 6 digits
        t = t.zfill(6)
    return t


def _to_code_with_prefix(ticker: str) -> str:
    '''Return e.g. "SZ000001" for akshare functions that need prefix.'''
    code = _resolve_code(ticker)
    if code.startswith(("6", "9")):
        return f"SH{code}"
    elif code.startswith("8"):
        return f"BJ{code}"
    return f"SZ{code}"


def _safe_df(df: pd.DataFrame | None) -> str:
    if df is None or df.empty:
        return "[No data returned]"
    return df.to_string(index=False)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def get_profit_forecast(
    ticker: Annotated[str, "A-stock code (e.g. 600519 or 688017)"],
) -> str:
    '''Retrieve consensus EPS forecasts with forward valuation metrics.
    Uses akshare stock_profit_forecast_em (eastmoney).
    '''
    code = _resolve_code(ticker)
    try:
        df = ak.stock_profit_forecast_em(symbol=code)
        if df is None or df.empty:
            return f"[数据缺失: 机构一致预期 EPS — {ticker} 无预测数据]"
        cols = [c for c in df.columns if c not in ("序号",)]
        return df[cols].to_string(index=False)
    except Exception as e:
        logger.warning("get_profit_forecast failed for %s: %s", ticker, e)
        return f"[数据缺失: 机构一致预期 EPS — {e}]"


@tool
def get_hot_stocks(
    curr_date: Annotated[str, "Date YYYY-MM-DD (empty for today)"] = "",
) -> str:
    '''Retrieve today's strong stocks with topic attribution.
    Uses akshare stock_hot_rank_em / stock_hot_up_em.
    '''
    try:
        # stock_hot_up_em gives big movers
        df = ak.stock_hot_up_em()
        if df is None or df.empty:
            return "[数据缺失: 当日强势股列表]"
        return df.head(30).to_string(index=False)
    except Exception as e:
        logger.warning("get_hot_stocks failed: %s", e)
        return f"[数据缺失: 当日强势股 — {e}]"


@tool
def get_northbound_flow(
    curr_date: Annotated[str, "Date YYYY-MM-DD"],
    include_history: Annotated[bool, "Include recent daily history"] = False,
) -> str:
    '''Retrieve northbound capital flow (沪深股通).
    Uses akshare stock_hsgt_hist_em.
    '''
    try:
        if include_history:
            df = ak.stock_hsgt_hist_em(symbol="北上资金")
            if df is None or df.empty:
                return f"[数据缺失: 北向资金历史 — 无数据]"
            return df.tail(30).to_string(index=False)
        else:
            df = ak.stock_hsgt_hist_em(symbol="北上资金")
            if df is None or df.empty:
                return f"[数据缺失: 北向资金 — 无数据]"
            return df.tail(3).to_string(index=False)
    except Exception as e:
        logger.warning("get_northbound_flow failed: %s", e)
        return f"[数据缺失: 北向资金 — {e}]"


@tool
def get_concept_blocks(
    ticker: Annotated[str, "A-stock code (e.g. 688017)"],
) -> str:
    '''Retrieve concept / sector blocks a stock belongs to.
    Uses akshare stock_board_concept_cons_em.
    '''
    code = _resolve_code(ticker)
    try:
        df = ak.stock_board_concept_cons_em(symbol=code)
        if df is None or df.empty:
            return f"[数据缺失: 概念板块 — {ticker}]"
        return df.head(20).to_string(index=False)
    except Exception as e:
        logger.warning("get_concept_blocks failed for %s: %s", ticker, e)
        return f"[数据缺失: 概念板块 — {e}]"


@tool
def get_fund_flow(
    ticker: Annotated[str, "A-stock code"],
    curr_date: Annotated[str, "Date YYYY-MM-DD"],
    include_history: Annotated[bool, "Include 20-day history"] = True,
) -> str:
    '''Retrieve individual stock fund flow (main force vs retail).
    Uses akshare stock_individual_fund_flow.
    '''
    code = _resolve_code(ticker)
    try:
        if code.startswith(("6", "9")):
            market = "sh"
        elif code.startswith("8"):
            market = "bj"
        else:
            market = "sz"
        df = ak.stock_individual_fund_flow(stock=code, market=market)
        if df is None or df.empty:
            return f"[数据缺失: 个股资金流向 — {ticker}]"
        if include_history and len(df) > 20:
            df = df.tail(20)
        return df.to_string(index=False)
    except Exception as e:
        logger.warning("get_fund_flow failed for %s: %s", ticker, e)
        return f"[数据缺失: 个股资金流向 — {e}]"


@tool
def get_dragon_tiger_board(
    ticker: Annotated[str, "A-stock code (e.g. 000858)"],
    curr_date: Annotated[str, "Date YYYY-MM-DD"],
    look_back_days: Annotated[int, "Days back (default 30)"] = 30,
) -> str:
    '''Retrieve dragon-tiger board (龙虎榜) appearances.
    Uses akshare stock_lhb_stock_detail_em.
    '''
    code = _resolve_code(ticker)
    try:
        prefixed = _to_code_with_prefix(code)
        # Use a recent date - try multiple dates going back
        results = []
        dt = datetime.strptime(curr_date, "%Y-%m-%d")
        for i in range(min(look_back_days, 30)):
            check_date = (dt - timedelta(days=i)).strftime("%Y%m%d")
            try:
                df = ak.stock_lhb_stock_detail_em(
                    symbol=prefixed, date=check_date, flag="上榜"
                )
                if df is not None and not df.empty:
                    results.append(df)
                    if len(results) >= 5:
                        break
            except Exception:
                continue
        if not results:
            return f"[数据缺失: 龙虎榜 — {ticker} 近{look_back_days}日内无上榜记录]"
        combined = pd.concat(results, ignore_index=True)
        return combined.to_string(index=False)
    except Exception as e:
        logger.warning("get_dragon_tiger_board failed for %s: %s", ticker, e)
        return f"[数据缺失: 龙虎榜 — {e}]"


@tool
def get_lockup_expiry(
    ticker: Annotated[str, "A-stock code (e.g. 000858)"],
    curr_date: Annotated[str, "Date YYYY-MM-DD"],
    forward_days: Annotated[int, "Days forward (default 90)"] = 90,
) -> str:
    '''Retrieve lockup expiry (限售解禁) schedule.
    Uses akshare stock_restricted_release_detail_em.
    '''
    code = _resolve_code(ticker)
    try:
        dt = datetime.strptime(curr_date, "%Y-%m-%d")
        end_date = (dt + timedelta(days=forward_days)).strftime("%Y%m%d")
        start_date = (dt - timedelta(days=180)).strftime("%Y%m%d")
        df = ak.stock_restricted_release_detail_em(
            start_date=start_date, end_date=end_date
        )
        if df is None or df.empty:
            return f"[数据缺失: 限售解禁 — {ticker} 无近期解禁数据]"
        # Filter for this ticker if possible
        code_col = None
        for c in df.columns:
            if "代码" in c or "code" in c.lower() or "symbol" in c.lower():
                code_col = c
                break
        if code_col:
            df = df[df[code_col].astype(str).str.contains(code, na=False)]
        if df.empty:
            return f"[数据缺失: 限售解禁 — {ticker} 无近期解禁计划]"
        return df.to_string(index=False)
    except Exception as e:
        logger.warning("get_lockup_expiry failed for %s: %s", ticker, e)
        return f"[数据缺失: 限售解禁 — {e}]"


@tool
def get_industry_comparison(
    ticker: Annotated[str, "A-stock code (e.g. 000858)"],
    curr_date: Annotated[str, "Date YYYY-MM-DD"],
) -> str:
    '''Retrieve industry sector performance comparison (行业横向对比).
    Uses akshare stock_board_industry_spot_em.
    '''
    try:
        # Get all industry performance
        all_industries = []
        # Try a few major industry names as proxies
        for ind in ["小金属", "电子", "医药制造", "银行", "房地产", "食品饮料", "电力",
                     "汽车", "计算机", "通信", "有色金属", "采掘", "钢铁", "化工", "纺织",
                     "建筑材料", "家用电器", "机械设备", "非银金融", "交通运输", "国防军工"]:
            try:
                df = ak.stock_board_industry_spot_em(symbol=ind)
                if df is not None and not df.empty:
                    all_industries.append(df)
            except Exception:
                continue
            if len(all_industries) >= 10:
                break
        if not all_industries:
            return f"[数据缺失: 行业对比 — 无行业数据]"
        combined = pd.concat(all_industries, ignore_index=True)
        return combined.to_string(index=False)
    except Exception as e:
        logger.warning("get_industry_comparison failed: %s", e)
        return f"[数据缺失: 行业对比 — {e}]"
