'''A-stock signal data tools backed by easy-tdx.

提供: fund_flow (资金流向), concept_blocks (概念板块), industry_comparison (行业对比)。
其余信号工具 (profit_forecast, hot_stocks, northbound_flow, dragon_tiger_board,
lockup_expiry) 保持 akshare。
'''
from __future__ import annotations

import logging
from typing import Annotated

from .easy_tdx_utils import _classify_market, _get_client

logger = logging.getLogger(__name__)


def get_fund_flow(
    ticker: Annotated[str, "A-stock code"],
    curr_date: Annotated[str, "Date YYYY-MM-DD"],
    include_history: Annotated[bool, "Include 20-day history"] = True,
) -> str:
    '''通过 easy-tdx 获取个股资金流向（主力/散户）。'''
    market, code = _classify_market(ticker)
    try:
        client = _get_client()
        df = client.get_capital_flow(market, code)
        if df is None or df.empty:
            return f"[数据缺失: 个股资金流向 — {ticker}]"
        if not include_history and len(df) > 1:
            df = df.tail(1)
        elif include_history and len(df) > 20:
            df = df.tail(20)
        return df.to_string(index=False)
    except Exception as e:
        logger.warning("get_fund_flow (easy_tdx) failed for %s: %s", ticker, e)
        return f"[数据缺失: 个股资金流向 — {e}]"


def get_concept_blocks(
    ticker: Annotated[str, "A-stock code (e.g. 688017)"],
) -> str:
    '''通过 easy-tdx 获取个股所属概念/行业板块。'''
    market, code = _classify_market(ticker)
    try:
        client = _get_client()
        df = client.get_belong_board(market, code)
        if df is None or df.empty:
            return f"[数据缺失: 概念板块 — {ticker}]"
        return df.to_string(index=False)
    except Exception as e:
        logger.warning("get_concept_blocks (easy_tdx) failed for %s: %s", ticker, e)
        return f"[数据缺失: 概念板块 — {e}]"


def get_industry_comparison(
    ticker: Annotated[str, "A-stock code (e.g. 000858)"],
    curr_date: Annotated[str, "Date YYYY-MM-DD"],
) -> str:
    '''通过 easy-tdx 获取行业板块涨跌幅排行（行业横向对比）。'''
    try:
        from easy_tdx.mac.enums import BoardType

        client = _get_client()
        # 获取行业板块涨跌幅排行 (top 20)
        df = client.get_board_ranking(
            board_type=BoardType.HY,
            top_n=20,
            sort_by="change_pct",
        )
        if df is None or df.empty:
            return "[数据缺失: 行业对比 — 无行业数据]"
        return df.to_string(index=False)
    except Exception as e:
        logger.warning("get_industry_comparison (easy_tdx) failed: %s", e)
        return f"[数据缺失: 行业对比 — {e}]"
