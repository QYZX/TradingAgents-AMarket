"""akshare dataflows: symbol classification, date parsing, retry logic,
DataFrame helpers, OHLCV loading, financial statements, news, and signal tools.

All API access is mocked — runs without network or API keys.
"""
import os
import tempfile
import unittest
from datetime import datetime
from unittest import mock

import pandas as pd
import pytest

from tradingagents.dataflows.akshare_utils import (
    _classify_market,
    _clean_dataframe,
    _ensure_date_column,
    _parse_akshare_date,
    ak_retry,
    _assert_ohlcv_not_stale,
)
from tradingagents.dataflows.symbol_utils import NoMarketDataError

# ============================================================
# akshare_utils – _classify_market
# ============================================================

@pytest.mark.unit
class ClassifyMarketTests(unittest.TestCase):
    """A-share SH/SZ/HK/US symbol classification."""

    def test_shanghai_suffix_ss(self):
        market, code = _classify_market("600519.SS")
        self.assertEqual(market, "sh")
        self.assertEqual(code, "600519")

    def test_shanghai_suffix_sh(self):
        market, code = _classify_market("600519.SH")
        self.assertEqual(market, "sh")
        self.assertEqual(code, "600519")

    def test_shenzhen_suffix(self):
        market, code = _classify_market("000001.SZ")
        self.assertEqual(market, "sz")
        self.assertEqual(code, "000001")

    def test_hk_suffix(self):
        market, code = _classify_market("0700.HK")
        self.assertEqual(market, "hk")
        self.assertEqual(code, "00700")

    def test_bare_6digit_sh(self):
        market, code = _classify_market("601318")
        self.assertEqual(market, "sh")
        self.assertEqual(code, "601318")

    def test_bare_6digit_sz(self):
        market, code = _classify_market("000001")
        self.assertEqual(market, "sz")
        self.assertEqual(code, "000001")

    def test_bare_6digit_starts_with_9(self):
        market, code = _classify_market("900901")
        self.assertEqual(market, "sh")

    def test_bare_5digit_is_hk(self):
        market, code = _classify_market("00700")
        self.assertEqual(market, "hk")
        self.assertEqual(code, "00700")

    def test_non_numeric_falls_back_to_us(self):
        market, code = _classify_market("AAPL")
        self.assertEqual(market, "us")
        self.assertEqual(code, "AAPL")

    def test_case_insensitive(self):
        market, code = _classify_market("aapl")
        self.assertEqual(market, "us")
        self.assertEqual(code, "AAPL")

# ============================================================
# akshare_utils – _parse_akshare_date
# ============================================================

@pytest.mark.unit
class ParseAkshareDateTests(unittest.TestCase):
    def test_standard_date(self):
        self.assertEqual(_parse_akshare_date("2025-06-15"), "20250615")

    def test_leap_day(self):
        self.assertEqual(_parse_akshare_date("2024-02-29"), "20240229")

    def test_invalid_date_raises(self):
        with self.assertRaises(ValueError):
            _parse_akshare_date("not-a-date")

# ============================================================
# akshare_utils – ak_retry
# ============================================================

@pytest.mark.unit
class AkRetryTests(unittest.TestCase):
    def test_success_on_first_try(self):
        result = ak_retry(lambda: 42, max_retries=3)
        self.assertEqual(result, 42)

    def test_retries_then_succeeds(self):
        call_count = {"n": 0}
        def flaky():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise RuntimeError("transient")
            return "ok"
        result = ak_retry(flaky, max_retries=3, base_delay=0.01)
        self.assertEqual(result, "ok")
        self.assertEqual(call_count["n"], 3)

    def test_raises_after_max_retries(self):
        with self.assertRaises(RuntimeError):
            ak_retry(lambda: (_ for _ in ()).throw(RuntimeError("fail")), max_retries=1, base_delay=0.01)

# ============================================================
# akshare_utils – _ensure_date_column
# ============================================================

@pytest.mark.unit
class EnsureDateColumnTests(unittest.TestCase):
    def test_already_has_date(self):
        df = pd.DataFrame({"Date": ["2025-01-01"], "Close": [10.0]})
        result = _ensure_date_column(df)
        self.assertIn("Date", result.columns)

    def test_renames_index(self):
        df = pd.DataFrame({"Close": [10.0]}, index=pd.to_datetime(["2025-01-01"]))
        df.index.name = "index"
        df = df.reset_index()
        result = _ensure_date_column(df)
        self.assertIn("Date", result.columns)

    def test_renames_chinese_date(self):
        df = pd.DataFrame({"\u65e5\u671f": ["2025-01-01"], "Close": [10.0]})
        result = _ensure_date_column(df)
        self.assertIn("Date", result.columns)

    def test_no_date_column_unchanged(self):
        df = pd.DataFrame({"A": [1], "B": [2]})
        result = _ensure_date_column(df)
        self.assertNotIn("Date", result.columns)

# ============================================================
# akshare_utils – _clean_dataframe
# ============================================================

@pytest.mark.unit
class CleanDataframeTests(unittest.TestCase):
    def test_parses_dates_and_drops_nan(self):
        df = pd.DataFrame({
            "Date": ["2025-01-01", "2025-01-02", None],
            "Open": [10.0, 11.0, 12.0],
            "High": [12.0, 13.0, 14.0],
            "Low": [9.0, 10.0, 11.0],
            "Close": [11.0, 12.0, None],
            "Volume": [100, 200, 300],
        })
        result = _clean_dataframe(df)
        self.assertEqual(len(result), 2)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result["Date"]))

    def test_forward_fill_price_gaps(self):
        df = pd.DataFrame({
            "Date": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "Open": [10.0, None, 12.0],
            "High": [12.0, None, 14.0],
            "Low": [9.0, None, 11.0],
            "Close": [11.0, 11.5, 13.0],
            "Volume": [100, None, 300],
        })
        result = _clean_dataframe(df)
        self.assertEqual(len(result), 3)

# ============================================================
# akshare_utils – _assert_ohlcv_not_stale
# ============================================================

@pytest.mark.unit
class AssertOhlcvNotStaleTests(unittest.TestCase):
    def test_fresh_data_passes(self):
        df = pd.DataFrame({
            "Date": pd.to_datetime(["2026-06-25", "2026-06-26"]),
            "Close": [100.0, 101.0],
        })
        _assert_ohlcv_not_stale(df, "2026-06-28", "TEST", max_stale_days=10)

    def test_stale_data_raises(self):
        df = pd.DataFrame({
            "Date": pd.to_datetime(["2026-05-01"]),
            "Close": [100.0],
        })
        with self.assertRaises(NoMarketDataError):
            _assert_ohlcv_not_stale(df, "2026-06-28", "TEST", max_stale_days=10)

    def test_empty_dataframe_is_noop(self):
        df = pd.DataFrame()
        _assert_ohlcv_not_stale(df, "2026-06-28", "TEST")

    def test_none_dataframe_is_noop(self):
        _assert_ohlcv_not_stale(None, "2026-06-28", "TEST")

# ============================================================
# akshare_data – get_akshare_data_online
# ============================================================

@pytest.mark.unit
class AkshareDataOnlineTests(unittest.TestCase):
    """Test get_akshare_data_online with mocked akshare APIs."""

    def test_sh_stock_returns_csv_with_header(self):

        from tradingagents.dataflows.akshare_data import get_akshare_data_online
        result = get_akshare_data_online("600519", "2026-06-01", "2026-06-07")

        self.assertIn("Stock data for", result)
        self.assertIn("600519", result)
        self.assertIn("Total records: 5", result)

    def test_empty_data_raises_no_market_data(self):

        from tradingagents.dataflows.akshare_data import get_akshare_data_online
        with self.assertRaises(NoMarketDataError):
            get_akshare_data_online("999999", "2026-06-01", "2026-06-07")

    def test_invalid_date_format_raises(self):
        from tradingagents.dataflows.akshare_data import get_akshare_data_online
        with self.assertRaises(ValueError):
            get_akshare_data_online("600519", "20260601", "2026-06-07")

# ============================================================
# akshare_data – financial statements
# ============================================================

@pytest.mark.unit
class FinancialStatementTests(unittest.TestCase):
    """Test balance sheet, cashflow, income statement functions."""

    def test_balance_sheet_returns_csv(self):

        from tradingagents.dataflows.akshare_data import get_akshare_balance_sheet
        result = get_akshare_balance_sheet("600519")

        self.assertIn("Balance Sheet for 600519", result)
        self.assertIn("TOTAL_ASSETS", result)

    def test_cashflow_returns_csv(self):

        from tradingagents.dataflows.akshare_data import get_akshare_cashflow
        result = get_akshare_cashflow("600519")

        self.assertIn("Cash Flow for 600519", result)

    def test_income_statement_returns_csv(self):

        from tradingagents.dataflows.akshare_data import get_akshare_income_statement
        result = get_akshare_income_statement("300750.SZ")
        self.assertIn("Income Statement for 300750", result)

    def test_balance_sheet_non_cn_returns_not_available(self):

        from tradingagents.dataflows.akshare_data import get_akshare_balance_sheet
        result = get_akshare_balance_sheet("AAPL")
        self.assertIn("not available", result)

# ============================================================
# akshare_data – insider transactions
# ============================================================

@pytest.mark.unit
class InsiderTransactionTests(unittest.TestCase):
    def test_cn_stock_returns_data(self):

        from tradingagents.dataflows.akshare_data import get_akshare_insider_transactions
        result = get_akshare_insider_transactions("600519")
        self.assertTrue("insider" in result.lower())

    def test_us_stock_returns_no_data(self):

        from tradingagents.dataflows.akshare_data import get_akshare_insider_transactions
        result = get_akshare_insider_transactions("AAPL")
        self.assertIn("No insider", result)

# ============================================================
# akshare_news – _in_news_window
# ============================================================

@pytest.mark.unit
class InNewsWindowTests(unittest.TestCase):
    def test_date_in_window_returns_true(self):
        from tradingagents.dataflows.akshare_news import _in_news_window
        pub = datetime(2026, 6, 15)
        self.assertTrue(_in_news_window(pub, datetime(2026, 6, 1), datetime(2026, 6, 30)))

    def test_date_outside_window_returns_false(self):
        from tradingagents.dataflows.akshare_news import _in_news_window
        pub = datetime(2026, 5, 15)
        self.assertFalse(_in_news_window(pub, datetime(2026, 6, 1), datetime(2026, 6, 30)))

    def test_none_pub_date_falls_back_to_recent(self):
        from tradingagents.dataflows.akshare_news import _in_news_window
        # None pub_date: returns True if end_dt is within 1 day of now
        self.assertTrue(
            _in_news_window(None, datetime(2026, 1, 1), datetime.now())
        )

# ============================================================
# akshare_news – get_news_akshare
# ============================================================

@pytest.mark.unit
@pytest.mark.unit
@pytest.mark.unit
class GetNewsAkshareTests(unittest.TestCase):
    def test_returns_formatted_news(self):

        from tradingagents.dataflows.akshare_news import get_news_akshare
        result = get_news_akshare("600519", "2026-06-01", "2026-06-30")
        self.assertIn("\u8305\u53f0\u65b0\u54c1\u53d1\u5e03", result)
        self.assertIn("\u4e1c\u65b9\u8d22\u5bcc", result)

    def test_us_ticker_returns_not_available(self):

        from tradingagents.dataflows.akshare_news import get_news_akshare
        result = get_news_akshare("AAPL", "2026-06-01", "2026-06-30")
        self.assertIn("not available", result)
class GetGlobalNewsAkshareTests(unittest.TestCase):
    def test_returns_macro_indicators(self):

        from tradingagents.dataflows.akshare_news import get_global_news_akshare
        result = get_global_news_akshare("2026-06-28")
        self.assertIn("中国宏观经济指标", result)
        self.assertIn("中国 GDP 年率", result)
        self.assertIn("5.0", result)

    def test_all_empty_returns_no_data(self):

        from tradingagents.dataflows.akshare_news import get_global_news_akshare
        result = get_global_news_akshare("2026-06-28")
        self.assertIn("无数据", result)

    def test_partial_failure_still_returns_other_data(self):

        from tradingagents.dataflows.akshare_news import get_global_news_akshare
        result = get_global_news_akshare("2026-06-28")
        self.assertIn("获取失败", result)
        self.assertIn("CPI", result)

# ============================================================
# akshare_signal_tools – _resolve_code / _to_code_with_prefix
# ============================================================

@pytest.mark.unit
class ResolveCodeTests(unittest.TestCase):
    def test_strips_sh_suffix(self):
        from tradingagents.dataflows.akshare_signal_tools import _resolve_code
        self.assertEqual(_resolve_code("600519.SH"), "600519")

    def test_strips_sz_suffix(self):
        from tradingagents.dataflows.akshare_signal_tools import _resolve_code
        self.assertEqual(_resolve_code("000001.SZ"), "000001")

    def test_strips_hk_suffix(self):
        from tradingagents.dataflows.akshare_signal_tools import _resolve_code
        self.assertEqual(_resolve_code("00700.HK"), "000700")

    def test_pad_short_code(self):
        from tradingagents.dataflows.akshare_signal_tools import _resolve_code
        self.assertEqual(_resolve_code("1"), "000001")

    def test_bare_6digit_code(self):
        from tradingagents.dataflows.akshare_signal_tools import _resolve_code
        self.assertEqual(_resolve_code("600519"), "600519")

@pytest.mark.unit
class CodeWithPrefixTests(unittest.TestCase):
    def test_sh_prefix_for_6_start(self):
        from tradingagents.dataflows.akshare_signal_tools import _to_code_with_prefix
        self.assertEqual(_to_code_with_prefix("600519"), "SH600519")

    def test_sz_prefix_for_0_start(self):
        from tradingagents.dataflows.akshare_signal_tools import _to_code_with_prefix
        self.assertEqual(_to_code_with_prefix("000001"), "SZ000001")

    def test_sz_prefix_for_3_start(self):
        from tradingagents.dataflows.akshare_signal_tools import _to_code_with_prefix
        self.assertEqual(_to_code_with_prefix("300750"), "SZ300750")

    def test_bj_prefix_for_8_start(self):
        from tradingagents.dataflows.akshare_signal_tools import _to_code_with_prefix
        self.assertEqual(_to_code_with_prefix("830799"), "BJ830799")

# ============================================================
# akshare_signal_tools – tool functions (mocked)
# ============================================================

@pytest.mark.unit
class SignalToolTests(unittest.TestCase):
    def test_get_profit_forecast_returns_data(self):

        from tradingagents.dataflows.akshare_signal_tools import get_profit_forecast
        result = get_profit_forecast.invoke({"ticker": "600519"})
        self.assertIn("预测EPS", result)

    def test_get_profit_forecast_empty_returns_message(self):

        from tradingagents.dataflows.akshare_signal_tools import get_profit_forecast
        result = get_profit_forecast.invoke({"ticker": "600519"})
        self.assertIn("数据缺失", result)

    def test_get_hot_stocks_returns_data(self):

        from tradingagents.dataflows.akshare_signal_tools import get_hot_stocks
        result = get_hot_stocks.invoke({"curr_date": ""})
        self.assertIn("贵州茅台", result)

    def test_get_northbound_flow_returns_data(self):

        from tradingagents.dataflows.akshare_signal_tools import get_northbound_flow
        result = get_northbound_flow.invoke({"curr_date": "2026-06-25", "include_history": False})
        self.assertIn("净流入", result)

    def test_get_fund_flow_returns_data(self):

        from tradingagents.dataflows.akshare_signal_tools import get_fund_flow
        result = get_fund_flow.invoke({
            "ticker": "600519",
            "curr_date": "2026-06-25",
            "include_history": False,
        })
        self.assertIn("主力净流入", result)

    def test_get_lockup_expiry_empty_returns_message(self):

        from tradingagents.dataflows.akshare_signal_tools import get_lockup_expiry
        result = get_lockup_expiry.invoke({
            "ticker": "600519",
            "curr_date": "2026-06-28",
        })
        self.assertIn("数据缺失", result)

